"""
Reverse Engineer Pipeline Orchestrator.

Manages the RESession state machine through 6 stages:
  UPLOADING → PARSING → EXTRACTING → INFERRING → GAP_REVIEW → WRITING → COMPLETE

Follows the same pattern as src/modules/agents/orchestrator.py:
  - In-memory dict of sessions (keyed by session_id)
  - SQLite persistence after each stage (survives server restarts)
  - Structured activity log on every state change
  - Harness integration at each stage boundary

Public API:
  start(log_bytes, file_name, user_comments) → RESession
  get_state(session_id) → RESession | None
  get_spec_section(session_id, section_id) → SpecSection | None
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .logging_config import (
    orchestrator_logger,
    log_stage_start,
    log_stage_complete,
    log_stage_error,
)
from .schemas import RESession, REStage, SpecSection
from .harness import sanitize_user_comments, re_policy_gate

# Demo cache — lazy import
try:
    from modules.cache.demo_cache import get_cache as _get_demo_cache
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False


# ─── SQLite persistence (mirrors orchestrator.py pattern) ────────────────────

_DB_PATH = Path(__file__).parent.parent.parent.parent.parent / "forge_re_sessions.db"


def _init_db() -> None:
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS re_sessions (
                id TEXT PRIMARY KEY,
                stage TEXT,
                created_at REAL,
                updated_at REAL,
                state_json TEXT
            )
        """)


def _save_session(session: RESession) -> None:
    try:
        _init_db()
        state_dict = session.to_dict()
        # SpecSection objects need special handling
        state_dict["spec_sections"] = {
            k: v.to_dict() for k, v in session.spec_sections.items()
        }
        state_json = json.dumps(state_dict, default=str)
        stage_val = session.stage.value
        session_id = session.id
        created_at = session.created_at

        def _write():
            with sqlite3.connect(str(_DB_PATH)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO re_sessions
                        (id, stage, created_at, updated_at, state_json)
                    VALUES (?, ?, COALESCE(
                        (SELECT created_at FROM re_sessions WHERE id=?), ?
                    ), ?, ?)
                """, (
                    session_id, stage_val, session_id,
                    created_at, time.time(),
                    state_json,
                ))

        # Fire-and-forget in a thread so we don't block the event loop
        import threading
        threading.Thread(target=_write, daemon=True).start()
    except Exception as e:
        orchestrator_logger.warning(f"[HARNESS] Session save failed (non-fatal): {e}")


def _load_session_from_db(session_id: str) -> Optional[RESession]:
    try:
        _init_db()
        with sqlite3.connect(str(_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT state_json FROM re_sessions WHERE id=?", (session_id,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        session = RESession(
            id=data["id"],
            stage=REStage(data["stage"]),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            log_file_name=data.get("log_file_name", ""),
            log_file_path=data.get("log_file_path", ""),
            user_comments=data.get("user_comments"),
            extracted_facts=data.get("extracted_facts"),
            asg=data.get("asg"),
            current_stage_detail=data.get("current_stage_detail", ""),
            activity_log=data.get("activity_log", []),
            error=data.get("error"),
            tool_receipts=data.get("tool_receipts", []),
        )
        # Restore spec sections
        raw_sections = data.get("spec_sections", {})
        for sid, sdata in raw_sections.items():
            session.spec_sections[sid] = SpecSection(
                section_id=sdata["section_id"],
                title=sdata["title"],
                content_md=sdata["content_md"],
                confidence_score=sdata["confidence_score"],
                gap_count=sdata["gap_count"],
                generated_at=sdata["generated_at"],
            )
        return session
    except Exception as e:
        orchestrator_logger.warning(f"[HARNESS] Session load failed: {e}")
        return None


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class REOrchestrator:
    """
    Coordinates the 5-stage Reverse Engineer pipeline.

    Each stage is run asynchronously so the API can return immediately
    and the client polls for progress.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, RESession] = {}
        # Output directory for spec files
        self._output_dir = Path(__file__).parent.parent.parent.parent.parent / "reverse-engineer" / "output"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        orchestrator_logger.info(f"REOrchestrator ready — output: {self._output_dir}")

    # ─── Public API ───────────────────────────────────────────────────────────

    async def start(
        self,
        log_bytes: bytes,
        file_name: str,
        user_comments: str = "",
    ) -> RESession:
        """
        Start a new RE pipeline run.

        Args:
            log_bytes:     Raw bytes of the uploaded log file
            file_name:     Original filename
            user_comments: Optional user context about the application

        Returns:
            RESession (stage=UPLOADING initially, then pipeline runs async)
        """
        session = RESession(
            id=str(uuid.uuid4()),
            stage=REStage.UPLOADING,
            log_file_name=file_name,
            user_comments=user_comments,
        )

        # Sanitize user comments (prompt injection guard)
        if user_comments:
            sanitized, was_modified = sanitize_user_comments(user_comments)
            if was_modified:
                session.add_activity(
                    "User comments sanitized (injection attempt detected)",
                    level="warning",
                    event_type="injection_blocked",
                )
            session.user_comments = sanitized

        # Validate file
        allowed, err_msg = re_policy_gate("read_log", file_name)
        if not allowed:
            session.stage = REStage.FAILED
            session.error = err_msg
            session.add_activity(f"File rejected: {err_msg}", level="error", event_type="harness_check")
            self._sessions[session.id] = session
            _save_session(session)
            return session

        # Save log file to temp location
        suffix = Path(file_name).suffix or ".log"
        tmp_dir = Path(tempfile.mkdtemp())
        log_path = tmp_dir / f"{session.id}{suffix}"
        log_path.write_bytes(log_bytes)
        session.log_file_path = str(log_path)

        session.add_activity(
            f"Log file received: {file_name} ({len(log_bytes):,} bytes)",
            event_type="stage_change",
            metadata={"file_name": file_name, "bytes": len(log_bytes)},
        )

        self._sessions[session.id] = session
        _save_session(session)

        # Transition to PARSING immediately before firing background task
        # so the first poll sees PARSING (not UPLOADING) since stage 1+2 complete in <100ms
        session.stage = REStage.PARSING
        session.current_stage_detail = "Parsing log file…"
        session.add_activity("Stage 1: Parsing log file", event_type="stage_change")
        _save_session(session)

        # Fire pipeline in background
        asyncio.create_task(self._run_pipeline(session.id))

        return session

    def get_state(self, session_id: str) -> Optional[RESession]:
        """Get current session state (in-memory first, then DB)."""
        session = self._sessions.get(session_id)
        if not session:
            session = _load_session_from_db(session_id)
            if session:
                self._sessions[session_id] = session
        return session

    def get_spec_section(self, session_id: str, section_id: str) -> Optional[SpecSection]:
        """Get a specific spec section."""
        session = self.get_state(session_id)
        if not session:
            return None
        return session.spec_sections.get(section_id)

    def get_all_spec_content(self, session_id: str) -> Dict[str, str]:
        """Get all spec sections as a dict of section_id → markdown string."""
        session = self.get_state(session_id)
        if not session:
            return {}
        return {sid: s.content_md for sid, s in session.spec_sections.items()}

    # ─── Pipeline runner ──────────────────────────────────────────────────────

    async def _run_pipeline(self, session_id: str) -> None:
        """
        Run all 5 stages in sequence.
        Each stage updates session state and persists to DB.
        """
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            # Stage 1: Parse
            await self._stage_parse(session)
            if session.stage == REStage.FAILED:
                return

            # Stage 2: Extract templates
            await self._stage_extract(session)
            if session.stage == REStage.FAILED:
                return

            # Stage 3: Infer
            await self._stage_infer(session)
            if session.stage == REStage.FAILED:
                return

            # Stage 4: Gap review
            await self._stage_gap_review(session)
            if session.stage == REStage.FAILED:
                return

            # Stage 5: Write spec
            await self._stage_write_spec(session)

        except Exception as e:
            orchestrator_logger.exception(f"Pipeline failed for {session_id}: {e}")
            session.stage = REStage.FAILED
            session.error = str(e)
            session.add_activity(f"Pipeline error: {e}", level="error", event_type="stage_change")
            _save_session(session)

    # ─── Stage implementations ────────────────────────────────────────────────

    async def _stage_parse(self, session: RESession) -> None:
        # Stage already set to PARSING in start() to avoid UPLOADING showing in UI
        session.stage = REStage.PARSING
        session.current_stage_detail = "Parsing log file…"
        # Only add activity if not already added by start()
        if not any(a.get("message", "").startswith("Stage 1:") for a in session.activity_log):
            session.add_activity("Stage 1: Parsing log file", event_type="stage_change")
        _save_session(session)

        log_stage_start(orchestrator_logger, "ORCHESTRATOR:PARSING", session.log_file_name)

        try:
            from .log_parser import LogParser
            parser = LogParser()
            loop = asyncio.get_event_loop()
            facts = await loop.run_in_executor(
                None, parser.parse_file, session.log_file_path, session.id
            )

            session.extracted_facts = dataclasses.asdict(facts)
            session.add_activity(
                f"Log parsed: {facts.service_count} services, "
                f"{facts.endpoint_count} endpoints, "
                f"{facts.trace_count} traces",
                event_type="stage_change",
                metadata={
                    "services": facts.service_count,
                    "endpoints": facts.endpoint_count,
                    "traces": facts.trace_count,
                },
            )
            log_stage_complete(orchestrator_logger, "ORCHESTRATOR:PARSING")

        except Exception as e:
            log_stage_error(orchestrator_logger, "ORCHESTRATOR:PARSING", str(e))
            session.stage = REStage.FAILED
            session.error = f"Parsing failed: {e}"
            session.add_activity(f"Parsing error: {e}", level="error")

        _save_session(session)

    async def _stage_extract(self, session: RESession) -> None:
        session.stage = REStage.EXTRACTING
        session.current_stage_detail = "Extracting log templates (Drain3)…"
        session.add_activity("Stage 2: Extracting log templates", event_type="stage_change")
        _save_session(session)

        log_stage_start(orchestrator_logger, "ORCHESTRATOR:EXTRACTING")

        try:
            from .schemas import ExtractedFacts
            from .template_extractor import extract_templates

            # Restore ExtractedFacts from dict
            facts = _dict_to_extracted_facts(session.extracted_facts, session.id)
            loop = asyncio.get_event_loop()
            facts = await loop.run_in_executor(
                None, extract_templates, session.log_file_path, facts
            )

            session.extracted_facts = dataclasses.asdict(facts)
            template_count = len(facts.log_templates)
            session.add_activity(
                f"Templates extracted: {template_count} unique patterns",
                event_type="stage_change",
                metadata={"template_count": template_count},
            )
            log_stage_complete(orchestrator_logger, "ORCHESTRATOR:EXTRACTING")

        except Exception as e:
            log_stage_error(orchestrator_logger, "ORCHESTRATOR:EXTRACTING", str(e))
            # Non-fatal — continue without templates
            session.add_activity(
                f"Template extraction failed (non-fatal): {e}",
                level="warning",
            )

        _save_session(session)

    async def _stage_infer(self, session: RESession) -> None:
        session.stage = REStage.INFERRING
        session.current_stage_detail = "Inferring architecture (Gemini 2.5 Pro)…"
        session.add_activity("Stage 3: AI inference (Gemini 2.5 Pro)", event_type="stage_change")
        _save_session(session)

        log_stage_start(orchestrator_logger, "ORCHESTRATOR:INFERRING")

        try:
            from .inference_agent import InferenceAgent
            agent = InferenceAgent()
            facts = _dict_to_extracted_facts(session.extracted_facts, session.id)
            asg = await agent.run(
                facts=facts,
                user_comments=session.user_comments or "",
                session_id=session.id,
            )

            session.asg = dataclasses.asdict(asg)
            session.tool_receipts = agent._receipts.get()
            session.add_activity(
                f"ASG produced: {asg.confirmed_count} CONFIRMED, "
                f"{asg.inferred_count} INFERRED, {asg.gap_count} GAP",
                event_type="stage_change",
                metadata={
                    "confirmed": asg.confirmed_count,
                    "inferred": asg.inferred_count,
                    "gaps": asg.gap_count,
                },
            )
            log_stage_complete(orchestrator_logger, "ORCHESTRATOR:INFERRING")

        except Exception as e:
            log_stage_error(orchestrator_logger, "ORCHESTRATOR:INFERRING", str(e))
            session.stage = REStage.FAILED
            session.error = f"Inference failed: {e}"
            session.add_activity(f"Inference error: {e}", level="error")

        _save_session(session)

    async def _stage_gap_review(self, session: RESession) -> None:
        session.stage = REStage.GAP_REVIEW
        session.current_stage_detail = "Gap review (Gemini 2.5 Flash)…"
        session.add_activity("Stage 4: Gap review (Gemini 2.5 Flash)", event_type="stage_change")
        _save_session(session)

        log_stage_start(orchestrator_logger, "ORCHESTRATOR:GAP_REVIEW")

        try:
            from .gap_agent import GapAgent
            from .schemas import ApplicationSpecGraph

            agent = GapAgent()
            asg = _dict_to_asg(session.asg, session.id)
            facts = _dict_to_extracted_facts(session.extracted_facts, session.id)

            gap_result = await agent.run(asg=asg, facts=facts)

            # Attach gap_review to ASG dict for later stages
            if session.asg:
                session.asg["_gap_review"] = gap_result

            summary = gap_result.get("confidence_summary", {})
            gap_count = len(gap_result.get("gaps", []))
            session.add_activity(
                f"Gap review: {gap_count} gaps, "
                f"confidence={summary.get('overall_confidence', 'MEDIUM')}",
                event_type="stage_change",
                metadata={"gaps": gap_count, "summary": summary},
            )
            log_stage_complete(orchestrator_logger, "ORCHESTRATOR:GAP_REVIEW")

        except Exception as e:
            log_stage_error(orchestrator_logger, "ORCHESTRATOR:GAP_REVIEW", str(e))
            # Non-fatal — continue without gap review
            session.add_activity(
                f"Gap review failed (non-fatal): {e}",
                level="warning",
            )

        _save_session(session)

    async def _stage_write_spec(self, session: RESession) -> None:
        session.stage = REStage.WRITING
        session.current_stage_detail = "Generating spec sections (Gemini 2.5 Flash)…"
        session.add_activity("Stage 5: Writing spec (Gemini 2.5 Flash)", event_type="stage_change")
        _save_session(session)

        log_stage_start(orchestrator_logger, "ORCHESTRATOR:WRITING")

        try:
            from .spec_writer_agent import SpecWriterAgent

            agent = SpecWriterAgent()
            asg = _dict_to_asg(session.asg, session.id)
            gap_review = (session.asg or {}).get("_gap_review", {})
            facts = _dict_to_extracted_facts(session.extracted_facts, session.id)

            def _on_section(section_id: str, section: SpecSection) -> None:
                """Callback: update session as each section is written."""
                session.spec_sections[section_id] = section
                session.current_stage_detail = f"Wrote: {section.title}"
                session.add_activity(
                    f"Section written: {section.title} "
                    f"(confidence={section.confidence_score:.0%}, gaps={section.gap_count})",
                    event_type="stage_change",
                    metadata={"section": section_id},
                )
                _save_session(session)

            sections = await agent.run(
                asg=asg,
                gap_review=gap_review,
                facts=facts,
                user_comments=session.user_comments or "",
                session_callback=_on_section,
            )

            session.spec_sections = sections
            session.stage = REStage.COMPLETE
            session.current_stage_detail = "All sections complete"
            session.add_activity(
                f"Spec complete: {len(sections)} sections generated",
                event_type="stage_change",
                metadata={"section_count": len(sections)},
            )

            # Write spec files to output directory
            self._write_output_files(session)

            # ── DEMO CACHE: save completed spec ──────────────────────────────
            if _CACHE_AVAILABLE and sections:
                try:
                    label = f"RE: {Path(session.log_file_name or session.log_file_path or 'unknown').stem}"[:60]
                    cache_input = {
                        "file_name": session.log_file_name,
                        "user_comments": session.user_comments or "",
                    }
                    _get_demo_cache().save(
                        cache_id=session.id,
                        pipeline_type="reverse_engineer",
                        label=label,
                        input_data=cache_input,
                        output_data={
                            "spec_sections": {
                                k: dataclasses.asdict(v) if dataclasses.is_dataclass(v) else v
                                for k, v in sections.items()
                            }
                        },
                    )
                    orchestrator_logger.info(f"[CACHE] RE spec saved: id={session.id!r} label={label!r}")
                except Exception as _ce:
                    orchestrator_logger.warning(f"[CACHE] RE save failed (non-fatal): {_ce}")

            log_stage_complete(orchestrator_logger, "ORCHESTRATOR:WRITING")

        except Exception as e:
            log_stage_error(orchestrator_logger, "ORCHESTRATOR:WRITING", str(e))
            session.stage = REStage.FAILED
            session.error = f"Spec writing failed: {e}"
            session.add_activity(f"Spec writing error: {e}", level="error")

        _save_session(session)

    def _write_output_files(self, session: RESession) -> None:
        """Write all spec sections to the output directory."""
        session_dir = self._output_dir / session.id
        session_dir.mkdir(parents=True, exist_ok=True)

        section_titles = {
            "executive_summary": "00_executive_summary",
            "service_inventory": "01_service_inventory",
            "api_catalog": "02_api_catalog",
            "business_logic": "03_business_logic",
            "event_topology": "04_event_topology",
            "data_model": "05_data_model",
            "cross_cutting": "06_cross_cutting",
            "slos_and_observability": "07_slos_and_observability",
            "resilience_patterns": "08_resilience_patterns",
            "tech_stack": "09_tech_stack",
            "risks_and_gaps": "10_risks_and_gaps",
            "confidence_report": "11_confidence_report",
        }

        for section_id, section in session.spec_sections.items():
            filename = section_titles.get(section_id, section_id) + ".md"
            out_path = session_dir / filename
            header = f"# {section.title}\n\n"
            meta = (
                f"*Confidence: {section.confidence_score:.0%} | "
                f"Gaps: {section.gap_count}*\n\n---\n\n"
            )
            out_path.write_text(header + meta + section.content_md, encoding="utf-8")

        orchestrator_logger.info(
            f"   Spec files written to {session_dir} "
            f"({len(session.spec_sections)} files)"
        )


# ─── Reconstruction helpers ───────────────────────────────────────────────────

def _dict_to_extracted_facts(data: Optional[Dict], session_id: str):
    """Reconstruct ExtractedFacts from a serialized dict."""
    from .schemas import (
        Confidence, EndpointInfo, ErrorEvent, ExtractedFacts,
        KafkaTopicInfo, ResiliencePattern, ServiceDataStore,
        ServiceInfo, SLOMetric, TraceFlow,
    )

    if not data:
        return ExtractedFacts(
            session_id=session_id,
            log_file_name="",
            total_log_lines=0,
            parsed_at=time.time(),
        )

    def _rebuild_services(items):
        return [ServiceInfo(**s) for s in (items or [])]

    def _rebuild_endpoints(items):
        result = []
        for e in (items or []):
            e2 = dict(e)
            e2["confidence"] = Confidence(e2.get("confidence", "CONFIRMED"))
            result.append(EndpointInfo(**e2))
        return result

    def _rebuild_trace_flows(items):
        return [TraceFlow(**t) for t in (items or [])]

    def _rebuild_kafka(items):
        return [KafkaTopicInfo(**k) for k in (items or [])]

    def _rebuild_stores(items):
        return [ServiceDataStore(**s) for s in (items or [])]

    def _rebuild_resilience(items):
        return [ResiliencePattern(**r) for r in (items or [])]

    def _rebuild_slos(items):
        return [SLOMetric(**s) for s in (items or [])]

    def _rebuild_errors(items):
        return [ErrorEvent(**e) for e in (items or [])]

    return ExtractedFacts(
        session_id=data.get("session_id", session_id),
        log_file_name=data.get("log_file_name", ""),
        total_log_lines=data.get("total_log_lines", 0),
        parsed_at=data.get("parsed_at", time.time()),
        services=_rebuild_services(data.get("services")),
        endpoints=_rebuild_endpoints(data.get("endpoints")),
        trace_flows=_rebuild_trace_flows(data.get("trace_flows")),
        kafka_topics=_rebuild_kafka(data.get("kafka_topics")),
        data_stores=_rebuild_stores(data.get("data_stores")),
        resilience_patterns=_rebuild_resilience(data.get("resilience_patterns")),
        slo_metrics=_rebuild_slos(data.get("slo_metrics")),
        errors=_rebuild_errors(data.get("errors")),
        log_templates=data.get("log_templates", []),
    )


def _dict_to_asg(data: Optional[Dict], session_id: str):
    """Reconstruct ApplicationSpecGraph from a serialized dict."""
    from .schemas import (
        ApplicationSpecGraph, ASGServiceNode, ASGDependencyEdge,
        ASGClaim, Confidence,
    )

    def _conf(s):
        try:
            return Confidence(s)
        except Exception:
            return Confidence.INFERRED

    if not data:
        return ApplicationSpecGraph(session_id=session_id, inferred_at=time.time())

    nodes = [
        ASGServiceNode(**{**n, "confidence": _conf(n.get("confidence", "INFERRED"))})
        for n in data.get("service_nodes", [])
    ]
    edges = [
        ASGDependencyEdge(**{**e, "confidence": _conf(e.get("confidence", "INFERRED"))})
        for e in data.get("dependency_edges", [])
    ]
    claims = [
        ASGClaim(**{**c, "confidence": _conf(c.get("confidence", "INFERRED"))})
        for c in data.get("all_claims", [])
    ]

    return ApplicationSpecGraph(
        session_id=data.get("session_id", session_id),
        inferred_at=data.get("inferred_at", time.time()),
        service_nodes=nodes,
        dependency_edges=edges,
        all_claims=claims,
    )
