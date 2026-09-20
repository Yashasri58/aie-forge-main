"""
Graph Explorer API Router.

Provides endpoints for interactive graph visualization with drill-down capability.
Similar to Neo4j browser - click a node to expand and see connected nodes.

Levels:
1. Services (top level)
2. Symbols (in a service)
3. Calls (from a symbol)

Updated for new Kuzu schema:
- Service(name, path)
- Symbol(id, name, kind, file, start_line, end_line, service)
- CALLS, CONTAINS, HTTP_CALLS relationships
"""

from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/graph", tags=["Graph Explorer"])


# =============================================================================
# MODELS
# =============================================================================

class GraphNode(BaseModel):
    """A node in the graph visualization."""
    id: str
    label: str
    type: Literal["service", "file", "symbol", "route"]
    properties: dict = Field(default_factory=dict)
    kind: Optional[str] = None
    service: Optional[str] = None
    file_path: Optional[str] = None
    expandable: bool = True
    child_count: int = 0


class GraphEdge(BaseModel):
    """An edge in the graph visualization."""
    id: str
    source: str
    target: str
    type: str
    properties: dict = Field(default_factory=dict)


class GraphData(BaseModel):
    """Graph data for visualization."""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int
    level: str
    parent_id: Optional[str] = None


class ExpandRequest(BaseModel):
    """Request to expand a node."""
    node_id: str
    node_type: Literal["service", "file", "symbol", "route"]
    direction: Literal["outgoing", "incoming", "both"] = "both"
    limit: int = Field(default=50, le=200)


# =============================================================================
# STORE REFERENCE
# =============================================================================

_store = None


def set_store(store):
    """Set the graph store reference."""
    global _store
    _store = store


def get_store():
    """Get the graph store."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Graph not loaded")
    return _store


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/overview", response_model=GraphData)
async def get_overview():
    """
    Get the top-level overview: all services.
    """
    store = get_store()
    
    # Get all services
    services = store.query("MATCH (s:Service) RETURN s.name AS name", {})
    
    # Get symbol counts per service
    counts = store.query(
        "MATCH (s:Symbol) RETURN s.service AS service, count(*) AS count",
        {}
    )
    count_map = {r["service"]: r["count"] for r in counts}
    
    # Get HTTP dependencies
    http_deps = store.query(
        "MATCH (a:Service)-[r:HTTP_CALLS]->(b:Service) RETURN a.name AS source, b.name AS target",
        {}
    )
    
    # Build nodes
    nodes = []
    for svc in services:
        svc_name = svc["name"]
        nodes.append(GraphNode(
            id=f"service:{svc_name}",
            label=svc_name,
            type="service",
            properties={"name": svc_name},
            expandable=True,
            child_count=count_map.get(svc_name, 0)
        ))
    
    # Build edges
    edges = []
    seen = set()
    for dep in http_deps:
        key = f"{dep['source']}->{dep['target']}"
        if key not in seen:
            seen.add(key)
            edges.append(GraphEdge(
                id=f"http:{dep['source']}:{dep['target']}",
                source=f"service:{dep['source']}",
                target=f"service:{dep['target']}",
                type="HTTP_CALLS"
            ))
    
    return GraphData(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        level="services"
    )


@router.get("/service/{service_id}", response_model=GraphData)
async def get_service_contents(
    service_id: str,
    show: Literal["files", "symbols", "both"] = "symbols"
):
    """
    Expand a service to see its symbols.
    """
    store = get_store()
    
    nodes = []
    edges = []
    
    # Add service node as parent
    nodes.append(GraphNode(
        id=f"service:{service_id}",
        label=service_id,
        type="service",
        expandable=True
    ))
    
    # Get symbols in this service
    symbols = store.query(
        """
        MATCH (s:Symbol)
        WHERE s.service = $svc
        RETURN s.id AS id, s.name AS name, s.kind AS kind, 
               s.file AS file, s.start_line AS line
        ORDER BY s.file, s.start_line
        LIMIT 100
        """,
        {"svc": service_id}
    )
    
    for sym in symbols:
        nodes.append(GraphNode(
            id=f"symbol:{sym['id']}",
            label=sym["name"],
            type="symbol",
            kind=sym["kind"],
            service=service_id,
            file_path=sym.get("file"),
            properties={"line": sym.get("line")},
            expandable=True
        ))
        
        edges.append(GraphEdge(
            id=f"contains:{service_id}:{sym['id']}",
            source=f"service:{service_id}",
            target=f"symbol:{sym['id']}",
            type="CONTAINS"
        ))
    
    return GraphData(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        level="symbols",
        parent_id=f"service:{service_id}"
    )


@router.get("/symbol/{symbol_id}", response_model=GraphData)
async def get_symbol_calls(
    symbol_id: str,
    direction: Literal["outgoing", "incoming", "both"] = "both",
    limit: int = Query(default=50, le=200)
):
    """
    Expand a symbol to see what it calls and what calls it.
    """
    store = get_store()
    
    nodes = []
    edges = []
    
    # Get source symbol info
    source = store.query(
        """
        MATCH (s:Symbol {id: $id})
        RETURN s.id AS id, s.name AS name, s.kind AS kind, 
               s.service AS service, s.file AS file
        """,
        {"id": symbol_id}
    )
    
    if not source:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol_id} not found")
    
    src = source[0]
    nodes.append(GraphNode(
        id=f"symbol:{src['id']}",
        label=src["name"],
        type="symbol",
        kind=src["kind"],
        service=src["service"],
        file_path=src.get("file"),
        expandable=True
    ))
    
    # Get outgoing calls
    if direction in ("outgoing", "both"):
        outgoing = store.query(
            """
            MATCH (s:Symbol {id: $id})-[:CALLS]->(t:Symbol)
            RETURN DISTINCT t.id AS id, t.name AS name, t.kind AS kind,
                   t.service AS service, t.file AS file
            LIMIT $limit
            """,
            {"id": symbol_id, "limit": limit // 2 if direction == "both" else limit}
        )
        
        for target in outgoing:
            nodes.append(GraphNode(
                id=f"symbol:{target['id']}",
                label=target["name"],
                type="symbol",
                kind=target["kind"],
                service=target["service"],
                file_path=target.get("file"),
                expandable=True
            ))
            edges.append(GraphEdge(
                id=f"calls:{symbol_id}:{target['id']}",
                source=f"symbol:{src['id']}",
                target=f"symbol:{target['id']}",
                type="CALLS",
                properties={"direction": "outgoing"}
            ))
    
    # Get incoming calls
    if direction in ("incoming", "both"):
        incoming = store.query(
            """
            MATCH (c:Symbol)-[:CALLS]->(s:Symbol {id: $id})
            RETURN DISTINCT c.id AS id, c.name AS name, c.kind AS kind,
                   c.service AS service, c.file AS file
            LIMIT $limit
            """,
            {"id": symbol_id, "limit": limit // 2 if direction == "both" else limit}
        )
        
        for caller in incoming:
            node_id = f"symbol:{caller['id']}"
            if not any(n.id == node_id for n in nodes):
                nodes.append(GraphNode(
                    id=node_id,
                    label=caller["name"],
                    type="symbol",
                    kind=caller["kind"],
                    service=caller["service"],
                    file_path=caller.get("file"),
                    expandable=True
                ))
            
            edges.append(GraphEdge(
                id=f"calls:{caller['id']}:{symbol_id}",
                source=f"symbol:{caller['id']}",
                target=f"symbol:{src['id']}",
                type="CALLS",
                properties={"direction": "incoming"}
            ))
    
    return GraphData(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        level="calls",
        parent_id=f"symbol:{symbol_id}"
    )


@router.post("/expand", response_model=GraphData)
async def expand_node(request: ExpandRequest):
    """Generic endpoint to expand any node type."""
    if request.node_type == "service":
        service_id = request.node_id.replace("service:", "")
        return await get_service_contents(service_id)
    
    elif request.node_type == "symbol":
        symbol_id = request.node_id.replace("symbol:", "")
        return await get_symbol_calls(symbol_id, request.direction, request.limit)
    
    else:
        raise HTTPException(status_code=400, detail=f"Cannot expand node type: {request.node_type}")


@router.get("/stats")
async def get_graph_stats():
    """Get statistics about the graph."""
    store = get_store()
    
    # Count services
    svc_result = store.query("MATCH (s:Service) RETURN count(*) AS count", {})
    service_count = svc_result[0]["count"] if svc_result else 0
    
    # Count symbols
    sym_result = store.query("MATCH (s:Symbol) RETURN count(*) AS count", {})
    symbol_count = sym_result[0]["count"] if sym_result else 0
    
    # Count call edges
    calls_result = store.query("MATCH ()-[r:CALLS]->() RETURN count(*) AS count", {})
    calls_count = calls_result[0]["count"] if calls_result else 0
    
    # Symbols by service
    by_service = store.query(
        "MATCH (s:Symbol) RETURN s.service AS service, count(*) AS count ORDER BY count DESC",
        {}
    )
    
    # Symbols by kind
    by_kind = store.query(
        "MATCH (s:Symbol) RETURN s.kind AS kind, count(*) AS count ORDER BY count DESC",
        {}
    )
    
    return {
        "nodes": {
            "services": service_count,
            "symbols": symbol_count,
            "total": service_count + symbol_count
        },
        "edges": {
            "calls": calls_count,
            "total": calls_count
        },
        "symbols_by_service": {r["service"]: r["count"] for r in by_service if r["service"]},
        "symbols_by_kind": {r["kind"]: r["count"] for r in by_kind if r["kind"]}
    }


@router.get("/path")
async def find_path(
    source: str = Query(..., description="Source node ID"),
    target: str = Query(..., description="Target node ID"),
    max_depth: int = Query(default=5, ge=1, le=10)
):
    """Find shortest path between two symbols."""
    store = get_store()
    
    src_id = source.replace("symbol:", "")
    tgt_id = target.replace("symbol:", "")
    
    # Simple BFS since Kuzu doesn't support shortestPath the same way
    # For now, return not found - would need manual implementation
    return {
        "found": False,
        "source": source,
        "target": target,
        "message": "Path finding requires manual BFS implementation"
    }


# =============================================================================
# ENRICHMENT ENDPOINTS
# =============================================================================

@router.get("/enrichment/packages")
async def get_packages(service: Optional[str] = None):
    """
    Get npm package dependencies.
    Returns all services and their runtime packages, with shared-package grouping.
    Optionally filter by service name.
    """
    store = get_store()

    cypher = (
        "MATCH (s:Service)-[r:DEPENDS_ON]->(p:Package) "
        + (f"WHERE s.name = '{service}' " if service else "")
        + "RETURN s.name AS service, p.name AS package, "
        + "r.version AS version, r.dep_type AS dep_type "
        + "ORDER BY s.name, p.name"
    )
    rows = store.query(cypher)

    # Group by service
    by_service: dict = {}
    for r in rows:
        svc = r["service"]
        if svc not in by_service:
            by_service[svc] = {"runtime": [], "dev": []}
        entry = {"package": r["package"], "version": r.get("version", "")}
        if r.get("dep_type") == "dev":
            by_service[svc]["dev"].append(entry)
        else:
            by_service[svc]["runtime"].append(entry)

    # Find shared packages (used by 2+ services)
    from collections import defaultdict
    pkg_to_services: dict = defaultdict(list)
    for r in rows:
        if r.get("dep_type") != "dev":
            pkg_to_services[r["package"]].append(r["service"])

    shared = [
        {"package": pkg, "used_by": list(set(svcs))}
        for pkg, svcs in pkg_to_services.items()
        if len(set(svcs)) > 1
    ]

    return {
        "by_service": by_service,
        "shared_packages": sorted(shared, key=lambda x: x["package"]),
        "total_entries": len(rows),
    }


@router.get("/enrichment/db-tables")
async def get_db_tables(service: Optional[str] = None):
    """
    Get database table schemas per service.
    Optionally filter by service name.
    """
    store = get_store()

    cypher = (
        "MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable) "
        + (f"WHERE s.name = '{service}' " if service else "")
        + "RETURN s.name AS service, t.table_name AS table_name "
        + "ORDER BY s.name, t.table_name"
    )
    rows = store.query(cypher)

    by_service: dict = {}
    for r in rows:
        svc = r["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append(r["table_name"])

    return {
        "by_service": by_service,
        "total_tables": len(rows),
    }


@router.get("/enrichment/api-endpoints")
async def get_api_endpoints(service: Optional[str] = None):
    """
    Get OpenAPI endpoints per service.
    Optionally filter by service name.
    """
    store = get_store()

    cypher = (
        "MATCH (s:Service)-[:EXPOSES_ENDPOINT]->(e:ApiEndpoint) "
        + (f"WHERE s.name = '{service}' " if service else "")
        + "RETURN s.name AS service, e.method AS method, "
        + "e.path AS path, e.operation_id AS operation_id "
        + "ORDER BY s.name, e.method, e.path"
    )
    rows = store.query(cypher)

    by_service: dict = {}
    for r in rows:
        svc = r["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append({
            "method": r["method"],
            "path": r["path"],
            "operation_id": r.get("operation_id") or "",
        })

    return {
        "by_service": by_service,
        "total_endpoints": len(rows),
    }


@router.get("/enrichment/env-vars")
async def get_env_vars(service: Optional[str] = None):
    """
    Get environment variables read by each service.
    Optionally filter by service name.
    """
    store = get_store()

    cypher = (
        "MATCH (s:Service)-[:READS_ENV]->(e:EnvVar) "
        + (f"WHERE s.name = '{service}' " if service else "")
        + "RETURN s.name AS service, e.name AS env_var "
        + "ORDER BY s.name, e.name"
    )
    rows = store.query(cypher)

    by_service: dict = {}
    for r in rows:
        svc = r["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append(r["env_var"])

    # Find vars shared across multiple services
    from collections import defaultdict
    var_to_services: dict = defaultdict(list)
    for r in rows:
        var_to_services[r["env_var"]].append(r["service"])

    shared = [
        {"env_var": var, "used_by": list(set(svcs))}
        for var, svcs in var_to_services.items()
        if len(set(svcs)) > 1
    ]

    return {
        "by_service": by_service,
        "shared_vars": sorted(shared, key=lambda x: x["env_var"]),
        "total_entries": len(rows),
    }
