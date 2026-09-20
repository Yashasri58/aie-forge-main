"""
Pipeline API Router

Endpoints for the impact analysis pipeline.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


# =============================================================================
# MODELS
# =============================================================================

class StartRequest(BaseModel):
    """Start a new pipeline."""
    message: str = Field(..., description="Initial requirements")


class RespondRequest(BaseModel):
    """Respond to context gatherer."""
    message: str = Field(..., description="User's response")


class ApprovalRequest(BaseModel):
    """Approve or reject."""
    approved: bool
    reason: Optional[str] = None


# =============================================================================
# DEPENDENCY
# =============================================================================

_orchestrator = None


def set_orchestrator(orchestrator):
    """Set the orchestrator instance."""
    global _orchestrator
    _orchestrator = orchestrator


def get_orchestrator():
    if not _orchestrator:
        raise HTTPException(503, "Pipeline not available")
    return _orchestrator


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/start")
async def start_pipeline(request: StartRequest):
    """
    Start impact analysis pipeline.
    
    If requirements are vague, returns questions to clarify.
    If clear, runs analysis and returns the full layered report.
    """
    orch = get_orchestrator()
    
    try:
        state = await orch.start(request.message)
        return state.to_dict()
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{pipeline_id}/respond")
async def respond(pipeline_id: str, request: RespondRequest):
    """
    Answer the context gatherer's question.
    
    Once requirements are clear, stage becomes "requirements_ready".
    User must then call /confirm to proceed with analysis.
    """
    orch = get_orchestrator()
    
    try:
        state = await orch.respond(pipeline_id, request.message)
        return state.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{pipeline_id}/confirm")
async def confirm_requirements(pipeline_id: str):
    """
    Confirm requirements and start impact analysis.
    
    Call this when stage is "requirements_ready" to proceed.
    Analysis (ImpactAgent + VerificationAgent loop) runs after confirmation.
    """
    orch = get_orchestrator()
    
    try:
        state = await orch.confirm_requirements(pipeline_id)
        return state.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{pipeline_id}")
async def get_status(pipeline_id: str):
    """Get current pipeline state."""
    orch = get_orchestrator()
    
    state = orch.get_state(pipeline_id)
    if not state:
        raise HTTPException(404, f"Pipeline {pipeline_id} not found")
    
    return state.to_dict()


@router.get("/{pipeline_id}/report", response_class=PlainTextResponse)
async def get_report(pipeline_id: str):
    """
    Get the full layered impact report as plain text.
    
    Returns the human-readable report with:
    - Layer 0, 1, 2 impacts
    - File changes with WHY and CHANGE
    - Execution order
    - Summary
    """
    orch = get_orchestrator()
    
    state = orch.get_state(pipeline_id)
    if not state:
        raise HTTPException(404, f"Pipeline {pipeline_id} not found")
    
    if not state.report:
        raise HTTPException(400, f"Analysis not complete. Stage: {state.stage.value}")
    
    return PlainTextResponse(content=state.report, media_type="text/plain")


@router.get("/{pipeline_id}/report/json")
async def get_report_json(pipeline_id: str):
    """Get the structured JSON version of the report."""
    orch = get_orchestrator()
    
    state = orch.get_state(pipeline_id)
    if not state:
        raise HTTPException(404, f"Pipeline {pipeline_id} not found")
    
    if not state.report_json:
        raise HTTPException(400, f"Analysis not complete. Stage: {state.stage.value}")
    
    return state.report_json


@router.post("/{pipeline_id}/approve")
async def approve(pipeline_id: str, request: ApprovalRequest):
    """Approve or reject the analysis."""
    orch = get_orchestrator()
    
    try:
        if request.approved:
            state = await orch.approve(pipeline_id)
        else:
            state = await orch.reject(pipeline_id, request.reason or "")
        return state.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/{pipeline_id}")
async def delete(pipeline_id: str):
    """Delete a pipeline."""
    orch = get_orchestrator()
    orch.delete_state(pipeline_id)
    return {"deleted": pipeline_id}
