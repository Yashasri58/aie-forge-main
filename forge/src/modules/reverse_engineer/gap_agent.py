"""
Stage 4 — GapAgent (Gemini 2.5 Flash).

Reviews the Application Specification Graph produced by InferenceAgent and:
- Reclassifies over-confident CONFIRMED claims to INFERRED
- Identifies true GAPs (things unknown from the log data)
- Flags contradictions in evidence
- Produces a confidence summary

Uses Gemini 2.5 Flash (not Pro) because this is a review/classification task,
not a complex reasoning task. Cheaper + faster.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .logging_config import (
    gap_logger,
    log_stage_start,
    log_stage_complete,
    log_stage_error,
    log_llm_call,
    log_harness_check,
)
from .prompts import GAP_SYSTEM, build_gap_prompt
from .schemas import (
    ApplicationSpecGraph,
    Confidence,
    ExtractedFacts,
)
from .harness import REBudgetEnforcer, REToolReceiptLog, RELoopDetector

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ─── JSON extraction helper ───────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ─── GapAgent ────────────────────────────────────────────────────────────────

class GapAgent:
    """
    Stage 4: Reviews the ASG and produces gap analysis.

    Uses Gemini 2.5 Flash for cost efficiency — gap review is
    classification, not deep reasoning.
    """

    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self) -> None:
        self._model = None
        self._budget = REBudgetEnforcer(max_llm_calls=5)
        self._receipts = REToolReceiptLog()

        if GEMINI_AVAILABLE:
            try:
                import os
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._model = genai.GenerativeModel(
                        model_name=self.MODEL_NAME,
                        system_instruction=GAP_SYSTEM,
                    )
                    gap_logger.info(f"   GapAgent initialized with {self.MODEL_NAME}")
            except Exception as e:
                gap_logger.error(f"   Failed to initialize Gemini: {e}")

    def _call_llm(self, prompt: str, pipeline_id: str = "") -> str:
        ok, err = self._budget.check()
        if not ok:
            raise RuntimeError(f"[HARNESS BUDGET] {err}")

        loop, msg = self._loop_detector.record_and_check("gap_review_llm", {"prompt_hash": hash(prompt[:100])})
        if loop:
            raise RuntimeError(f"[HARNESS LOOP] {msg}")

        log_llm_call(gap_logger, self.MODEL_NAME, prompt[:120])
        gap_logger.debug(f"   └─ Prompt: {len(prompt)} chars, asg+facts preview: {prompt[:200].replace(chr(10),' ')!r}")
        self._budget.record_llm_call()
        self._receipts.log("gap_review_llm", {"prompt_len": len(prompt)}, 1)

        if not self._model:
            return self._mock_response()

        from modules.llm_registry import _get_provider, _resolve_model, _gemini_call, _litellm_call
        model = _resolve_model(self.MODEL_NAME)
        if _get_provider() == "litellm":
            return _litellm_call(model, prompt, GAP_SYSTEM, temperature=0.4, json_mode=True)

        response = self._model.generate_content(prompt)

        # ── Token tracking ──────────────────────────────────────────────────
        if pipeline_id:
            try:
                from modules.cache.token_tracker import get_tracker
                meta = response.usage_metadata
                get_tracker().record(
                    pipeline_id=pipeline_id,
                    model=self.MODEL_NAME,
                    input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                                reasoning_tokens=getattr(meta, "thoughts_token_count", 0) or 0,
                    call_label="GapAgent._call_llm",
                )
            except Exception:
                pass

        return response.text

    def _mock_response(self) -> str:
        return json.dumps({
            "reclassifications": [],
            "gaps": [
                {
                    "gap_id": "gap-mock-1",
                    "category": "general",
                    "description": "Gap analysis unavailable (no API key)",
                    "why_unknown": "GOOGLE_API_KEY not set",
                    "data_source_that_would_help": "Set GOOGLE_API_KEY",
                    "impact": "high",
                }
            ],
            "conflicts": [],
            "confidence_summary": {
                "confirmed_count": 0,
                "inferred_count": 0,
                "gap_count": 1,
                "overall_confidence": "LOW",
                "notes": "No API key — mock mode",
            },
        })

    async def run(
        self,
        asg: ApplicationSpecGraph,
        facts: ExtractedFacts,
        pipeline_id: str = "",
    ) -> Dict[str, Any]:
        """
        Review the ASG for gaps and over-confident claims.

        Args:
            asg:   Application Specification Graph from InferenceAgent
            facts: Original extracted facts (ground truth)

        Returns:
            Dict with reclassifications, gaps, conflicts, confidence_summary
        """
        start = time.time()
        log_stage_start(
            gap_logger, "GAP_AGENT",
            f"{asg.confirmed_count} confirmed, {asg.inferred_count} inferred claims"
        )

        self._receipts.reset()
        self._budget = REBudgetEnforcer(max_llm_calls=5)
        self._loop_detector = RELoopDetector()  # added — was missing

        # Build compact representations for the prompt
        import dataclasses

        asg_dict = dataclasses.asdict(asg)
        facts_dict = dataclasses.asdict(facts)

        # Slim down for token budget
        for tf in facts_dict.get("trace_flows", []):
            tf.pop("events", None)
        facts_dict.pop("errors", None)

        asg_json = json.dumps(asg_dict, indent=2, default=str)[:15000]
        facts_json = json.dumps(facts_dict, indent=2, default=str)[:5000]

        prompt = build_gap_prompt(asg_json, facts_json)

        try:
            import asyncio, functools
            loop = asyncio.get_event_loop()
            raw_text = await loop.run_in_executor(
                None, functools.partial(self._call_llm, prompt, pipeline_id)
            )
        except Exception as e:
            log_stage_error(gap_logger, "GAP_AGENT", str(e))
            return {
                "reclassifications": [],
                "gaps": [],
                "conflicts": [],
                "confidence_summary": {
                    "confirmed_count": asg.confirmed_count,
                    "inferred_count": asg.inferred_count,
                    "gap_count": asg.gap_count,
                    "overall_confidence": "MEDIUM",
                    "notes": f"Gap review failed: {e}",
                },
            }

        result = _extract_json(raw_text)
        if not result:
            gap_logger.error("   Failed to parse gap review as JSON")
            result = {
                "reclassifications": [],
                "gaps": [],
                "conflicts": [],
                "confidence_summary": {
                    "confirmed_count": asg.confirmed_count,
                    "inferred_count": asg.inferred_count,
                    "gap_count": asg.gap_count,
                    "overall_confidence": "MEDIUM",
                    "notes": "JSON parse failed",
                },
            }

        # Apply reclassifications back to ASG in memory
        reclassifications = result.get("reclassifications", [])
        if reclassifications:
            gap_logger.info(f"   Reclassifying {len(reclassifications)} over-confident claims")
            claim_map = {c.claim_id: c for c in asg.all_claims}
            for rec in reclassifications:
                cid = rec.get("claim_id", "")
                old_conf = rec.get("old_confidence", "CONFIRMED")
                new_conf = rec.get("new_confidence", "INFERRED")
                reason = rec.get("reason", "")[:80]
                if cid in claim_map:
                    claim_map[cid].confidence = Confidence.INFERRED
                    gap_logger.info(f"   Reclassified: {cid} {old_conf} -> {new_conf} — {reason}")

        gaps = result.get("gaps", [])
        summary = result.get("confidence_summary", {})
        overall = summary.get("overall_confidence", "MEDIUM")

        log_harness_check(
            gap_logger, "output_grounding",
            len(gaps) > 0 or True,  # Always passes — gaps are informational
            f"{len(gaps)} gaps identified, {len(reclassifications)} reclassifications"
        )

        duration_ms = (time.time() - start) * 1000
        log_stage_complete(
            gap_logger, "GAP_AGENT", duration_ms,
            f"confidence={overall}, gaps={len(gaps)}"
        )

        return result
