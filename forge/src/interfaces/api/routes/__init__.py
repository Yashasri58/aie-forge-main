"""
API Routes.

All API endpoints organized by feature:
- health: Health checks and service listing
- impact: Impact analysis and code graph queries
- graph_explorer: Interactive graph visualization
- pipeline: Multi-agent impact analysis pipeline
- codegen: Code generation from approved impact reports
- reverse_engineer: Reverse engineering pipeline from log files (Pipeline 3)
"""

from .health import router as health_router, set_dependencies as set_health_deps
from .impact import router as impact_router, set_dependencies as set_impact_deps
from .graph_explorer import router as graph_router, set_store as set_graph_store
from .pipeline import router as pipeline_router, set_orchestrator as set_pipeline_orchestrator

# Import codegen routes from parent package
from ..codegen_routes import (
    router as codegen_router,
    set_codegen_orchestrator,
    set_pipeline_orchestrator as set_codegen_pipeline_orchestrator,
)

# Import reverse engineer routes from parent package
from ..re_routes import (
    router as re_router,
    set_re_orchestrator,
)

__all__ = [
    "health_router",
    "impact_router",
    "graph_router",
    "pipeline_router",
    "codegen_router",
    "re_router",
    "set_health_deps",
    "set_impact_deps",
    "set_graph_store",
    "set_pipeline_orchestrator",
    "set_codegen_orchestrator",
    "set_codegen_pipeline_orchestrator",
    "set_re_orchestrator",
]
