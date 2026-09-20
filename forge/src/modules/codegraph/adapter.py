"""
Unified Graph Adapter
=====================

Combines CodeGraph's symbol graph with Forge's HTTP service topology to provide
a unified query API for impact analysis.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                   UnifiedGraphAdapter                        │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  ┌─────────────────────┐    ┌─────────────────────┐        │
    │  │    CodeGraph        │    │    HTTP Topology    │        │
    │  │  (Symbol Graph)     │    │  (Service Graph)    │        │
    │  │  - NetworkX         │    │  - NetworkX         │        │
    │  │  - Functions/Classes│    │  - HTTP_CALLS edges │        │
    │  │  - CALLS edges      │    │                     │        │
    │  └─────────────────────┘    └─────────────────────┘        │
    │                                                             │
    │  Methods:                                                   │
    │  - search_symbol(query) → Find symbols across repos         │
    │  - get_internal_callers(symbol) → Within-service callers    │
    │  - get_external_callers(service) → Cross-service HTTP deps  │
    │  - trace_full_impact(symbol) → Complete impact chain        │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘

Usage:
    adapter = UnifiedGraphAdapter(extraction_path, http_edges)
    
    # Find a symbol
    results = adapter.search_symbol('processPayment')
    
    # Get full impact
    impact = adapter.trace_full_impact('payment_processor_processpayment')
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field

# Import codegraph-tools for graph building
try:
    from codegraph.build import build
    import networkx as nx
    CODEGRAPH_AVAILABLE = True
except ImportError:
    CODEGRAPH_AVAILABLE = False
    build = None
    nx = None

logger = logging.getLogger(__name__)


@dataclass
class ImpactResult:
    """Result of an impact analysis query."""
    symbol_id: str
    symbol_name: str
    service: str
    file: Optional[str] = None
    line: Optional[int] = None
    
    # Internal callers (within same service)
    internal_callers: list[dict] = field(default_factory=list)
    
    # External callers (other services via HTTP)
    external_callers: list[str] = field(default_factory=list)
    
    # HTTP routes that might be affected
    affected_routes: list[str] = field(default_factory=list)
    
    # Layered impact chain
    impact_chain: list[dict] = field(default_factory=list)
    
    # Risk assessment
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    
    def to_dict(self) -> dict:
        return {
            "symbol_id": self.symbol_id,
            "symbol_name": self.symbol_name,
            "service": self.service,
            "file": self.file,
            "line": self.line,
            "internal_callers": self.internal_callers,
            "external_callers": self.external_callers,
            "affected_routes": self.affected_routes,
            "impact_chain": self.impact_chain,
            "risk_level": self.risk_level,
        }


class UnifiedGraphAdapter:
    """
    Unified graph adapter combining CodeGraph symbols with HTTP topology.
    
    Provides a single query API for impact analysis across both:
    - Intra-service: Function calls within a service (from CodeGraph)
    - Inter-service: HTTP calls between services (from HttpLinker)
    """
    
    def __init__(
        self,
        extraction_path: Optional[Union[str, Path]] = None,
        extraction_data: Optional[dict] = None,
        http_edges: Optional[list[dict]] = None,
    ):
        """
        Args:
            extraction_path: Path to combined_extraction.json
            extraction_data: Extraction dict (alternative to path)
            http_edges: List of HTTP edge dicts from HttpLinker
        """
        if not CODEGRAPH_AVAILABLE:
            raise ImportError("codegraph-tools not installed")
        
        # Load extraction data
        if extraction_data:
            self._extraction = extraction_data
        elif extraction_path:
            with open(extraction_path, 'r', encoding='utf-8') as f:
                self._extraction = json.load(f)
        else:
            raise ValueError("Either extraction_path or extraction_data required")
        
        # Build symbol graph from CodeGraph extraction
        self.symbol_graph: nx.DiGraph = build([self._extraction], directed=True)
        logger.info(
            f"Symbol graph: {self.symbol_graph.number_of_nodes()} nodes, "
            f"{self.symbol_graph.number_of_edges()} edges"
        )
        
        # Build service topology graph from HTTP edges
        self.service_graph = nx.DiGraph()
        if http_edges:
            for edge in http_edges:
                self.service_graph.add_edge(
                    edge["source"],
                    edge["target"],
                    route=edge.get("route", "/"),
                    method=edge.get("method", "GET"),
                    relation="HTTP_CALLS",
                )
            logger.info(
                f"Service graph: {self.service_graph.number_of_nodes()} services, "
                f"{self.service_graph.number_of_edges()} HTTP edges"
            )
        
        # Build lookup indices
        self._build_indices()
    
    def _build_indices(self) -> None:
        """Build lookup indices for fast querying."""
        # Map label (function name) to node IDs
        self._label_to_ids: dict[str, list[str]] = {}
        
        # Map repo/service to node IDs
        self._repo_to_ids: dict[str, list[str]] = {}
        
        for node_id in self.symbol_graph.nodes():
            attrs = self.symbol_graph.nodes[node_id]
            
            # Index by label
            label = attrs.get("label", "")
            if label:
                clean_label = label.strip("().").lower()
                if clean_label not in self._label_to_ids:
                    self._label_to_ids[clean_label] = []
                self._label_to_ids[clean_label].append(node_id)
            
            # Index by repo
            repo = self._get_repo_from_attrs(attrs)
            if repo:
                if repo not in self._repo_to_ids:
                    self._repo_to_ids[repo] = []
                self._repo_to_ids[repo].append(node_id)
    
    def _get_repo_from_attrs(self, attrs: dict) -> Optional[str]:
        """Extract repo/service name from node attributes."""
        # Try explicit repo field
        if attrs.get("repo"):
            return attrs["repo"]
        
        # Extract from source_file path
        source_file = attrs.get("source_file", "")
        if source_file:
            parts = source_file.replace("\\", "/").split("/")
            if parts:
                return parts[0]
        
        return None
    
    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================
    
    def search_symbol(
        self,
        query: str,
        kind: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Search for symbols matching a query.
        
        Args:
            query: Search string (partial match)
            kind: Filter by kind (function, class, method)
            service: Filter by service/repo name
            limit: Maximum results
            
        Returns:
            List of matching symbol dicts
        """
        results = []
        query_lower = query.lower()
        
        for node_id in self.symbol_graph.nodes():
            attrs = self.symbol_graph.nodes[node_id]
            label = attrs.get("label", "")
            
            # Check query match
            if query_lower not in label.lower():
                continue
            
            # Check kind filter (only include functions)
            if kind and "()" not in label:
                continue
            
            # Check service filter
            if service:
                repo = self._get_repo_from_attrs(attrs)
                if repo and service.lower() not in repo.lower():
                    continue
            
            results.append({
                "id": node_id,
                "label": label,
                "file": attrs.get("source_file"),
                "line": attrs.get("source_location"),
                "repo": self._get_repo_from_attrs(attrs),
            })
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_symbol(self, symbol_id: str) -> Optional[dict]:
        """Get a symbol by its ID."""
        if symbol_id not in self.symbol_graph.nodes():
            return None
        
        attrs = self.symbol_graph.nodes[symbol_id]
        return {
            "id": symbol_id,
            "label": attrs.get("label"),
            "file": attrs.get("source_file"),
            "line": attrs.get("source_location"),
            "repo": self._get_repo_from_attrs(attrs),
        }
    
    # =========================================================================
    # CALLER OPERATIONS (Internal - within service)
    # =========================================================================
    
    def get_internal_callers(self, symbol_id: str) -> list[dict]:
        """
        Get functions that call this symbol (within the same service).
        
        Args:
            symbol_id: Node ID of the target symbol
            
        Returns:
            List of caller symbol dicts
        """
        callers = []
        
        for caller_id in self.symbol_graph.predecessors(symbol_id):
            attrs = self.symbol_graph.nodes[caller_id]
            label = attrs.get("label", "")
            
            # Only include functions (have parentheses)
            if "()" not in label:
                continue
            
            callers.append({
                "id": caller_id,
                "label": label,
                "file": attrs.get("source_file"),
                "line": attrs.get("source_location"),
                "repo": self._get_repo_from_attrs(attrs),
            })
        
        return callers
    
    def get_internal_callees(self, symbol_id: str) -> list[dict]:
        """
        Get functions that this symbol calls (within the same service).
        """
        callees = []
        
        for callee_id in self.symbol_graph.successors(symbol_id):
            attrs = self.symbol_graph.nodes[callee_id]
            label = attrs.get("label", "")
            
            if "()" not in label:
                continue
            
            callees.append({
                "id": callee_id,
                "label": label,
                "file": attrs.get("source_file"),
                "line": attrs.get("source_location"),
                "repo": self._get_repo_from_attrs(attrs),
            })
        
        return callees
    
    # =========================================================================
    # CALLER OPERATIONS (External - cross-service HTTP)
    # =========================================================================
    
    def get_external_callers(self, service: str) -> list[str]:
        """
        Get services that call this service via HTTP.
        
        Args:
            service: Service name
            
        Returns:
            List of calling service names
        """
        if service not in self.service_graph:
            return []
        
        return list(self.service_graph.predecessors(service))
    
    def get_external_callees(self, service: str) -> list[str]:
        """
        Get services that this service calls via HTTP.
        """
        if service not in self.service_graph:
            return []
        
        return list(self.service_graph.successors(service))
    
    def get_http_routes_to_service(self, service: str) -> list[dict]:
        """Get HTTP routes that call this service."""
        routes = []
        
        for caller in self.service_graph.predecessors(service):
            edge_data = self.service_graph.get_edge_data(caller, service)
            if edge_data:
                routes.append({
                    "caller": caller,
                    "route": edge_data.get("route", "/"),
                    "method": edge_data.get("method", "GET"),
                })
        
        return routes
    
    # =========================================================================
    # IMPACT ANALYSIS
    # =========================================================================
    
    def trace_full_impact(self, symbol_id: str) -> ImpactResult:
        """
        Get complete impact analysis for a symbol change.
        
        Combines:
        1. Internal callers (CodeGraph - within service)
        2. External callers (HTTP topology - cross-service)
        3. Layered impact chain
        
        Args:
            symbol_id: Node ID of the symbol to analyze
            
        Returns:
            ImpactResult with full impact chain
        """
        # Get symbol info
        symbol = self.get_symbol(symbol_id)
        if not symbol:
            # Try searching by name
            results = self.search_symbol(symbol_id, limit=1)
            if results:
                symbol = results[0]
                symbol_id = symbol["id"]
            else:
                return ImpactResult(
                    symbol_id=symbol_id,
                    symbol_name="Unknown",
                    service="Unknown",
                    risk_level="UNKNOWN",
                )
        
        service = symbol.get("repo") or "unknown"
        
        # Get internal callers (within service)
        internal_callers = self.get_internal_callers(symbol_id)
        
        # Get external callers (cross-service HTTP)
        external_callers = self.get_external_callers(service)
        
        # Get HTTP routes to this service
        http_routes = self.get_http_routes_to_service(service)
        affected_routes = [r["route"] for r in http_routes]
        
        # Build layered impact chain
        impact_chain = self._build_impact_chain(
            symbol, service, internal_callers, external_callers
        )
        
        # Assess risk level
        risk_level = self._assess_risk(
            internal_callers, external_callers
        )
        
        return ImpactResult(
            symbol_id=symbol_id,
            symbol_name=symbol.get("label", "Unknown"),
            service=service,
            file=symbol.get("file"),
            line=symbol.get("line"),
            internal_callers=internal_callers,
            external_callers=external_callers,
            affected_routes=affected_routes,
            impact_chain=impact_chain,
            risk_level=risk_level,
        )
    
    def _build_impact_chain(
        self,
        symbol: dict,
        service: str,
        internal_callers: list[dict],
        external_callers: list[str],
    ) -> list[dict]:
        """Build a layered impact chain."""
        chain = []
        
        # Layer 0: The changed symbol
        chain.append({
            "layer": 0,
            "type": "direct_change",
            "items": [{
                "name": symbol.get("label"),
                "service": service,
                "file": symbol.get("file"),
            }],
        })
        
        # Layer 1: Internal callers (within service)
        if internal_callers:
            chain.append({
                "layer": 1,
                "type": "internal_callers",
                "description": f"Functions in {service} that call this",
                "items": [
                    {
                        "name": c["label"],
                        "file": c.get("file"),
                    }
                    for c in internal_callers
                ],
            })
        
        # Layer 2: External service callers (via HTTP)
        if external_callers:
            chain.append({
                "layer": 2,
                "type": "http_callers",
                "description": "Services that call via HTTP",
                "items": [{"service": s} for s in external_callers],
            })
        
        return chain
    
    def _assess_risk(
        self,
        internal_callers: list[dict],
        external_callers: list[str],
    ) -> str:
        """Assess risk level based on impact scope."""
        total_callers = len(internal_callers) + len(external_callers)
        external_count = len(external_callers)
        
        if external_count >= 3 or total_callers >= 10:
            return "HIGH"
        elif external_count >= 1 or total_callers >= 5:
            return "MEDIUM"
        else:
            return "LOW"
    
    # =========================================================================
    # PATH FINDING
    # =========================================================================
    
    def find_call_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[list[str]]:
        """
        Find the shortest call path between two symbols.
        
        Args:
            source_id: Starting symbol ID
            target_id: Target symbol ID
            max_depth: Maximum path length
            
        Returns:
            List of node IDs in the path, or None if no path exists
        """
        try:
            if nx.has_path(self.symbol_graph, source_id, target_id):
                path = nx.shortest_path(self.symbol_graph, source_id, target_id)
                if len(path) <= max_depth + 1:
                    return path
        except nx.NetworkXError:
            pass
        
        return None
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get graph statistics."""
        return {
            "symbol_nodes": self.symbol_graph.number_of_nodes(),
            "symbol_edges": self.symbol_graph.number_of_edges(),
            "services": self.service_graph.number_of_nodes(),
            "http_edges": self.service_graph.number_of_edges(),
            "repos": list(self._repo_to_ids.keys()),
        }
