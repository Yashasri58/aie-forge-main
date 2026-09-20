"""
Reverse Engineer API Routes.

Endpoints:
  POST /reverse-engineer/start           — upload log file, start pipeline
  GET  /reverse-engineer/{id}            — get session state (poll for progress)
  GET  /reverse-engineer/{id}/facts      — extracted facts (Stage 1+2 output)
  GET  /reverse-engineer/{id}/spec/{section}  — one spec section
  GET  /reverse-engineer/{id}/spec/all   — all sections as a dict
  GET  /reverse-engineer/{id}/spec/download  — zip of all markdown files

Follows the same pattern as codegen_routes.py — module-level dep injection,
set_re_orchestrator() called from main.py lifespan.
"""

import io
import zipfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/reverse-engineer", tags=["reverse-engineer"])

# Module-level orchestrator (set by main.py)
_re_orchestrator = None


def set_re_orchestrator(orchestrator) -> None:
    """Called from main.py lifespan after REOrchestrator is initialized."""
    global _re_orchestrator
    _re_orchestrator = orchestrator


def _get_orchestrator():
    if not _re_orchestrator:
        raise HTTPException(503, "Reverse Engineer pipeline not initialized")
    return _re_orchestrator


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_reverse_engineer(
    log_file: UploadFile = File(..., description="Log file to analyse"),
    user_comments: Optional[str] = Form(
        None,
        description="Optional context about the application (e.g. 'This is a payment system', 'service X is the API gateway')"
    ),
):
    """
    Start a new Reverse Engineer pipeline run.

    Upload a structured log file (`.log`, `.txt`, `.jsonl`).
    Optionally provide plain-text context about the application.

    Returns immediately with a session ID.
    Poll GET /reverse-engineer/{id} for progress.
    """
    orch = _get_orchestrator()

    # Read file bytes
    try:
        log_bytes = await log_file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read log file: {e}")

    if len(log_bytes) == 0:
        raise HTTPException(400, "Log file is empty")

    file_name = log_file.filename or "log.txt"

    try:
        session = await orch.start(
            log_bytes=log_bytes,
            file_name=file_name,
            user_comments=user_comments or "",
        )
        return session.to_dict()
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{session_id}")
async def get_session(session_id: str):
    """
    Get current pipeline state.

    Poll this every 2–3 seconds to track progress.
    The `stage` field transitions through:
      uploading → parsing → extracting → inferring → gap_review → writing → complete

    The `activity_log` field streams all pipeline events.
    """
    orch = _get_orchestrator()
    session = orch.get_state(session_id)

    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    return session.to_dict()


@router.get("/{session_id}/facts")
async def get_extracted_facts(session_id: str):
    """
    Get the extracted facts from Stage 1 (log parsing) and Stage 2 (templates).

    Available after stage: `extracting` completes.
    Contains: services, endpoints, trace flows, Kafka topics, resilience patterns, etc.
    """
    orch = _get_orchestrator()
    session = orch.get_state(session_id)

    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if not session.extracted_facts:
        raise HTTPException(400, f"Facts not yet available. Stage: {session.stage.value}")

    return session.extracted_facts


@router.get("/{session_id}/spec/all")
async def get_all_spec_sections(session_id: str):
    """
    Get all generated spec sections as a dict.

    Available after stage: `complete`.
    Returns: { section_id: { title, content_md, confidence_score, gap_count } }
    """
    orch = _get_orchestrator()
    session = orch.get_state(session_id)

    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if not session.spec_sections:
        raise HTTPException(400, f"Spec not yet available. Stage: {session.stage.value}")

    return {sid: s.to_dict() for sid, s in session.spec_sections.items()}


@router.get("/{session_id}/spec/download")
async def download_spec_zip(session_id: str):
    """
    Download all spec sections as a ZIP of Markdown files.

    Available after stage: `complete`.
    """
    orch = _get_orchestrator()
    session = orch.get_state(session_id)

    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if not session.spec_sections:
        raise HTTPException(400, f"Spec not yet available. Stage: {session.stage.value}")

    # Build ZIP in memory
    buf = io.BytesIO()
    section_filenames = {
        "executive_summary": "00_executive_summary.md",
        "service_inventory": "01_service_inventory.md",
        "api_catalog": "02_api_catalog.md",
        "business_logic": "03_business_logic.md",
        "event_topology": "04_event_topology.md",
        "data_model": "05_data_model.md",
        "cross_cutting": "06_cross_cutting.md",
        "slos_and_observability": "07_slos_and_observability.md",
        "resilience_patterns": "08_resilience_patterns.md",
        "tech_stack": "09_tech_stack.md",
        "risks_and_gaps": "10_risks_and_gaps.md",
        "confidence_report": "11_confidence_report.md",
    }

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sid, section in session.spec_sections.items():
            filename = section_filenames.get(sid, f"{sid}.md")
            header = f"# {section.title}\n\n"
            meta = (
                f"*Confidence: {section.confidence_score:.0%} | "
                f"Gaps: {section.gap_count}*\n\n---\n\n"
            )
            zf.writestr(filename, (header + meta + section.content_md).encode("utf-8"))

    buf.seek(0)
    zip_name = f"spec_{session.log_file_name.replace('.log', '').replace('.txt', '')}_{session_id[:8]}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"},
    )


@router.get("/{session_id}/spec/{section_id}")
async def get_spec_section(session_id: str, section_id: str):
    """
    Get a single spec section.

    section_id must be one of:
      executive_summary | service_inventory | api_catalog | business_logic |
      event_topology | data_model | cross_cutting | slos_and_observability |
      resilience_patterns | tech_stack | risks_and_gaps | confidence_report

    Available after stage: `writing` starts writing this section.
    """
    orch = _get_orchestrator()
    section = orch.get_spec_section(session_id, section_id)

    if section is None:
        session = orch.get_state(session_id)
        if not session:
            raise HTTPException(404, f"Session {session_id} not found")
        raise HTTPException(
            404,
            f"Section '{section_id}' not yet available. Stage: {session.stage.value}"
        )

    return section.to_dict()
