"""
TokenTracker — per-pipeline token usage accumulator.

Every LLM call in the pipeline reports its token counts here.
When the pipeline completes, call .snapshot(pipeline_id) to get
a dict ready to pass into DemoCache.save(token_usage=...).

Usage:
    from modules.cache.token_tracker import get_tracker

    tracker = get_tracker()

    # In any agent after an LLM call:
    tracker.record(
        pipeline_id="abc-123",
        model="gemini-2.5-flash",
        input_tokens=1200,
        output_tokens=450,
        call_label="ImpactAgent.analyze",   # optional human label
    )

    # At cache-save time:
    usage = tracker.snapshot("abc-123")
    cache.save(..., token_usage=usage)

    # Cleanup after save:
    tracker.clear("abc-123")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Gemini pricing table (USD per 1M tokens, as of Sep 2026)
# Source: https://ai.google.dev/pricing
#
# Token field mapping from usage_metadata (per official docs):
#   prompt_token_count     → input tokens (everything sent in)
#   candidates_token_count → output tokens (visible response text only)
#   thoughts_token_count   → reasoning/thinking tokens (internal chain of thought,
#                            SEPARATE from candidates — billed at output rate)
#   total_token_count      → prompt + candidates + thoughts combined
#
# Cost formula: (input × input_price) + ((output + thinking) × output_price)
# ---------------------------------------------------------------------------

PRICING: Dict[str, Dict[str, float]] = {
    # model_name → {input: $/1M, output: $/1M}
    "gemini-2.5-pro":          {"input": 1.25,   "output": 10.00},
    "gemini-2.5-flash":        {"input": 0.15,   "output": 0.60},
    "gemini-2.5-flash-lite":   {"input": 0.075,  "output": 0.30},
    # Fallback for unknown models
    "_default":                {"input": 0.15,   "output": 0.60},
}


def price_per_million(model: str) -> Dict[str, float]:
    """Return pricing dict for a model, falling back to _default."""
    # Normalise: strip provider prefix e.g. "google/gemini-2.5-flash" → "gemini-2.5-flash"
    key = model.split("/")[-1].lower()
    for k, v in PRICING.items():
        if k in key:
            return v
    return PRICING["_default"]


def calc_cost(model: str, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> float:
    """Return USD cost for a single LLM call.
    
    Per Google docs: thinking/reasoning tokens (thoughts_token_count) are billed
    at output token rates — they are separate from candidates_token_count but
    charged the same way.
    """
    p = price_per_million(model)
    return (input_tokens * p["input"] + (output_tokens + reasoning_tokens) * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float
    label: str
    ts: float = field(default_factory=time.time)


@dataclass
class PipelineUsage:
    pipeline_id: str
    calls: List[CallRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, record: CallRecord) -> None:
        with self._lock:
            self.calls.append(record)

    def to_dict(self) -> dict:
        """
        Serialise into the format stored in demo_cache.token_usage and
        returned by the /cache/:id API.

        Shape:
        {
          "by_model": {
            "gemini-2.5-flash": {
              "input_tokens": 12000,
              "output_tokens": 4500,
              "reasoning_tokens": 800,
              "calls": 3,
              "cost_usd": 0.0045,
              "price_input_per_m": 0.15,
              "price_output_per_m": 0.60
            },
            ...
          },
          "totals": {
            "input_tokens": 13200,
            "output_tokens": 5000,
            "reasoning_tokens": 900,
            "calls": 4,
            "cost_usd": 0.0053
          },
          "call_log": [
            {"model": "gemini-2.5-flash", "input": 1200, "output": 450, "reasoning": 120,
             "cost_usd": 0.00045, "label": "ImpactAgent.analyze", "ts": 1234567890.0},
            ...
          ]
        }
        """
        with self._lock:
            calls_copy = list(self.calls)

        by_model: Dict[str, dict] = {}
        for c in calls_copy:
            key = c.model
            if key not in by_model:
                p = price_per_million(key)
                by_model[key] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "calls": 0,
                    "cost_usd": 0.0,
                    "price_input_per_m":  p["input"],
                    "price_output_per_m": p["output"],
                }
            by_model[key]["input_tokens"]     += c.input_tokens
            by_model[key]["output_tokens"]    += c.output_tokens
            by_model[key]["reasoning_tokens"] += c.reasoning_tokens
            by_model[key]["calls"]            += 1
            by_model[key]["cost_usd"]         += c.cost_usd

        total_input     = sum(c.input_tokens     for c in calls_copy)
        total_output    = sum(c.output_tokens    for c in calls_copy)
        total_reasoning = sum(c.reasoning_tokens for c in calls_copy)
        total_cost      = sum(c.cost_usd         for c in calls_copy)

        return {
            "by_model": by_model,
            "totals": {
                "input_tokens":     total_input,
                "output_tokens":    total_output,
                "reasoning_tokens": total_reasoning,
                "calls":            len(calls_copy),
                "cost_usd":         round(total_cost, 6),
            },
            "call_log": [
                {
                    "model":            c.model,
                    "input":            c.input_tokens,
                    "output":           c.output_tokens,
                    "reasoning":        c.reasoning_tokens,
                    "cost_usd":         round(c.cost_usd, 6),
                    "label":            c.label,
                    "ts":               c.ts,
                }
                for c in calls_copy
            ],
        }


# ---------------------------------------------------------------------------
# Global tracker (singleton)
# ---------------------------------------------------------------------------

class TokenTracker:
    """
    Thread-safe global accumulator for LLM token usage.
    One entry per active pipeline_id.
    """

    def __init__(self) -> None:
        self._runs: Dict[str, PipelineUsage] = {}
        self._lock = threading.Lock()

    def record(
        self,
        pipeline_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        call_label: str = "",
        reasoning_tokens: int = 0,
    ) -> None:
        """Record token usage for one LLM call."""
        if not pipeline_id:
            return

        cost = calc_cost(model, input_tokens, output_tokens, reasoning_tokens)
        rec = CallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=cost,
            label=call_label,
        )

        with self._lock:
            if pipeline_id not in self._runs:
                self._runs[pipeline_id] = PipelineUsage(pipeline_id=pipeline_id)
            run = self._runs[pipeline_id]

        run.add(rec)

    def snapshot(self, pipeline_id: str) -> dict:
        """Return usage dict for a pipeline (empty dict if not found)."""
        with self._lock:
            run = self._runs.get(pipeline_id)
        return run.to_dict() if run else {}

    def clear(self, pipeline_id: str) -> None:
        """Remove a completed pipeline's tracking data."""
        with self._lock:
            self._runs.pop(pipeline_id, None)


# Module-level singleton
_tracker: Optional[TokenTracker] = None


def get_tracker() -> TokenTracker:
    """Return the module-level singleton TokenTracker."""
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker
