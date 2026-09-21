"""
Forge API Server.

FastAPI application for code impact analysis.

Usage:
    python main.py
"""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

# Import routers
from interfaces.api.routes import (
    health_router,
    impact_router,
    graph_router,
    pipeline_router,
    codegen_router,
    re_router,
    set_health_deps,
    set_impact_deps,
    set_graph_store,
    set_pipeline_orchestrator,
    set_codegen_orchestrator,
    set_codegen_pipeline_orchestrator,
    set_re_orchestrator,
)
from interfaces.api.cache_routes import router as cache_router, set_cache
from modules.cache.demo_cache import get_cache


# =============================================================================
# GLOBALS
# =============================================================================

_store = None
_agent = None
_tools = None
_orchestrator = None
_codegen_orchestrator = None
_re_orchestrator = None


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global _store, _agent, _tools, _orchestrator, _codegen_orchestrator, _re_orchestrator
    
    # Find services directory
    services_path = Path(__file__).parent / ".." / "services"
    if not services_path.exists():
        services_path = Path(__file__).parent / "services"
    
    # Check for codegraph-tools extraction file
    extraction_path = services_path / "codegraph-out" / "combined_extraction.json"
    
    # Kuzu database path
    kuzu_db_path = services_path / "codegraph-out" / "code_graph.kuzu"
    
    if not extraction_path.exists():
        print(f"Extraction file not found at {extraction_path}")
        print("Running indexer to generate extraction...")
        try:
            from modules.codegraph.indexer import CodeGraphIndexer
            indexer = CodeGraphIndexer(str(services_path))
            indexer.index_all()
            print(f"Indexing complete. Extraction saved to {extraction_path}")
        except Exception as idx_err:
            print(f"ERROR: Indexing failed: {idx_err}")
            print("Please ensure codegraph-tools is installed: pip install codegraph-tools")
    
    # Now load the extraction (whether it existed or was just created)
    if extraction_path.exists():
        print(f"Loading codegraph from: {extraction_path}")
        print(f"Kuzu DB path: {kuzu_db_path}")
        
        try:
            from modules.codegraph.kuzu_store import KuzuCodeGraphStore
            from modules.codegraph.tools import CodeGraphTools
            
            # Initialize Kuzu store
            _store = KuzuCodeGraphStore(str(kuzu_db_path))
            _store.init_schema()
            
            # Load extraction into Kuzu if empty
            if _store.get_symbol_count() == 0:
                print("Loading extraction into Kuzu...")
                
                # Also run HTTP linker to detect service-to-service HTTP calls
                http_data = None
                try:
                    from modules.codegraph.http_linker import HttpLinker
                    print("Running HTTP linker to detect service connections...")
                    linker = HttpLinker(str(services_path))
                    
                    # Extract routes and calls
                    routes = linker.extract_all_routes()
                    edges = linker.link_services()
                    
                    # Convert to http_data format expected by load_extraction
                    http_data = {
                        "routes": [
                            {
                                "service": r.service,
                                "method": r.method,
                                "path": r.path,
                                "handler": r.handler,
                            }
                            for r in routes
                        ],
                        "calls": [
                            {
                                "from_service": e.source,
                                "to_service": e.target,
                                "method": e.method,
                                "path": e.route,
                            }
                            for e in edges
                        ],
                    }
                    print(f"HTTP linker found: {len(routes)} routes, {len(edges)} service connections")
                except Exception as http_err:
                    print(f"WARNING: HTTP linker failed: {http_err}")
                
                _store.load_extraction(str(extraction_path), http_data=http_data)
            else:
                print(f"Kuzu DB already populated: {_store.get_symbol_count()} symbols")
            
            # Run enrichment (package deps, DB schemas, OpenAPI, env vars)
            # Always re-run so the enrichment tables stay current even if
            # the symbol tables were already populated from a previous run.
            try:
                from modules.codegraph.enricher import CodeGraphEnricher
                enricher = CodeGraphEnricher(str(services_path))
                enrichment = enricher.extract_all()
                _store.load_enrichment(enrichment)
            except Exception as enrich_err:
                print(f"WARNING: Enrichment failed (non-fatal): {enrich_err}")
            
            # Initialize tools with the store
            _tools = CodeGraphTools(
                kuzu_store=_store,
                services_path=str(services_path)
            )
            
            print(f"CodeGraph ready: {len(_tools.services)} services, {len(_tools.all_symbols)} symbols")
            
            # Initialize agent and pipeline if Google API key available
            if os.getenv("GOOGLE_API_KEY"):
                try:
                    from modules.agents.impact import ImpactAgent
                    from modules.agents import PipelineOrchestrator
                    
                    _agent = ImpactAgent(_store, _tools)
                    _orchestrator = PipelineOrchestrator(_agent)
                    print(f"Agent & Pipeline ready")
                    
                    # Initialize code generation orchestrator
                    if services_path.exists():
                        from modules.codegen import CodeGenOrchestrator
                        _codegen_orchestrator = CodeGenOrchestrator(_store, str(services_path))
                        print(f"Code Generation ready: {services_path}")
                except Exception as agent_err:
                    print(f"WARNING: Could not initialize agents: {agent_err}")
            else:
                print(f"Tools ready (no GOOGLE_API_KEY - LLM disabled)")
                
        except Exception as e:
            print(f"ERROR: Failed to load codegraph: {e}")
            import traceback
            traceback.print_exc()
        
        # Set dependencies for routers
        set_health_deps(_store, _agent, _tools)
        set_impact_deps(_agent, _tools)
        set_graph_store(_store)
        if _orchestrator:
            set_pipeline_orchestrator(_orchestrator)
        if _codegen_orchestrator:
            set_codegen_orchestrator(_codegen_orchestrator)
            # Give codegen routes access to pipeline state
            if _orchestrator:
                set_codegen_pipeline_orchestrator(_orchestrator)
    
    # Initialize Reverse Engineer pipeline (always available — no graph store needed)
    try:
        from modules.reverse_engineer import REOrchestrator
        _re_orchestrator = REOrchestrator()
        set_re_orchestrator(_re_orchestrator)
        print(f"Reverse Engineer Pipeline ready")
    except Exception as re_err:
        print(f"WARNING: Could not initialize Reverse Engineer pipeline: {re_err}")
    
    # Demo cache
    try:
        _demo_cache = get_cache()
        set_cache(_demo_cache)
        stats = _demo_cache.stats()
        print(f"Demo cache ready — {stats['total']} entries ({stats['by_type']})")
    except Exception as cache_err:
        print(f"WARNING: Could not initialize demo cache: {cache_err}")
    
    yield
    
    # Cleanup
    if _store:
        _store.close()
        print("Graph store closed")


# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="Forge Impact Analysis API",
    description="Analyze code dependencies and answer 'what breaks if I change X?'",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# STATIC FILES - Mount BEFORE API routers
# =============================================================================

frontend_dir = Path(__file__).parent / "frontend" / "dist"
if not frontend_dir.exists():
    frontend_dir = Path(__file__).parent / "frontend"

_has_frontend = frontend_dir.exists() and (frontend_dir / "index.html").exists()

if _has_frontend:
    # Mount entire dist folder at /static - this serves /static/assets/* correctly
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# =============================================================================
# API ROUTERS
# =============================================================================

app.include_router(health_router)
app.include_router(impact_router)
app.include_router(graph_router)
app.include_router(pipeline_router)
app.include_router(codegen_router)
app.include_router(re_router)
app.include_router(cache_router)


# =============================================================================
# SPA FALLBACK
# =============================================================================

# For SPA routing: serve index.html for the root and let the frontend router handle paths.
# Static files at /static/* are handled by the mount above.
# API routes (/health, /impact, /graph, /pipeline) are handled by their routers.
# Unknown API-style paths will 404 naturally.

if _has_frontend:
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(frontend_dir / "index.html"))
    
    # SPA catch-all: serve index.html for frontend routes (but not /static/*)
    # This must NOT match /static/* - those go to the mount
    @app.api_route("/{path:path}", methods=["GET"], include_in_schema=False)
    async def serve_spa(path: str):
        from fastapi import Request
        from starlette.responses import Response
        
        # Let /static/* fall through to mount by returning 404
        # (FastAPI will then try the mount)
        if path.startswith("static/"):
            # Serve directly from the mount path
            file_path = frontend_dir / path.replace("static/", "", 1)
            if file_path.exists() and file_path.is_file():
                import mimetypes
                mime_type, _ = mimetypes.guess_type(str(file_path))
                return FileResponse(str(file_path), media_type=mime_type)
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Static file not found")
        
        # Don't serve index.html for API paths - let them 404
        api_prefixes = ("health", "impact", "graph", "pipeline/", "codegen/", "reverse-engineer/", "api", "docs", "openapi", "redoc")
        
        if path.startswith(api_prefixes):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        
        # SPA fallback - serve index.html for client-side routing
        return FileResponse(str(frontend_dir / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return {"message": "Frontend not built. Run: cd frontend && npm run build"}


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)



# =============================================================================
# ENTRY POINT
# =============================================================================
# Run directly:  python main.py
# Configure via .env:  PORT=8000  HOST=0.0.0.0  LOG_LEVEL=info

if __name__ == "__main__":
    import uvicorn

    host      = os.getenv("HOST", "0.0.0.0")
    port      = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info")

    print(f"Starting Forge on http://{host}:{port}  (log_level={log_level})")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,          # set LOG_LEVEL=debug and RELOAD=true for dev
    )
