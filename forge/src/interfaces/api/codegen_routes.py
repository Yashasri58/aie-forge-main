"""
Code Generation API Routes.

Endpoints for the code generation pipeline.
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional


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
    
    Fetches the impact report from the pipeline and starts code generation.
    
    Returns:
        CodeGenState with ID to track progress
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
    
    # Build impact report dict from pipeline state
    # Extract the description from requirements (which is a RequirementsOutput object)
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
    
    try:
        state = await _codegen_orchestrator.start(impact_report)
        return state.to_dict()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/{state_id}/stream")
async def stream_codegen(state_id: str):
    """SSE stream of codegen progress. Closes when terminal stage is reached."""
    if not _codegen_orchestrator:
        raise HTTPException(status_code=503, detail="Code generation not initialized")

    TERMINAL = {"complete", "failed", "approved", "rejected"}

    async def event_generator():
        sent_count = 0
        last_stage = None

        while True:
            state = _codegen_orchestrator.get_state(state_id)
            if not state:
                state = _codegen_orchestrator.get_state_by_pipeline(state_id)

            if not state:
                yield f"event: error\ndata: {json.dumps({'error': 'State not found'})}\n\n"
                return

            entries = state.activity_log if hasattr(state, "activity_log") else []
            for entry in (entries or [])[sent_count:]:
                yield f"data: {json.dumps(entry)}\n\n"
            sent_count = len(entries or [])

            current_stage = state.stage.value if hasattr(state.stage, "value") else str(state.stage)
            if current_stage != last_stage:
                last_stage = current_stage
                yield f"event: stage\ndata: {json.dumps({'stage': current_stage})}\n\n"

            if current_stage in TERMINAL:
                yield f"event: done\ndata: {json.dumps({'stage': current_stage})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
