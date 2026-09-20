"""
Kuzu graph store for codegraph-tools extraction.

Loads extraction JSON into Kuzu for persistent, queryable graph storage.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

import kuzu


class KuzuCodeGraphStore:
    """
    Kuzu-backed storage for code graph data.
    
    Schema:
        - Service: name, path
        - Symbol: id, name, kind, file, start_line, end_line, service
        - CONTAINS: Service -> Symbol
        - CALLS: Symbol -> Symbol
        - HTTP_ROUTE: service, method, path, handler
        - HTTP_CALL: from_service, to_service, method, path
    """
    
    def __init__(self, db_path: str):
        """Initialize Kuzu connection."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.db = kuzu.Database(str(self.db_path))
        self.conn = kuzu.Connection(self.db)
        
    def init_schema(self):
        """Create node and relationship tables if they don't exist."""
        # Node tables
        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS Service(
                name STRING,
                path STRING,
                PRIMARY KEY(name)
            )
        """)
        
        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS Symbol(
                id STRING,
                name STRING,
                kind STRING,
                file STRING,
                start_line INT64,
                end_line INT64,
                service STRING,
                PRIMARY KEY(id)
            )
        """)
        
        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS HttpRoute(
                id STRING,
                service STRING,
                method STRING,
                path STRING,
                handler STRING,
                PRIMARY KEY(id)
            )
        """)
        
        # Relationship tables
        self._exec("""
            CREATE REL TABLE IF NOT EXISTS CONTAINS(
                FROM Service TO Symbol
            )
        """)
        
        self._exec("""
            CREATE REL TABLE IF NOT EXISTS CALLS(
                FROM Symbol TO Symbol
            )
        """)
        
        self._exec("""
            CREATE REL TABLE IF NOT EXISTS EXPOSES(
                FROM Service TO HttpRoute
            )
        """)
        
        self._exec("""
            CREATE REL TABLE IF NOT EXISTS HTTP_CALLS(
                FROM Service TO Service,
                method STRING,
                path STRING
            )
        """)

        # ── Enrichment tables (package deps, DB schemas, OpenAPI, env vars) ──

        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS Package(
                name STRING,
                PRIMARY KEY(name)
            )
        """)

        self._exec("""
            CREATE REL TABLE IF NOT EXISTS DEPENDS_ON(
                FROM Service TO Package,
                version STRING,
                dep_type STRING
            )
        """)

        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS DbTable(
                id STRING,
                service STRING,
                table_name STRING,
                PRIMARY KEY(id)
            )
        """)

        self._exec("""
            CREATE REL TABLE IF NOT EXISTS OWNS_TABLE(
                FROM Service TO DbTable
            )
        """)

        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS ApiEndpoint(
                id STRING,
                service STRING,
                method STRING,
                path STRING,
                operation_id STRING,
                PRIMARY KEY(id)
            )
        """)

        self._exec("""
            CREATE REL TABLE IF NOT EXISTS EXPOSES_ENDPOINT(
                FROM Service TO ApiEndpoint
            )
        """)

        self._exec("""
            CREATE NODE TABLE IF NOT EXISTS EnvVar(
                name STRING,
                PRIMARY KEY(name)
            )
        """)

        self._exec("""
            CREATE REL TABLE IF NOT EXISTS READS_ENV(
                FROM Service TO EnvVar
            )
        """)
        
    def _exec(self, query: str, params: Optional[Dict] = None):
        """Execute a query, ignoring errors for IF NOT EXISTS statements."""
        try:
            if params:
                return self.conn.execute(query, params)
            return self.conn.execute(query)
        except Exception as e:
            # Ignore "already exists" errors
            if "already exists" not in str(e).lower():
                raise
                
    def clear(self):
        """Clear all data (but keep schema)."""
        # Delete relationships first, then nodes
        for rel in ['HTTP_CALLS', 'EXPOSES', 'CALLS', 'CONTAINS']:
            try:
                self._exec(f"MATCH ()-[r:{rel}]->() DELETE r")
            except:
                pass
        for node in ['HttpRoute', 'Symbol', 'Service']:
            try:
                self._exec(f"MATCH (n:{node}) DELETE n")
            except:
                pass
                
    def load_extraction(self, extraction_path: str, http_data: Optional[Dict] = None):
        """
        Load codegraph extraction JSON into Kuzu.
        
        Args:
            extraction_path: Path to combined_extraction.json
            http_data: Optional HTTP routes/calls data from HttpLinker
        """
        with open(extraction_path, 'r') as f:
            data = json.load(f)
            
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        repos = data.get('repos', [])
        
        # Build service list from repos (may be strings or dicts)
        services = set()
        for repo in repos:
            if isinstance(repo, str):
                services.add(repo)
            elif isinstance(repo, dict):
                services.add(repo.get('name', Path(repo.get('root', '')).name))
            
        # Also extract services from node IDs (fallback)
        for node in nodes:
            node_id = node.get('id', '')
            if '::' in node_id:
                svc = node_id.split('::')[0]
                services.add(svc)
                
        # Insert services
        for svc in services:
            self._exec(
                "MERGE (s:Service {name: $name}) SET s.path = $path",
                {"name": svc, "path": ""}
            )
            
        # Insert symbols
        for node in nodes:
            node_id = node.get('id', '')
            label = node.get('label', '')
            # Extract name from label (remove parentheses and extension)
            name = label.replace('()', '').replace('.js', '').replace('.ts', '').strip()
            kind = node.get('kind', 'function')
            if '()' in label:
                kind = 'function'
            elif label.endswith('.js') or label.endswith('.ts'):
                kind = 'file'
            
            # Extract service from repo or node ID
            service = node.get('repo', '')
            if not service and '::' in node_id:
                service = node_id.split('::')[0]
            
            # Extract file info
            file_path = node.get('file', '')
            start_line = node.get('start', {}).get('line', 0) if isinstance(node.get('start'), dict) else 0
            end_line = node.get('end', {}).get('line', 0) if isinstance(node.get('end'), dict) else 0
            
            self._exec(
                """MERGE (sym:Symbol {id: $id}) 
                   SET sym.name = $name, 
                       sym.kind = $kind,
                       sym.file = $file,
                       sym.start_line = $start_line,
                       sym.end_line = $end_line,
                       sym.service = $service""",
                {
                    "id": node_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "service": service
                }
            )
            
            # Create CONTAINS relationship
            if service:
                self._exec(
                    """MATCH (svc:Service {name: $service}), (sym:Symbol {id: $id})
                       MERGE (svc)-[:CONTAINS]->(sym)""",
                    {"service": service, "id": node_id}
                )
                
        # Insert call edges
        for edge in edges:
            rel_type = edge.get('relation', edge.get('type', ''))
            source = edge.get('source', edge.get('from', ''))
            target = edge.get('target', edge.get('to', ''))
            
            if rel_type == 'calls' and source and target:
                self._exec(
                    """MATCH (a:Symbol {id: $source}), (b:Symbol {id: $target})
                       MERGE (a)-[:CALLS]->(b)""",
                    {"source": source, "target": target}
                )
                
        # Insert HTTP data if provided
        if http_data:
            routes = http_data.get('routes', [])
            calls = http_data.get('calls', [])
            
            for route in routes:
                route_id = f"{route['service']}::{route['method']}::{route['path']}"
                self._exec(
                    """MERGE (r:HttpRoute {id: $id})
                       SET r.service = $service,
                           r.method = $method,
                           r.path = $path,
                           r.handler = $handler""",
                    {
                        "id": route_id,
                        "service": route.get('service', ''),
                        "method": route.get('method', ''),
                        "path": route.get('path', ''),
                        "handler": route.get('handler', '')
                    }
                )
                
                # Link to service
                self._exec(
                    """MATCH (s:Service {name: $service}), (r:HttpRoute {id: $id})
                       MERGE (s)-[:EXPOSES]->(r)""",
                    {"service": route.get('service', ''), "id": route_id}
                )
                
            for call in calls:
                from_svc = call.get('from_service', '')
                to_svc = call.get('to_service', '')
                if from_svc and to_svc:
                    self._exec(
                        """MATCH (a:Service {name: $from}), (b:Service {name: $to})
                           MERGE (a)-[r:HTTP_CALLS]->(b)
                           SET r.method = $method, r.path = $path""",
                        {
                            "from": from_svc,
                            "to": to_svc,
                            "method": call.get('method', ''),
                            "path": call.get('path', '')
                        }
                    )
                    
        print(f"Loaded into Kuzu: {len(services)} services, {len(nodes)} symbols, {len([e for e in edges if e.get('relation') == 'calls'])} call edges")
        
    def query(self, cypher: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute Cypher query and return results as list of dicts."""
        result = self._exec(cypher, params)
        if result is None:
            return []
            
        rows = []
        while result.has_next():
            row = result.get_next()
            # Convert to dict using column names
            col_names = result.get_column_names()
            rows.append(dict(zip(col_names, row)))
        return rows
        
    def get_services(self) -> List[str]:
        """Get all service names."""
        rows = self.query("MATCH (s:Service) RETURN s.name AS name")
        return [r['name'] for r in rows]
        
    def get_symbols(self, service: Optional[str] = None) -> List[Dict]:
        """Get all symbols, optionally filtered by service."""
        if service:
            return self.query(
                "MATCH (sym:Symbol) WHERE sym.service = $service RETURN sym",
                {"service": service}
            )
        return self.query("MATCH (sym:Symbol) RETURN sym")
        
    def search_symbols(self, query: str, service: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Search symbols by name (case-insensitive contains)."""
        query_lower = query.lower()
        
        if service:
            cypher = """
                MATCH (sym:Symbol)
                WHERE sym.service = $service AND lower(sym.name) CONTAINS $query
                RETURN sym.id AS id, sym.name AS name, sym.kind AS kind, 
                       sym.service AS service, sym.file AS file,
                       sym.start_line AS start_line, sym.end_line AS end_line
                LIMIT $limit
            """
            return self.query(cypher, {"service": service, "query": query_lower, "limit": limit})
        else:
            cypher = """
                MATCH (sym:Symbol)
                WHERE lower(sym.name) CONTAINS $query
                RETURN sym.id AS id, sym.name AS name, sym.kind AS kind,
                       sym.service AS service, sym.file AS file,
                       sym.start_line AS start_line, sym.end_line AS end_line
                LIMIT $limit
            """
            return self.query(cypher, {"query": query_lower, "limit": limit})
            
    def get_callers(self, symbol_id: str) -> List[Dict]:
        """Get symbols that call the given symbol."""
        return self.query(
            """MATCH (caller:Symbol)-[:CALLS]->(target:Symbol {id: $id})
               RETURN caller.id AS id, caller.name AS name, caller.service AS service""",
            {"id": symbol_id}
        )
        
    def get_callees(self, symbol_id: str) -> List[Dict]:
        """Get symbols that the given symbol calls."""
        return self.query(
            """MATCH (source:Symbol {id: $id})-[:CALLS]->(callee:Symbol)
               RETURN callee.id AS id, callee.name AS name, callee.service AS service""",
            {"id": symbol_id}
        )
        
    def get_call_chain(self, symbol_id: str, direction: str = 'incoming', max_depth: int = 3) -> List[Dict]:
        """
        Get call chain for a symbol.
        
        Args:
            symbol_id: Symbol ID to start from
            direction: 'incoming' (callers) or 'outgoing' (callees)
            max_depth: Maximum traversal depth
        """
        # Kuzu doesn't support list comprehension in RETURN like Neo4j
        # Use recursive approach instead
        chains = []
        visited = set()
        
        def traverse(current_id: str, path: List[str], depth: int):
            if depth >= max_depth:
                if len(path) > 1:
                    chains.append({"chain": path.copy()})
                return
            
            if current_id in visited:
                return
            visited.add(current_id)
            
            # Get neighbors
            if direction == 'incoming':
                neighbors = self.get_callers(current_id)
            else:
                neighbors = self.get_callees(current_id)
            
            if not neighbors and len(path) > 1:
                chains.append({"chain": path.copy()})
                return
            
            for n in neighbors:
                neighbor_id = n.get('id')
                if neighbor_id and neighbor_id not in path:
                    new_path = path + [neighbor_id]
                    traverse(neighbor_id, new_path, depth + 1)
                    if len(chains) >= 50:  # Limit results
                        return
            
            visited.discard(current_id)
        
        traverse(symbol_id, [symbol_id], 0)
        return chains
        
    def get_http_dependencies(self) -> List[Dict]:
        """Get HTTP service dependencies."""
        return self.query("""
            MATCH (a:Service)-[r:HTTP_CALLS]->(b:Service)
            RETURN a.name AS from_service, b.name AS to_service, 
                   r.method AS method, r.path AS path
        """)
        
    def get_symbol_count(self) -> int:
        """Get total symbol count."""
        rows = self.query("MATCH (s:Symbol) RETURN count(s) AS cnt")
        return rows[0]['cnt'] if rows else 0
        
    def load_enrichment(self, enrichment: dict):
        """
        Load enrichment data into Kuzu.

        Expects the dict produced by CodeGraphEnricher.extract_all():
            {
              "packages":   [{"service", "package", "version", "dep_type"}],
              "db_tables":  [{"service", "table", "columns": [...]}],
              "endpoints":  [{"service", "method", "path", "operation_id"}],
              "env_vars":   [{"service", "env_var"}],
            }
        """
        # ── 1. Package dependencies ──────────────────────────────────────────
        for dep in enrichment.get("packages", []):
            pkg = dep["package"]
            # Upsert Package node
            self._exec(
                "MERGE (p:Package {name: $name})",
                {"name": pkg}
            )
            # Upsert DEPENDS_ON edge (Service must already exist from load_extraction)
            self._exec(
                """MATCH (s:Service {name: $svc}), (p:Package {name: $pkg})
                   MERGE (s)-[r:DEPENDS_ON]->(p)
                   SET r.version = $ver, r.dep_type = $dt""",
                {
                    "svc": dep["service"],
                    "pkg": pkg,
                    "ver": dep.get("version", ""),
                    "dt":  dep.get("dep_type", "runtime"),
                }
            )

        # ── 2. Database table schemas ────────────────────────────────────────
        for tbl in enrichment.get("db_tables", []):
            tbl_id = f"{tbl['service']}::{tbl['table']}"
            self._exec(
                """MERGE (t:DbTable {id: $id})
                   SET t.service = $svc, t.table_name = $tbl""",
                {"id": tbl_id, "svc": tbl["service"], "tbl": tbl["table"]}
            )
            self._exec(
                """MATCH (s:Service {name: $svc}), (t:DbTable {id: $id})
                   MERGE (s)-[:OWNS_TABLE]->(t)""",
                {"svc": tbl["service"], "id": tbl_id}
            )

        # ── 3. OpenAPI endpoints ─────────────────────────────────────────────
        for ep in enrichment.get("endpoints", []):
            ep_id = f"{ep['service']}::{ep['method']}::{ep['path']}"
            self._exec(
                """MERGE (e:ApiEndpoint {id: $id})
                   SET e.service = $svc,
                       e.method  = $method,
                       e.path    = $path,
                       e.operation_id = $op_id""",
                {
                    "id":     ep_id,
                    "svc":    ep["service"],
                    "method": ep["method"],
                    "path":   ep["path"],
                    "op_id":  ep.get("operation_id") or "",
                }
            )
            self._exec(
                """MATCH (s:Service {name: $svc}), (e:ApiEndpoint {id: $id})
                   MERGE (s)-[:EXPOSES_ENDPOINT]->(e)""",
                {"svc": ep["service"], "id": ep_id}
            )

        # ── 4. Environment variables ─────────────────────────────────────────
        for ev in enrichment.get("env_vars", []):
            self._exec(
                "MERGE (e:EnvVar {name: $name})",
                {"name": ev["env_var"]}
            )
            self._exec(
                """MATCH (s:Service {name: $svc}), (e:EnvVar {name: $name})
                   MERGE (s)-[:READS_ENV]->(e)""",
                {"svc": ev["service"], "name": ev["env_var"]}
            )

        pkg_count = len(set(d["package"] for d in enrichment.get("packages", [])))
        tbl_count = len(enrichment.get("db_tables", []))
        ep_count  = len(enrichment.get("endpoints", []))
        ev_count  = len(set(e["env_var"] for e in enrichment.get("env_vars", [])))
        print(
            f"Enrichment loaded: {pkg_count} packages, "
            f"{tbl_count} DB tables, {ep_count} API endpoints, {ev_count} env vars"
        )

    def close(self):
        """Close database connection."""
        # Kuzu handles cleanup automatically
        pass
