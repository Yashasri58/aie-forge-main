"""
Stage 3 — InferenceAgent (Gemini 2.5 Pro).

Takes ExtractedFacts (Stage 1+2) and produces the Application Specification Graph (ASG).
Wraps the LLM call in the RE harness for:
  - Tool receipt logging
  - Loop detection
  - Budget enforcement
  - Output grounding (every service name in ASG must appear in extracted facts)

Follows the same pattern as src/modules/agents/impact/agent.py.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from .logging_config import (
    inference_logger,
    log_stage_start,
    log_stage_complete,
    log_stage_error,
    log_llm_call,
    log_confidence,
)
from .prompts import INFERENCE_SYSTEM, build_inference_prompt
from .schemas import (
    ASGClaim,
    ASGDependencyEdge,
    ASGServiceNode,
    ApplicationSpecGraph,
    Confidence,
    ExtractedFacts,
)

# ─── LLM import (mirrors impact/agent.py pattern) ────────────────────────────

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ─── Harness imports ─────────────────────────────────────────────────────────

from .harness import (
    REToolReceiptLog,
    REBudgetEnforcer,
    RELoopDetector,
    re_policy_gate,
)


# ─── JSON extraction helper ───────────────────────────────────────────────────

def _extract_json_from_response(text: str) -> Optional[Dict]:
    """Extract the first valid JSON object from an LLM response."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Try to find the outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ─── ASG builder from raw dict ────────────────────────────────────────────────

def _dict_to_asg(raw: Dict, session_id: str) -> ApplicationSpecGraph:
    """Convert raw LLM JSON output into an ApplicationSpecGraph dataclass."""

    def _conf(s: str) -> Confidence:
        s = (s or "").upper()
        if s == "CONFIRMED":
            return Confidence.CONFIRMED
        if s == "INFERRED":
            return Confidence.INFERRED
        return Confidence.GAP

    svc_nodes = [
        ASGServiceNode(
            service_name=n.get("service_name", ""),
            responsibility=n.get("responsibility", ""),
            tech_stack_hints=n.get("tech_stack_hints", []),
            preconditions=n.get("preconditions", []),
            postconditions=n.get("postconditions", []),
            invariants=n.get("invariants", []),
            confidence=_conf(n.get("confidence", "INFERRED")),
            evidence=n.get("evidence", []),
        )
        for n in raw.get("service_nodes", [])
    ]

    dep_edges = [
        ASGDependencyEdge(
            source=e.get("source", ""),
            target=e.get("target", ""),
            protocol=e.get("protocol", "HTTP"),
            direction=e.get("direction", "sync"),
            call_frequency=e.get("call_frequency", "conditional"),
            confidence=_conf(e.get("confidence", "INFERRED")),
            evidence=e.get("evidence", []),
        )
        for e in raw.get("dependency_edges", [])
    ]

    claims = [
        ASGClaim(
            claim_id=c.get("claim_id", f"claim-{i}"),
            category=c.get("category", "general"),
            subject=c.get("subject", ""),
            predicate=c.get("predicate", ""),
            value=c.get("value", ""),
            confidence=_conf(c.get("confidence", "INFERRED")),
            evidence=c.get("evidence", []),
            gaps=c.get("gaps", []),
        )
        for i, c in enumerate(raw.get("all_claims", []))
    ]

    return ApplicationSpecGraph(
        session_id=session_id,
        inferred_at=time.time(),
        service_nodes=svc_nodes,
        dependency_edges=dep_edges,
        all_claims=claims,
    )


# ─── Service name grounding ───────────────────────────────────────────────────

def _ground_asg(
    asg: ApplicationSpecGraph,
    facts: ExtractedFacts,
) -> tuple[ApplicationSpecGraph, list[str]]:
    """
    Verify every service name in the ASG exists in the extracted facts.
    Returns (asg, hallucinated_services).
    """
    known_services = {s.name for s in facts.services}
    hallucinated = []

    for node in asg.service_nodes:
        if node.service_name not in known_services:
            hallucinated.append(node.service_name)
            # Downgrade to GAP if hallucinated
            node.confidence = Confidence.GAP
            node.evidence = [f"[HARNESS] Service not found in log data. Known services: {sorted(known_services)}"]

    for edge in asg.dependency_edges:
        for svc in (edge.source, edge.target):
            if svc and svc not in known_services and svc not in hallucinated:
                hallucinated.append(svc)

    return asg, hallucinated


# ─── InferenceAgent ───────────────────────────────────────────────────────────

class InferenceAgent:
    """
    Stage 3: Uses Gemini 2.5 Pro to infer business logic,
    architecture, and behavior from ExtractedFacts.

    Produces an ApplicationSpecGraph with CONFIRMED/INFERRED/GAP confidence tags.
    """

    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self) -> None:
        self._model = None
        self._budget = REBudgetEnforcer(max_llm_calls=10)  # ASG in 1-2 calls max
        self._loop_detector = RELoopDetector()
        self._receipts = REToolReceiptLog()

        if GEMINI_AVAILABLE:
            try:
                import os
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._model = genai.GenerativeModel(
                        model_name=self.MODEL_NAME,
                        system_instruction=INFERENCE_SYSTEM,
                    )
                    inference_logger.info(f"   InferenceAgent initialized with {self.MODEL_NAME}")
                else:
                    inference_logger.warning("   GOOGLE_API_KEY not set — InferenceAgent will use mock mode")
            except Exception as e:
                inference_logger.error(f"   Failed to initialize Gemini: {e}")

    def _call_llm(self, prompt: str, pipeline_id: str = "") -> str:
        """Make one LLM call with budget + loop detection."""
        # Budget check
        ok, err = self._budget.check()
        if not ok:
            raise RuntimeError(f"[HARNESS BUDGET] {err}")

        # Loop detection
        loop, msg = self._loop_detector.record_and_check("inference_llm", {"prompt_hash": hash(prompt[:100])})
        if loop:
            raise RuntimeError(f"[HARNESS LOOP] {msg}")

        log_llm_call(inference_logger, self.MODEL_NAME, prompt[:120])
        inference_logger.debug(f"   └─ Prompt: {len(prompt)} chars, first 200: {prompt[:200].replace(chr(10),' ')!r}")
        self._budget.record_llm_call()
        self._receipts.log("inference_llm", {"prompt_len": len(prompt)}, 1)

        if not self._model:
            return self._mock_response()

        from modules.llm_registry import _get_provider, _resolve_model, _gemini_call, _litellm_call
        model = _resolve_model(self.MODEL_NAME)
        if _get_provider() == "litellm":
            return _litellm_call(model, prompt, INFERENCE_SYSTEM, temperature=0.4, max_tokens=8192)

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
                    call_label="InferenceAgent._call_llm",
                )
            except Exception:
                pass

        return response.text

    def _mock_response(self) -> str:
        """Return a minimal valid ASG for testing without API key."""
        return json.dumps({
            "service_nodes": [
                {
                    "service_name": "mock-service",
                    "responsibility": "Mock service (no API key)",
                    "tech_stack_hints": [],
                    "preconditions": [],
                    "postconditions": [],
                    "invariants": [],
                    "confidence": "GAP",
                    "evidence": ["[MOCK] No GOOGLE_API_KEY set"],
                }
            ],
            "dependency_edges": [],
            "all_claims": [
                {
                    "claim_id": "mock-1",
                    "category": "general",
                    "subject": "analysis",
                    "predicate": "status",
                    "value": "No GOOGLE_API_KEY — set env var to enable full analysis",
                    "confidence": "GAP",
                    "evidence": [],
                    "gaps": ["GOOGLE_API_KEY required for LLM inference"],
                }
            ],
        })

    async def run(
        self,
        facts: ExtractedFacts,
        user_comments: str = "",
        session_id: str = "",
        pipeline_id: str = "",
    ) -> ApplicationSpecGraph:
        """
        Run the inference agent.

        Args:
            facts:         ExtractedFacts from Stage 1+2
            user_comments: Optional user context
            session_id:    Pipeline session ID

        Returns:
            ApplicationSpecGraph
        """
        start = time.time()
        log_stage_start(
            inference_logger, "INFERENCE_AGENT",
            f"{facts.service_count} services, {facts.endpoint_count} endpoints"
        )

        self._receipts.reset()
        self._budget = REBudgetEnforcer(max_llm_calls=10)
        self._loop_detector = RELoopDetector()

        # ── Build prompt ────────────────────────────────────────────────────
        # Compress facts for LLM (don't include raw events — too large)
        import dataclasses
        facts_dict = dataclasses.asdict(facts)

        # Remove raw event data from trace flows — keep only summaries
        for tf in facts_dict.get("trace_flows", []):
            tf.pop("events", None)

        # Limit parameters in templates to avoid bloat
        for t in facts_dict.get("log_templates", []):
            t["parameters"] = t.get("parameters", [])[:3]

        facts_json = json.dumps(facts_dict, indent=2, default=str)

        # If facts JSON is too large, summarize it
        if len(facts_json) > 30000:
            inference_logger.warning(
                f"   Facts JSON is {len(facts_json)} chars — summarizing for LLM"
            )
            # Keep only the most informative fields
            summarized = {
                "services": facts_dict.get("services", []),
                "endpoints": facts_dict.get("endpoints", [])[:20],
                "trace_flows": [
                    {k: v for k, v in tf.items() if k != "events"}
                    for tf in facts_dict.get("trace_flows", [])
                ],
                "kafka_topics": facts_dict.get("kafka_topics", []),
                "data_stores": facts_dict.get("data_stores", []),
                "resilience_patterns": facts_dict.get("resilience_patterns", []),
                "slo_metrics": facts_dict.get("slo_metrics", []),
                "errors": facts_dict.get("errors", [])[:10],
                "log_templates": facts_dict.get("log_templates", [])[:20],
            }
            facts_json = json.dumps(summarized, indent=2, default=str)

        prompt = build_inference_prompt(facts_json, user_comments)

        # ── Call LLM ────────────────────────────────────────────────────────
        try:
            import asyncio, functools
            loop = asyncio.get_event_loop()
            raw_text = await loop.run_in_executor(
                None, functools.partial(self._call_llm, prompt, pipeline_id)
            )
            inference_logger.debug(f"   LLM response length: {len(raw_text)} chars")
        except Exception as e:
            log_stage_error(inference_logger, "INFERENCE_AGENT", str(e))
            # Return minimal ASG on error
            return ApplicationSpecGraph(session_id=session_id, inferred_at=time.time())

        # ── Parse JSON ───────────────────────────────────────────────────────
        raw_dict = _extract_json_from_response(raw_text)
        if not raw_dict:
            inference_logger.warning("   Failed to parse LLM response as JSON — retrying once")
            try:
                retry_prompt = prompt + "\n\nYOUR PREVIOUS RESPONSE DID NOT CONTAIN VALID JSON.\nReturn ONLY a JSON object — no prose, no markdown fences around it, just the raw JSON."
                raw_text2 = await loop.run_in_executor(
                    None, functools.partial(self._call_llm, retry_prompt, pipeline_id)
                )
                raw_dict = _extract_json_from_response(raw_text2)
            except Exception as re:
                inference_logger.error(f"   Retry also failed: {re}")
            
            if not raw_dict:
                inference_logger.error("   Could not parse ASG JSON after retry — returning empty ASG")
                return ApplicationSpecGraph(session_id=session_id, inferred_at=time.time())

        # ── Build ASG ────────────────────────────────────────────────────────
        asg = _dict_to_asg(raw_dict, session_id or facts.session_id)

        # ── Harness: ground service names ────────────────────────────────────
        asg, hallucinated = _ground_asg(asg, facts)
        if hallucinated:
            inference_logger.warning(
                f"   [HARNESS] Hallucinated services detected: {hallucinated}"
            )

        # ── Log confidence breakdown ─────────────────────────────────────────
        log_confidence(
            inference_logger,
            asg.confirmed_count,
            asg.inferred_count,
            asg.gap_count,
        )

        duration_ms = (time.time() - start) * 1000
        log_stage_complete(
            inference_logger, "INFERENCE_AGENT", duration_ms,
            f"{len(asg.service_nodes)} service nodes, {len(asg.all_claims)} claims"
        )

        inference_logger.info(
            f"   [HARNESS] Receipts: {len(self._receipts.get())} LLM calls recorded"
        )

        return asg
