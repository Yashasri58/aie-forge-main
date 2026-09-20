"""
CodeGraph-based Tools for the Impact Analysis Agent.

This module provides graph query tools that use Kuzu as the storage backend
and codegraph-tools extraction for parsing code.

Architecture:
- codegraph-tools: Extracts AST → JSON
- Kuzu: Persistent graph database for queries
- This module: Tool interface for agents
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class CodeGraphTools:
    """
    Tools for querying the code graph using Kuzu as the backend.
    
    Provides the same interface as the original GraphTools but uses:
    - Kuzu for persistent storage and Cypher queries
    - codegraph-tools extraction JSON as the source
    """
    
    def __init__(
        self,
        kuzu_store=None,
        extraction_path: Optional[str] = None,
        services_path: Optional[str] = None,
    ):
        """
        Initialize with Kuzu store.
        
        Args:
            kuzu_store: KuzuCodeGraphStore instance (if None, creates one)
            extraction_path: Path to combined_extraction.json
            services_path: Path to services directory
        """
        from .kuzu_store import KuzuCodeGraphStore
        
        self._services_path = Path(services_path) if services_path else None
        
        # Use provided store or create one
        if kuzu_store:
            self._store = kuzu_store
        else:
            # Default DB path
            if services_path:
                db_path = Path(services_path) / "codegraph-out" / "code_graph.kuzu"
            else:
                db_path = Path("data/code_graph.kuzu")
            
            self._store = KuzuCodeGraphStore(str(db_path))
            self._store.init_schema()
            
            # Load extraction if provided
            if extraction_path and Path(extraction_path).exists():
                # Check if DB is empty
                if self._store.get_symbol_count() == 0:
                    logger.info(f"Loading extraction into Kuzu from {extraction_path}")
                    self._store.load_extraction(extraction_path)
                else:
                    logger.info(f"Kuzu DB already populated, skipping load")
        
        # Build cached indices
        self._build_indices()
        
        logger.info(
            f"CodeGraphTools ready: {len(self.services)} services, "
            f"{len(self.all_symbols)} symbols"
        )
    
    def _build_indices(self):
        """Build cached lookup indices."""
        self.services = self._store.get_services()
        
        # Get all symbols
        symbols = self._store.query("""
            MATCH (s:Symbol) 
            WHERE s.kind = 'function' OR s.kind = 'method'
            RETURN s.id AS id, s.name AS name, s.kind AS kind, s.service AS service
        """)
        self.all_symbols = symbols
    
    # =========================================================================
    # TOOL METHODS (matching GraphTools interface)
    # =========================================================================
    
    def get_schema(self) -> dict:
        """Return graph schema for LLM context."""
        return {
            "schema": "Kuzu graph database with codegraph-tools extraction",
            "node_types": ["Service", "Symbol", "HttpRoute"],
            "edge_types": ["CONTAINS", "CALLS", "EXPOSES", "HTTP_CALLS"],
            "services": self.services,
            "total_symbols": len(self.all_symbols),
            "hint": "Use search_symbols to find symbols, analyze_impact for full analysis"
        }
    
    def search_symbols(
        self,
        query: str,
        kind: Optional[str] = None,
        service: Optional[str] = None,
    ) -> dict:
        """Search for symbols matching a query.
        
        Args:
            query: Search string (partial match on function name)
            kind: Filter by kind (function, class, method)
            service: Filter by service/repo name
        
        Returns:
            List of matching symbols
        """
        results = self._store.search_symbols(query, service=service, limit=50)
        
        # Filter by kind if specified
        if kind:
            results = [r for r in results if r.get('kind') == kind]
        
        return {
            "query": query,
            "results": results,
            "count": len(results),
        }
    
    def trace_call_path(
        self,
        start_symbol: str,
        direction: str = "outgoing",
        max_depth: int = 4,
    ) -> dict:
        """Trace call chains from/to a symbol.
        
        Args:
            start_symbol: Function name to start from
            direction: 'outgoing' (what does X call?) or 'incoming' (what calls X?)
            max_depth: How many hops (1-6)
        
        Returns:
            Call paths and affected services
        """
        max_depth = min(max(1, max_depth), 6)
        
        # Find the symbol ID
        symbol_id = self._find_symbol_id(start_symbol)
        if not symbol_id:
            similar = self._find_similar(start_symbol)
            return {
                "error": f"Symbol '{start_symbol}' not found",
                "similar_symbols": similar[:5],
            }
        
        # Get call chains from Kuzu
        chains = self._store.get_call_chain(symbol_id, direction, max_depth)
        
        # Format paths
        paths = []
        affected_services = set()
        
        for chain in chains:
            chain_ids = chain.get('chain', [])
            if len(chain_ids) > 1:
                path_info = self._format_path(chain_ids)
                paths.append(path_info)
                affected_services.update(path_info.get('services', []))
        
        return {
            "symbol": start_symbol,
            "direction": direction,
            "max_depth": max_depth,
            "paths": paths[:20],
            "total_paths": len(paths),
            "affected_services": list(affected_services),
        }
    
    def _format_path(self, symbol_ids: List[str]) -> dict:
        """Format a path of symbol IDs into readable format."""
        names = []
        services = []
        
        for sid in symbol_ids:
            # Query symbol info
            rows = self._store.query(
                "MATCH (s:Symbol {id: $id}) RETURN s.name AS name, s.service AS service",
                {"id": sid}
            )
            if rows:
                names.append(rows[0].get('name', sid))
                svc = rows[0].get('service')
                if svc and svc not in services:
                    services.append(svc)
            else:
                names.append(sid)
        
        return {
            "path_names": names,
            "services": services,
            "depth": len(names) - 1,
        }
    
    def _find_symbol_id(self, name: str) -> Optional[str]:
        """Find a symbol ID by name."""
        # Exact match first
        rows = self._store.query(
            "MATCH (s:Symbol) WHERE s.name = $name RETURN s.id AS id LIMIT 1",
            {"name": name}
        )
        if rows:
            return rows[0]['id']
        
        # Partial match
        rows = self._store.query(
            "MATCH (s:Symbol) WHERE lower(s.name) CONTAINS $name RETURN s.id AS id LIMIT 1",
            {"name": name.lower()}
        )
        if rows:
            return rows[0]['id']
        
        return None
    
    def _find_similar(self, name: str) -> List[str]:
        """Find similar symbol names."""
        rows = self._store.query(
            """MATCH (s:Symbol) 
               WHERE lower(s.name) CONTAINS $prefix
               RETURN DISTINCT s.name AS name LIMIT 10""",
            {"prefix": name[:3].lower()}
        )
        return [r['name'] for r in rows]
    
    def analyze_impact(self, symbol_name: str) -> dict:
        """Comprehensive impact analysis - THE key tool.
        
        Args:
            symbol_name: Function/class to analyze
        
        Returns:
            Complete impact with callers, affected services, risk level
        """
        # Find the symbol
        symbol_id = self._find_symbol_id(symbol_name)
        if not symbol_id:
            similar = self._find_similar(symbol_name)
            return {
                "error": f"Symbol '{symbol_name}' not found",
                "similar_symbols": similar[:8],
            }
        
        # Get symbol info
        sym_rows = self._store.query(
            """MATCH (s:Symbol {id: $id})
               RETURN s.name AS name, s.service AS service, s.file AS file, 
                      s.kind AS kind, s.start_line AS start_line""",
            {"id": symbol_id}
        )
        if not sym_rows:
            return {"error": f"Symbol data not found for {symbol_id}"}
        
        sym_info = sym_rows[0]
        source_service = sym_info.get('service')
        
        # Get direct callers
        direct_callers = self._store.get_callers(symbol_id)
        
        # Get outgoing calls
        outgoing_calls = self._store.get_callees(symbol_id)
        
        # Get HTTP callers (services that call this service)
        http_callers = []
        if source_service:
            http_rows = self._store.query(
                """MATCH (a:Service)-[:HTTP_CALLS]->(b:Service {name: $service})
                   RETURN a.name AS caller""",
                {"service": source_service}
            )
            http_callers = [r['caller'] for r in http_rows]
        
        # Aggregate affected services
        affected_services = {}
        for c in direct_callers:
            svc = c.get("service")
            if svc:
                if svc not in affected_services:
                    affected_services[svc] = {"service": svc, "callers": []}
                affected_services[svc]["callers"].append(c["name"])
        
        # Add HTTP callers
        for http_svc in http_callers:
            if http_svc not in affected_services:
                affected_services[http_svc] = {
                    "service": http_svc,
                    "callers": [],
                    "via": "HTTP"
                }
        
        # Calculate risk
        total_affected = len(affected_services)
        risk_level = "HIGH" if total_affected >= 3 else \
                     "MEDIUM" if total_affected >= 1 else "LOW"
        
        # Build explanation
        explanation = [
            f"**{symbol_name}** in **{source_service}**",
            f"- {len(direct_callers)} direct callers",
            f"- {len(outgoing_calls)} outgoing calls",
            f"- Risk: {risk_level}",
        ]
        
        if affected_services:
            explanation.append("\nAffected services:")
            for svc, info in affected_services.items():
                callers = ", ".join(info.get("callers", [])[:3])
                via = f" (via {info.get('via')})" if info.get("via") else ""
                explanation.append(f"- {svc}{via}: {callers}")
        
        return {
            "symbol": {
                "name": symbol_name,
                "id": symbol_id,
                "service": source_service,
                "file": sym_info.get("file"),
                "line": sym_info.get("start_line"),
            },
            "direct_callers": direct_callers,
            "outgoing_calls": outgoing_calls[:20],
            "affected_services": list(affected_services.values()),
            "affected_service_names": list(affected_services.keys()),
            "http_callers": http_callers,
            "risk_level": risk_level,
            "explanation": "\n".join(explanation),
            "testing_recommendation": self._generate_test_rec(
                symbol_name, source_service, affected_services
            ),
        }
    
    def _generate_test_rec(self, symbol: str, service: str, affected: dict) -> str:
        """Generate testing recommendation."""
        parts = [f"1. Unit tests for `{symbol}` in {service}"]
        
        for svc in list(affected.keys())[:3]:
            parts.append(f"2. Integration tests for {svc} → {service}")
        
        if len(affected) > 3:
            parts.append(f"3. Run full regression for {len(affected)} affected services")
        
        return "\n".join(parts)
    
    def get_service_topology(self, service: Optional[str] = None) -> dict:
        """Get service dependency topology.
        
        Args:
            service: Filter by service name (optional)
        
        Returns:
            Service dependencies (incoming and outgoing)
        """
        if service:
            # Get incoming HTTP calls
            incoming_rows = self._store.query(
                """MATCH (a:Service)-[:HTTP_CALLS]->(b:Service {name: $service})
                   RETURN a.name AS caller""",
                {"service": service}
            )
            incoming = [r['caller'] for r in incoming_rows]
            
            # Get outgoing HTTP calls
            outgoing_rows = self._store.query(
                """MATCH (a:Service {name: $service})-[:HTTP_CALLS]->(b:Service)
                   RETURN b.name AS callee""",
                {"service": service}
            )
            outgoing = [r['callee'] for r in outgoing_rows]
            
            return {
                "service": service,
                "incoming": incoming,
                "outgoing": outgoing,
                "summary": f"{service} called by {len(incoming)} services, calls {len(outgoing)} services"
            }
        
        # Full topology
        deps = self._store.get_http_dependencies()
        
        # Build adjacency lists
        outgoing_map = {}
        incoming_map = {}
        for d in deps:
            src = d.get('from_service')
            tgt = d.get('to_service')
            if src not in outgoing_map:
                outgoing_map[src] = []
            outgoing_map[src].append(tgt)
            if tgt not in incoming_map:
                incoming_map[tgt] = []
            incoming_map[tgt].append(src)
        
        return {
            "services": self.services,
            "dependencies": deps,
            "outgoing": outgoing_map,
            "incoming": incoming_map,
            "summary": f"{len(self.services)} services, {len(deps)} HTTP dependencies"
        }
    
    def query_graph(self, cypher: str, params: Optional[dict] = None) -> dict:
        """Execute a Cypher query directly.
        
        Args:
            cypher: Cypher query string
            params: Query parameters
        
        Returns:
            Query results
        """
        try:
            results = self._store.query(cypher, params)
            return {
                "query": cypher,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {
                "error": str(e),
                "query": cypher,
            }
    
    def close(self):
        """Close the underlying store."""
        self._store.close()
