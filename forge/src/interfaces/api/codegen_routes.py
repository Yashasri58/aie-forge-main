"""
Code Generation API Routes.

Endpoints for the code generation pipeline.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import json


# =============================================================================
# ROUTER
# =============================================================================

router = APIRouter(prefix="/codegen", tags=["codegen"])


# Module-level orchestrators (set by main.py)
_codegen_orchestrator = None
_pipeline_orchestrator = None


def set_codegen_orchestrator(orchestrator):
    """Set the codegen orchestrator instance."""
    global _codegen_orchestrator
    _codegen_orchestrator = orchestrator


def set_pipeline_orchestrator(orchestrator):
    """Set the pipeline orchestrator to look up approved reports."""
    global _pipeline_orchestrator
    _pipeline_orchestrator = orchestrator


# =============================================================================
# MODELS
# =============================================================================

class StartRequest(BaseModel):
    """Request to start code generation."""
    pipeline_id: str  # The approved pipeline ID


class RefineRequest(BaseModel):
    """Request to refine the plan."""
    feedback: str


class ApproveRequest(BaseModel):
    """Request to approve/reject."""
    approved: bool
    reason: Optional[str] = None


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/start")
async def start_codegen(request: StartRequest):
    """
    Start code generation from an approved pipeline.

    Returns immediately with the initial state (stage=pending).
    The full pipeline runs in a background task — poll GET /{state_id} for progress.
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")

    if not _pipeline_orchestrator:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    # Get the approved pipeline
    pipeline_state = _pipeline_orchestrator.get_state(request.pipeline_id)
    if not pipeline_state:
        raise HTTPException(status_code=404, detail=f"Pipeline {request.pipeline_id} not found")

    # Verify it's approved
    if pipeline_state.stage.value != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline not approved. Current stage: {pipeline_state.stage.value}"
        )

    # Return existing codegen state if already started for this pipeline
    existing = _codegen_orchestrator.get_state_by_pipeline(request.pipeline_id)
    if existing:
        return existing.to_dict()

    # Build impact report dict from pipeline state
    requirements_data = pipeline_state.requirements
    change_request = ""
    if requirements_data:
        if hasattr(requirements_data, 'description'):
            change_request = requirements_data.description
        elif isinstance(requirements_data, dict):
            change_request = requirements_data.get('description', '')

    impact_report = {
        "pipeline_id": request.pipeline_id,
        "change_request": change_request,
        "report": pipeline_state.report or "",
        "report_json": pipeline_state.report_json or {},
        "requirements": requirements_data if isinstance(requirements_data, dict) else (
            requirements_data.__dict__ if hasattr(requirements_data, '__dict__') else {}
        ),
    }

    # Create initial state synchronously so we can return it immediately
    from modules.codegen.schemas import CodeGenState as _CodeGenState
    import asyncio

    state = _CodeGenState.create(impact_report)
    _codegen_orchestrator._states[state.id] = state
    state.log(f"Starting code generation: {impact_report.get('change_request', '')[:100]}")

    # Fire the actual pipeline in the background
    async def _run():
        try:
            await _codegen_orchestrator._run_pipeline(state)
        except Exception as e:
            import traceback
            traceback.print_exc()
            from modules.codegen.schemas import CodeGenStage
            state.stage = CodeGenStage.FAILED
            state.error = str(e)
            state.log(f"Pipeline failed: {e}", "error")

    import asyncio
    asyncio.create_task(_run())

    return state.to_dict()


@router.get("/{state_id}/stream")
async def stream_codegen(state_id: str):
    """SSE stream of codegen progress. Closes when terminal stage is reached."""
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")

    TERMINAL = {"awaiting_approval", "approved", "rejected", "failed"}

    async def event_generator():
        sent_count = 0
        last_stage = None

        while True:
            state = _lookup_state(state_id)

            if not state:
                yield f"event: error\ndata: {json.dumps({'error': 'State not found'})}\n\n"
                return

            entries = state.activity_log or []
            for entry in entries[sent_count:]:
                yield f"data: {json.dumps(entry)}\n\n"
            sent_count = len(entries)

            current_stage = state.stage.value if hasattr(state.stage, "value") else str(state.stage)
            if current_stage != last_stage:
                last_stage = current_stage
                yield f"event: stage\ndata: {json.dumps({'stage': current_stage})}\n\n"

            if current_stage in TERMINAL:
                yield f"event: done\ndata: {json.dumps({'stage': current_stage, 'error': state.error})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{state_id}")
async def get_state(state_id: str):
    """
    Get the current state of code generation.
    
    Poll this endpoint to track progress.
    Can lookup by either state_id or pipeline_id.
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    # Try direct lookup first
    state = _codegen_orchestrator.get_state(state_id)
    
    # Fallback to pipeline_id lookup
    if not state:
        state = _codegen_orchestrator.get_state_by_pipeline(state_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    return state.to_dict()


def _lookup_state(state_id: str):
    """Helper to lookup state by either state_id or pipeline_id."""
    state = _codegen_orchestrator.get_state(state_id)
    if not state:
        state = _codegen_orchestrator.get_state_by_pipeline(state_id)
    return state


@router.get("/{state_id}/plan")
async def get_plan(state_id: str):
    """
    Get the generated plan.
    
    Returns the plan.json that will be executed.
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    state = _lookup_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    if not state.plan:
        raise HTTPException(status_code=404, detail="Plan not yet generated")
    
    return state.plan.to_dict()


@router.get("/{state_id}/diffs")
async def get_diffs(state_id: str):
    """
    Get all generated diffs.
    
    Returns list of diffs per file.
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    state = _lookup_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    # Return as array (matches frontend expectation)
    return [d.to_dict() for d in state.diffs]


@router.post("/{state_id}/approve")
async def approve_codegen(state_id: str, request: ApproveRequest):
    """
    Approve or reject the generated changes.
    
    Args:
        approved: True to approve, False to reject
        reason: Rejection reason (optional)
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    state = _lookup_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    # Use the actual state.id for the orchestrator call
    if request.approved:
        state = await _codegen_orchestrator.approve(state.id)
    else:
        state = await _codegen_orchestrator.reject(state.id, request.reason or "")
    
    return state.to_dict()


@router.post("/{state_id}/refine")
async def refine_plan(state_id: str, request: RefineRequest):
    """
    Refine the plan based on user feedback.
    
    This will:
    1. Update the plan based on feedback
    2. Re-run implementation
    3. Re-verify
    
    Args:
        feedback: User's feedback on what to change
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    state = _codegen_orchestrator.get_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    state = await _codegen_orchestrator.refine_plan(state_id, request.feedback)
    return state.to_dict()


@router.get("/{state_id}/result")
async def get_result(state_id: str):
    """
    Get the final result.
    
    Only available after approval/rejection/failure.
    """
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    result = _codegen_orchestrator.get_result(state_id)
    if not result:
        raise HTTPException(
            status_code=400, 
            detail="Result not available - code generation not complete"
        )
    
    return result.to_dict()


@router.delete("/{state_id}")
async def delete_state(state_id: str):
    """Delete a state to free resources."""
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")
    
    _codegen_orchestrator.delete_state(state_id)
    return {"status": "deleted"}


# =============================================================================
# VERSION HISTORY ENDPOINTS (apply-diffs-sync-graph feature)
# =============================================================================

import os as _os


def _sync_enabled() -> bool:
    return _os.getenv("SYNC_GRAPH_ON_APPROVE", "false").lower() in ("true", "1", "yes")


def _get_services_root():
    from pathlib import Path as _Path
    if not _codegen_orchestrator:
        return None
    return _Path(_codegen_orchestrator._services_path).parent


@router.get("/versions")
async def list_versions():
    if not _sync_enabled():
        raise HTTPException(status_code=503, detail="Version history unavailable — set SYNC_GRAPH_ON_APPROVE=true to enable")
    services_root = _get_services_root()
    if not services_root:
        raise HTTPException(503, "Code generation not initialized")
    from modules.codegen.version_manager import VersionManager
    vm = VersionManager(services_root)
    versions = vm.list_versions()
    return [{"commit_hash": v.commit_hash, "short_hash": v.short_hash, "message": v.message,
             "timestamp": v.timestamp, "state_id": v.state_id, "changed_files": v.changed_files}
            for v in versions]


@router.get("/versions/{commit_hash}/download")
async def download_version(commit_hash: str):
    if not _sync_enabled():
        raise HTTPException(status_code=503, detail="Version download unavailable — set SYNC_GRAPH_ON_APPROVE=true to enable")
    services_root = _get_services_root()
    if not services_root:
        raise HTTPException(503, "Code generation not initialized")
    from modules.codegen.version_manager import VersionManager
    from fastapi.responses import Response as _Response
    vm = VersionManager(services_root)
    try:
        zip_bytes = vm.download_version(commit_hash)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _Response(content=zip_bytes, media_type="application/zip",
                     headers={"Content-Disposition": f'attachment; filename="forge-{commit_hash[:8]}.zip"'})


@router.post("/{state_id}/revert")
async def revert_state(state_id: str):
    if not _sync_enabled():
        raise HTTPException(status_code=503, detail="Revert unavailable — set SYNC_GRAPH_ON_APPROVE=true to enable")
    state = _lookup_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    commit_hash = getattr(state, "git_commit_hash", None)
    if not commit_hash:
        raise HTTPException(status_code=404, detail="No git commit associated with this state")
    services_root = _get_services_root()
    from modules.codegen.version_manager import VersionManager
    vm = VersionManager(services_root)
    result = vm.revert_version(commit_hash)
    if not result.success:
        raise HTTPException(status_code=409, detail={"error": result.error, "conflict_details": result.conflict_details})
    rebuilder = getattr(_codegen_orchestrator, "_graph_rebuilder", None)
    if rebuilder:
        import asyncio
        asyncio.create_task(rebuilder.rebuild())
    return {"status": "reverted", "revert_commit": result.revert_commit_hash, "original_commit": commit_hash}
