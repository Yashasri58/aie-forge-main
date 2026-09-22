"""
Stage 5 — SpecWriterAgent (Gemini 2.5 Flash).

Generates all 11 Markdown spec sections from the verified ASG.
Includes Mermaid diagrams for service topology, sequence flows, state machines.

Uses Gemini 2.5 Flash (formatting/generation, not deep reasoning).
One LLM call per section, run sequentially to stay within budget.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .logging_config import (
    spec_logger,
    log_stage_start,
    log_stage_complete,
    log_stage_error,
    log_llm_call,
    log_extract,
)
from .prompts import SPEC_WRITER_SYSTEM, build_spec_section_prompt
from .schemas import SPEC_SECTIONS
from .schemas import (
    ApplicationSpecGraph,
    Confidence,
    ExtractedFacts,
    SpecSection,
)
from .harness import REBudgetEnforcer, REToolReceiptLog

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

import json


# ─── Section titles ───────────────────────────────────────────────────────────

SECTION_TITLES: Dict[str, str] = {
    "executive_summary": "Executive Summary",
    "service_inventory": "Service Inventory",
    "api_catalog": "API Catalog",
    "business_logic": "Business Logic & Flows",
    "event_topology": "Event Topology (Kafka)",
    "data_model": "Data Model",
    "cross_cutting": "Cross-Cutting Concerns",
    "slos_and_observability": "SLOs & Observability",
    "resilience_patterns": "Resilience Patterns",
    "tech_stack": "Technology Stack",
    "risks_and_gaps": "Risks & Gaps",
    "confidence_report": "Confidence Report",
}


# ─── JSON extraction helper ───────────────────────────────────────────────────

def _extract_json_from_text(text: str) -> Optional[Dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None


# ─── Confidence score calculation ─────────────────────────────────────────────

def _section_confidence(
    asg: ApplicationSpecGraph, section_id: str
) -> float:
    """Estimate confidence score for a section based on ASG claim categories."""
    category_map = {
        "executive_summary": ["service", "flow"],
        "service_inventory": ["service"],
        "api_catalog": ["endpoint"],
        "business_logic": ["flow"],
        "event_topology": ["flow", "data"],
        "data_model": ["data"],
        "cross_cutting": ["service"],
        "slos_and_observability": ["service"],
        "resilience_patterns": ["resilience"],
        "tech_stack": ["tech"],
        "risks_and_gaps": ["risk"],
        "confidence_report": ["service", "endpoint", "flow"],
    }

    relevant_cats = set(category_map.get(section_id, []))
    relevant = [
        c for c in asg.all_claims
        if c.category in relevant_cats
    ]

    if not relevant:
        return 0.5  # Unknown confidence if no relevant claims

    confirmed = sum(1 for c in relevant if c.confidence == Confidence.CONFIRMED)
    return round(confirmed / len(relevant), 2)


# ─── SpecWriterAgent ─────────────────────────────────────────────────────────

class SpecWriterAgent:
    """
    Stage 5: Generates all 11 Markdown spec sections.
    One call per section, sequential, Gemini 2.5 Flash.
    """

    MODEL_NAME = "gemini-3.5-flash"

    def __init__(self) -> None:
        self._client = None
        self._budget = REBudgetEnforcer(max_llm_calls=15)  # 12 sections + retries
        self._receipts = REToolReceiptLog()

        if GEMINI_AVAILABLE:
            try:
                import os
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    self._client = genai.Client(api_key=api_key)
                    spec_logger.info(f"   SpecWriterAgent initialized with {self.MODEL_NAME}")
            except Exception as e:
                spec_logger.error(f"   Failed to initialize Gemini client: {e}")

    def _call_llm(self, prompt: str, section_id: str) -> str:
        ok, err = self._budget.check()
        if not ok:
            raise RuntimeError(f"[HARNESS BUDGET] {err}")

        log_llm_call(spec_logger, self.MODEL_NAME, f"section={section_id}")
        self._budget.record_llm_call()
        self._receipts.log("spec_writer_llm", {"section": section_id}, 1)

        if not self._client:
            return self._mock_section(section_id)

        response = self._client.models.generate_content(
            model=self.MODEL_NAME,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=SPEC_WRITER_SYSTEM,
            ),
        )
        return response.text

    def _mock_section(self, section_id: str) -> str:
        title = SECTION_TITLES.get(section_id, section_id)
        return f"""*This section could not be generated — GOOGLE_API_KEY not set.*

Set the `GOOGLE_API_KEY` environment variable to enable full spec generation.

**Section:** {title}
"""

    async def run(
        self,
        asg: ApplicationSpecGraph,
        gap_review: Dict[str, Any],
        facts: ExtractedFacts,
        user_comments: str = "",
        session_callback=None,
    ) -> Dict[str, SpecSection]:
        """
        Generate all 11 spec sections.

        Args:
            asg:              Verified ApplicationSpecGraph
            gap_review:       Gap review result from GapAgent
            facts:            Original extracted facts
            user_comments:    Optional user context
            session_callback: Optional callable(section_id, SpecSection) for
                              streaming section completion to the UI

        Returns:
            Dict mapping section_id → SpecSection
        """
        start = time.time()
        log_stage_start(
            spec_logger, "SPEC_WRITER",
            f"{len(SPEC_SECTIONS)} sections to generate"
        )

        self._receipts.reset()
        self._budget = REBudgetEnforcer(max_llm_calls=15)

        import dataclasses

        # Pre-serialize for prompts
        asg_json = json.dumps(dataclasses.asdict(asg), indent=2, default=str)[:12000]
        gap_json = json.dumps(gap_review, indent=2, default=str)[:4000]
        facts_dict = dataclasses.asdict(facts)
        for tf in facts_dict.get("trace_flows", []):
            tf.pop("events", None)
        facts_json = json.dumps(facts_dict, indent=2, default=str)[:4000]

        sections: Dict[str, SpecSection] = {}

        for section_id in SPEC_SECTIONS:
            title = SECTION_TITLES.get(section_id, section_id.replace("_", " ").title())
            spec_logger.info(f"   Writing section: {title}")

            prompt = build_spec_section_prompt(
                section_id=section_id,
                asg_json=asg_json,
                gap_review_json=gap_json,
                extracted_facts_json=facts_json,
                user_comments=user_comments,
            )

            try:
                content_md = self._call_llm(prompt, section_id)
            except Exception as e:
                log_stage_error(spec_logger, f"spec:{section_id}", str(e))
                # One retry with a simpler prompt before giving up
                try:
                    spec_logger.info(f"   Retrying section {section_id} after error: {e}")
                    content_md = self._call_llm(prompt, section_id)
                    spec_logger.info(f"   Retry succeeded for {section_id}")
                except Exception as e2:
                    spec_logger.error(f"   Retry also failed for {section_id}: {e2}")
                    content_md = f"*Section generation failed after retry: {e2}*"

            # Count gaps in this section's content
            import re
            gap_count = len(re.findall(r"\[GAP\]", content_md, re.IGNORECASE))
            confidence = _section_confidence(asg, section_id)

            section = SpecSection(
                section_id=section_id,
                title=title,
                content_md=content_md,
                confidence_score=confidence,
                gap_count=gap_count,
                generated_at=time.time(),
            )

            sections[section_id] = section
            spec_logger.info(
                f"   ✓ {title} ({len(content_md)} chars, "
                f"confidence={confidence:.0%}, gaps={gap_count})"
            )

            # Stream to UI if callback provided
            if session_callback:
                try:
                    session_callback(section_id, section)
                except Exception:
                    pass

        log_extract(spec_logger, "spec sections", len(sections))

        duration_ms = (time.time() - start) * 1000
        log_stage_complete(
            spec_logger, "SPEC_WRITER", duration_ms,
            f"{len(sections)}/12 sections generated"
        )

        return sections
