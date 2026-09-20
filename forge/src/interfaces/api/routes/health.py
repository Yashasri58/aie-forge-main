"""
Health & Status API Router.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


# =============================================================================
# DEPENDENCIES (set by main.py)
# =============================================================================

_store = None
_agent = None
_tools = None


def set_dependencies(store, agent, tools):
    """Set dependencies for health checks."""
    global _store, _agent, _tools
    _store = store
    _agent = agent
    _tools = tools


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "graph_loaded": _store is not None,
        "agent_ready": _agent is not None,
        "services": _tools.services if _tools else [],
        "symbol_count": len(_tools.all_symbols) if _tools else 0
    }


@router.get("/services")
async def list_services():
    """List all indexed services."""
    if not _tools:
        return {"services": [], "count": 0, "status": "graph not loaded"}
    
    return {
        "services": _tools.services,
        "count": len(_tools.services)
    }
