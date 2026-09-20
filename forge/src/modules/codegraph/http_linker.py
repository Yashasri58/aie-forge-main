"""
HTTP Service Linker
===================

Detects HTTP routes and cross-service HTTP calls to build the inter-service
dependency graph. This complements CodeGraph's intra-service call analysis.

What CodeGraph provides: function A calls function B (within a service)
What this provides: service A calls service B via HTTP (between services)

Usage:
    linker = HttpLinker('./services')
    routes = linker.extract_all_routes()
    http_edges = linker.link_services()
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HttpRoute:
    """An HTTP route defined in a service."""
    service: str
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str
    handler: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None


@dataclass
class HttpCall:
    """An HTTP call made from one service to another."""
    source_service: str
    target_url: str
    method: str
    source_file: str
    source_function: Optional[str] = None
    line: Optional[int] = None
    _resolved_target: Optional[str] = None  # Pre-resolved target service


@dataclass
class HttpEdge:
    """An edge representing a service-to-service HTTP dependency."""
    source: str  # Calling service
    target: str  # Target service
    route: str   # The URL/path being called
    method: str  # HTTP method
    confidence: float = 1.0
    source_file: Optional[str] = None


class HttpLinker:
    """
    Detects HTTP routes and cross-service dependencies.
    
    Patterns detected:
    - Express routes: app.get('/path', handler), router.post('/path', ...)
    - Fetch calls: fetch('http://service/path')
    - Axios calls: axios.get('http://service/path')
    """
    
    # Route definition patterns (Express-style)
    ROUTE_PATTERNS = [
        # app.get('/path', handler)
        r"app\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
        # router.get('/path', handler)
        r"router\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
        # @app.route('/path', methods=['GET'])
        r"@app\.route\s*\(\s*['\"]([^'\"]+)['\"]",
        # @GetMapping('/path')
        r"@(Get|Post|Put|Delete)Mapping\s*\(\s*['\"]([^'\"]+)['\"]",
    ]
    
    # HTTP call patterns
    CALL_PATTERNS = [
        # fetch('http://service/path') - literal strings
        r"fetch\s*\(\s*['\"]([^'\"]+)['\"]",
        # fetch(`${VAR}/path`) - template literals
        r"fetch\s*\(\s*`\$\{[^}]+\}([^`]*)`",
        # axios.get('http://service/path') - literal strings
        r"axios\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
        # axios.get(`${VAR}/path`) - template literals with variable prefix
        r"axios\.(get|post|put|delete|patch)\s*\(\s*`\$\{(\w+)\}([^`]*)`",
        # http.request({ url: 'http://...' })
        r"(?:http|request)\s*\.\s*(?:get|post|put|delete|request)\s*\([^)]*['\"]([^'\"]+)['\"]",
        # process.env.SERVICE_URL + '/path' (common pattern)
        r"(?:SERVICE|API)_URL[^+]*\+\s*['\"]([^'\"]+)['\"]",
    ]
    
    # Service URL variable patterns (VAR_NAME -> service mapping)
    SERVICE_VAR_MAP = {
        # Short names (used in gateway)
        'PAYMENT_SERVICE': 'payment-processor',
        'ACCOUNT_SERVICE': 'account-service', 
        'VALIDATION_SERVICE': 'validation-service',
        'FX_SERVICE': 'fx-service',
        'AUDIT_SERVICE': 'audit-service',
        'LEDGER_SERVICE': 'ledger-service',
        'GATEWAY_SERVICE': 'gateway-service',
        'API_BASE': 'gateway-service',
        # Full _URL names (used in clients)
        'PAYMENT_SERVICE_URL': 'payment-processor',
        'ACCOUNT_SERVICE_URL': 'account-service',
        'VALIDATION_SERVICE_URL': 'validation-service',
        'FX_SERVICE_URL': 'fx-service',
        'AUDIT_SERVICE_URL': 'audit-service',
        'LEDGER_SERVICE_URL': 'ledger-service',
        'GATEWAY_SERVICE_URL': 'gateway-service',
    }
    
    # Skip directories
    SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '__pycache__'}
    
    def __init__(
        self, 
        services_path: str | Path,
        service_urls: Optional[dict[str, list[str]]] = None
    ):
        """
        Args:
            services_path: Root directory containing microservice repos
            service_urls: Mapping of service names to URL patterns
                          e.g., {'payment-processor': ['localhost:3002', 'payment-processor']}
        """
        self.services_path = Path(services_path)
        
        # Build service URL mapping from discovered services
        self._services = self._discover_services()
        self.service_urls = service_urls or self._build_default_url_mapping()
        
        logger.info(f"HttpLinker initialized with {len(self._services)} services")
    
    def _discover_services(self) -> list[str]:
        """Find all service directories."""
        services = []
        for item in self.services_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith('.') or item.name in self.SKIP_DIRS:
                continue
            if (item / 'package.json').exists() or (item / 'src').exists():
                services.append(item.name)
        return services
    
    def _build_default_url_mapping(self) -> dict[str, list[str]]:
        """Build default URL patterns for each service."""
        mapping = {}
        for i, service in enumerate(self._services):
            # Common patterns: service name, localhost with port
            mapping[service] = [
                service,
                f"localhost:{3000 + i}",
                f"127.0.0.1:{3000 + i}",
            ]
        return mapping
    
    @property
    def services(self) -> list[str]:
        """List of discovered services."""
        return self._services
    
    def extract_routes(self, service: str) -> list[HttpRoute]:
        """
        Extract HTTP route definitions from a service.
        
        Args:
            service: Service name (directory name)
            
        Returns:
            List of HttpRoute objects
        """
        service_path = self.services_path / service
        routes = []
        
        for js_file in service_path.rglob('*.js'):
            if any(skip in str(js_file) for skip in self.SKIP_DIRS):
                continue
            
            try:
                content = js_file.read_text(encoding='utf-8')
            except Exception:
                continue
            
            for pattern in self.ROUTE_PATTERNS:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    groups = match.groups()
                    if len(groups) >= 2:
                        method = groups[0].upper()
                        path = groups[1]
                    else:
                        method = "GET"
                        path = groups[0]
                    
                    # Calculate line number
                    line = content[:match.start()].count('\n') + 1
                    
                    routes.append(HttpRoute(
                        service=service,
                        method=method,
                        path=path,
                        file=str(js_file.relative_to(self.services_path)),
                        line=line,
                    ))
        
        return routes
    
    def extract_http_calls(self, service: str) -> list[HttpCall]:
        """
        Extract outbound HTTP calls from a service.
        
        Args:
            service: Service name
            
        Returns:
            List of HttpCall objects
        """
        service_path = self.services_path / service
        calls = []
        
        for js_file in service_path.rglob('*.js'):
            if any(skip in str(js_file) for skip in self.SKIP_DIRS):
                continue
            
            try:
                content = js_file.read_text(encoding='utf-8')
            except Exception:
                continue
            
            # Pattern 1: axios with template literal `${VAR}/path`
            template_pattern = r"axios\.(get|post|put|delete|patch)\s*\(\s*`\$\{(\w+)\}([^`]*)`"
            for match in re.finditer(template_pattern, content, re.IGNORECASE):
                method, var_name, path = match.groups()
                line = content[:match.start()].count('\n') + 1
                
                # Resolve variable to target service
                target_service = self.SERVICE_VAR_MAP.get(var_name)
                if target_service and target_service != service:
                    calls.append(HttpCall(
                        source_service=service,
                        target_url=f"${{{var_name}}}{path}",
                        method=method.upper(),
                        source_file=str(js_file.relative_to(self.services_path)),
                        line=line,
                        _resolved_target=target_service,  # Store resolved target
                    ))
            
            # Pattern 2: fetch with template literal `${VAR}/path`
            fetch_template = r"fetch\s*\(\s*`\$\{([^}]+)\}([^`]*)`"
            for match in re.finditer(fetch_template, content, re.IGNORECASE):
                var_expr, path = match.groups()
                var_name = var_expr.split('}')[0].strip()  # Handle ${API_BASE}
                line = content[:match.start()].count('\n') + 1
                
                target_service = self.SERVICE_VAR_MAP.get(var_name)
                if target_service and target_service != service:
                    calls.append(HttpCall(
                        source_service=service,
                        target_url=f"${{{var_name}}}{path}",
                        method="GET",  # fetch defaults to GET
                        source_file=str(js_file.relative_to(self.services_path)),
                        line=line,
                        _resolved_target=target_service,
                    ))
            
            # Pattern 3: Literal URL patterns (original logic)
            for pattern in self.CALL_PATTERNS[:2]:  # Only literal string patterns
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    groups = match.groups()
                    
                    if len(groups) >= 2:
                        method = groups[0].upper() if groups[0] else "GET"
                        url = groups[1]
                    else:
                        method = "GET"
                        url = groups[0]
                    
                    if not self._is_internal_url(url):
                        continue
                    
                    line = content[:match.start()].count('\n') + 1
                    
                    calls.append(HttpCall(
                        source_service=service,
                        target_url=url,
                        method=method,
                        source_file=str(js_file.relative_to(self.services_path)),
                        line=line,
                    ))
        
        return calls
    
    def _is_internal_url(self, url: str) -> bool:
        """Check if URL points to an internal service."""
        url_lower = url.lower()
        
        # Check against known service patterns
        for service, patterns in self.service_urls.items():
            for pattern in patterns:
                if pattern.lower() in url_lower:
                    return True
        
        # Common internal patterns
        if 'localhost' in url_lower or '127.0.0.1' in url_lower:
            return True
        
        # Check for service names in URL
        for service in self._services:
            if service.lower() in url_lower:
                return True
        
        return False
    
    def _resolve_target_service(self, url: str) -> Optional[str]:
        """Resolve a URL to a target service name."""
        url_lower = url.lower()
        
        for service, patterns in self.service_urls.items():
            for pattern in patterns:
                if pattern.lower() in url_lower:
                    return service
        
        # Try to match service name directly
        for service in self._services:
            if service.lower() in url_lower:
                return service
        
        return None
    
    def extract_all_routes(self) -> list[HttpRoute]:
        """Extract routes from all services."""
        all_routes = []
        for service in self._services:
            routes = self.extract_routes(service)
            all_routes.extend(routes)
            logger.info(f"  {service}: {len(routes)} routes")
        return all_routes
    
    def extract_all_calls(self) -> list[HttpCall]:
        """Extract HTTP calls from all services."""
        all_calls = []
        for service in self._services:
            calls = self.extract_http_calls(service)
            all_calls.extend(calls)
            logger.info(f"  {service}: {len(calls)} HTTP calls")
        return all_calls
    
    def link_services(self) -> list[HttpEdge]:
        """
        Build HTTP edges between services.
        
        Returns:
            List of HttpEdge objects representing service dependencies
        """
        logger.info("Linking services...")
        
        calls = self.extract_all_calls()
        edges = []
        
        for call in calls:
            # Use pre-resolved target if available (from template literal matching)
            target = getattr(call, '_resolved_target', None) or self._resolve_target_service(call.target_url)
            
            if target and target != call.source_service:
                # Extract route path from URL
                route = self._extract_route_path(call.target_url)
                
                edges.append(HttpEdge(
                    source=call.source_service,
                    target=target,
                    route=route,
                    method=call.method,
                    source_file=call.source_file,
                ))
        
        # Deduplicate edges
        unique_edges = self._deduplicate_edges(edges)
        
        logger.info(f"Found {len(unique_edges)} HTTP edges between services")
        return unique_edges
    
    def _extract_route_path(self, url: str) -> str:
        """Extract the route path from a URL."""
        # Remove protocol and host
        url = re.sub(r'^https?://[^/]+', '', url)
        # Remove query string
        url = url.split('?')[0]
        return url or '/'
    
    def _deduplicate_edges(self, edges: list[HttpEdge]) -> list[HttpEdge]:
        """Remove duplicate edges, keeping one per source-target-route combo."""
        seen = set()
        unique = []
        
        for edge in edges:
            key = (edge.source, edge.target, edge.route)
            if key not in seen:
                seen.add(key)
                unique.append(edge)
        
        return unique
    
    def to_dict(self, edges: list[HttpEdge]) -> list[dict]:
        """Convert edges to dict format for JSON serialization."""
        return [
            {
                "source": e.source,
                "target": e.target,
                "route": e.route,
                "method": e.method,
                "relation": "HTTP_CALLS",
                "confidence": e.confidence,
                "source_file": e.source_file,
            }
            for e in edges
        ]
    
    def save_edges(self, edges: list[HttpEdge], path: str | Path) -> None:
        """Save edges to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(edges), f, indent=2)
