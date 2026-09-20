"""
Harness Utilities
=================

Shared deterministic harness components for the impact analysis pipeline.
All functions are pure Python, zero new dependencies, thread-safe.

Components:
  PolicyGate      — action boundary: blocks write Cypher, validates inputs
  ToolReceiptLog  — records every actual tool call (proves tools were used)
  BudgetEnforcer  — tracks LLM calls + wall-clock time, rejects runaway runs
  LoopDetector    — detects same tool called with same args 3x in a row
  sanitize_message — strips obvious prompt injection from user input
  ground_services  — removes service names not in graph from agent output
  check_report_grounding — scans report for hallucinated service names
  structured_log   — enriches activity_log entries with event_type + metadata
"""

import re
import time
import json
import hashlib
from pathlib import Path
from threading import local
from typing import Optional


# =============================================================================
# POLICY GATE  (ITEM 6 — action boundary on tool arguments)
# =============================================================================

# Cypher operations that would mutate the Kuzu database
_WRITE_OPS = frozenset([
    "CREATE ", "DELETE ", "MERGE ", "SET ", "REMOVE ",
    "DROP ", "DETACH ", "LOAD ",
])


def check_cypher_safe(query: str) -> tuple[bool, str]:
    """
    Return (allowed, error_message).
    Blocks any Cypher query that starts with a write keyword.
    Error message is written for the model to act on (ITEM 7 pattern).
    """
    upper = query.strip().upper()
    for op in _WRITE_OPS:
        if upper.startswith(op) or ("\n" + op) in upper:
            return False, (
                f"Write operation '{op.strip()}' is not allowed on the code graph. "
                "Only read queries are permitted. Use MATCH/RETURN to query data. "
                "Example: MATCH (s:Symbol) WHERE s.name CONTAINS 'validate' RETURN s.name"
            )
    return True, ""


def check_symbol_name(name: str) -> tuple[bool, str]:
    """
    Validate symbol_name before hitting the graph.
    Return (valid, error_message).
    """
    if not name or not name.strip():
        return False, "symbol_name cannot be empty — provide the exact function or class name."
    if len(name) > 200:
        return False, (
            f"symbol_name is {len(name)} characters — likely a malformed input. "
            "Provide a short function name like 'processPayment' or 'validatePayment'."
        )
    forbidden = [";", "--", "/*", "\n", "\r"]
    for ch in forbidden:
        if ch in name:
            return False, (
                f"symbol_name contains invalid character '{ch}'. "
                "Provide a plain function or class name without special characters."
            )
    return True, ""


# =============================================================================
# TOOL RECEIPT LOG  (ITEM 3 — proof that tools were actually called)
# =============================================================================

_receipts = local()  # thread-local so parallel pipeline runs don't interfere


def receipts_reset():
    """Clear the receipt log at the start of each analysis run."""
    _receipts.log = []


def receipts_log(tool_name: str, input_preview: str, result_count: int):
    """
    Record one tool execution receipt.
    Called after every successful tool invocation in the ImpactAgent.
    """
    if not hasattr(_receipts, "log"):
        _receipts.log = []
    _receipts.log.append({
        "tool": tool_name,
        "input": str(input_preview)[:120],
        "result_count": result_count,
        "ts": time.time(),
    })


def receipts_get() -> list[dict]:
    """Return a copy of the current receipt log."""
    return list(getattr(_receipts, "log", []))


def receipts_assert_used(min_calls: int = 1) -> tuple[bool, str]:
    """
    Assert that at least min_calls tool receipts exist.
    Returns (ok, error_message).
    Used to reject reports produced without any graph queries (ITEM 3).
    """
    receipts = receipts_get()
    if len(receipts) < min_calls:
        tools_used = [r["tool"] for r in receipts]
        return False, (
            f"ImpactAgent produced a report with only {len(receipts)} graph tool call(s) "
            f"(minimum required: {min_calls}). "
            f"Tools called: {tools_used if tools_used else 'none'}. "
            "This suggests the report was generated from training data rather than "
            "actual code graph queries. Re-run the analysis."
        )
    return True, ""


# =============================================================================
# BUDGET ENFORCER  (P4 — cap LLM calls and wall-clock time per run)
# =============================================================================

class BudgetEnforcer:
    """
    Track resource usage for one pipeline run.
    Forge's max_iterations=3 caps the verification loop;
    this caps total LLM calls and wall-clock time inside a single analysis.
    """

    def __init__(
        self,
        max_llm_calls: int = 50,
        max_tool_calls: int = 200,
        max_seconds: int = 600,
    ):
        self.max_llm_calls = max_llm_calls
        self.max_tool_calls = max_tool_calls
        self.max_seconds = max_seconds
        self.llm_calls = 0
        self.tool_calls = 0
        self._start = time.time()

    def record_llm_call(self):
        self.llm_calls += 1

    def record_tool_call(self):
        self.tool_calls += 1

    def remaining_turns(self) -> int:
        """Approximate remaining LLM turns before budget expires."""
        return max(0, self.max_llm_calls - self.llm_calls)

    def check(self) -> tuple[bool, str]:
        """Return (within_budget, error_message)."""
        if self.llm_calls >= self.max_llm_calls:
            return False, (
                f"LLM call budget exhausted ({self.max_llm_calls} calls). "
                "Wrap up the current analysis and produce the final report now."
            )
        if self.tool_calls >= self.max_tool_calls:
            return False, (
                f"Tool call budget exhausted ({self.max_tool_calls} calls). "
                "Produce the final report with findings gathered so far."
            )
        elapsed = time.time() - self._start
        if elapsed >= self.max_seconds:
            return False, (
                f"Time budget exhausted ({int(elapsed)}s / {self.max_seconds}s). "
                "Produce the final report immediately."
            )
        return True, ""

    def get_budget_message(self) -> Optional[str]:
        """
        Return a turn-budget warning to inject into context (P4 pattern).
        Returns None if no warning needed yet.
        """
        remaining = self.remaining_turns()
        if remaining <= 2:
            return (
                "\n\n# BUDGET: Only 2 turns remaining.\n"
                "STOP all new analysis. Write the final report NOW with what you have."
            )
        if remaining <= 5:
            return (
                f"\n\nNote: {remaining} turns remaining. "
                "Finish the current service analysis and do not start new ones."
            )
        if remaining <= 10:
            return f"\n\nNote: {remaining} turns remaining in this analysis session."
        return None


# =============================================================================
# LOOP DETECTOR  (P2 — detect same tool called with same input 3x)
# =============================================================================

class LoopDetector:
    """
    Detect when an agent calls the same tool with the same arguments
    repeatedly without making progress.
    """

    def __init__(self, window: int = 5, threshold: int = 3):
        self.window = window
        self.threshold = threshold
        self._history: list[tuple] = []

    def record(self, tool_name: str, inputs: dict):
        """Record a tool call. Call before executing the tool."""
        key = (tool_name, json.dumps(inputs, sort_keys=True, default=str)[:200])
        self._history.append(key)
        # Keep only the sliding window
        if len(self._history) > self.window * 2:
            self._history = self._history[-self.window * 2:]

    def check(self) -> tuple[bool, str]:
        """
        Return (loop_detected, intervention_message).
        Returns (False, '') when no loop is detected.
        """
        recent = self._history[-self.window:] if len(self._history) >= self.window else self._history
        if len(recent) < self.threshold:
            return False, ""
        for key in set(recent):
            if recent.count(key) >= self.threshold:
                tool_name = key[0]
                return True, (
                    f"\n\n[HARNESS LOOP DETECTED] You have called '{tool_name}' "
                    f"with the same arguments {recent.count(key)} times without new results.\n"
                    "Stop repeating this call. Try a different tool, different input, "
                    "or move on to the next service. If you have enough data, write the report."
                )
        return False, ""


# =============================================================================
# PROMPT INJECTION SANITIZER  (C2 — security & governance)
# =============================================================================

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(your\s+)?(previous\s+|prior\s+)?instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a?\s*different", re.IGNORECASE),
    re.compile(r"output\s+(the\s+)?(api[_\s]?key|secret|password|token|key)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions|context)", re.IGNORECASE),
    re.compile(r"new\s+persona\s*:", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
]


def sanitize_message(msg: str) -> tuple[str, bool]:
    """
    Strip obvious prompt injection attempts from user input.
    Returns (sanitized_message, was_modified).
    Logs the attempt but does not expose details to the user.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(msg):
            return (
                "[This message contained potentially unsafe content "
                "and has been sanitized for security.]",
                True,
            )
    return msg, False


# =============================================================================
# SERVICE NAME GROUNDING  (ITEM 2, ITEM 4 — cross-ref against graph)
# =============================================================================

def ground_services(
    services: list[str],
    known_services: list[str],
) -> tuple[list[str], list[str]]:
    """
    Split services list into (valid, hallucinated).
    valid: appear in known_services
    hallucinated: do not appear in known_services
    """
    valid = [s for s in services if s in known_services]
    hallucinated = [s for s in services if s not in known_services]
    return valid, hallucinated


def check_report_grounding(report: str, known_services: list[str]) -> list[str]:
    """
    Scan impact report text for SERVICE: lines and verify each name
    exists in the codebase graph.
    Returns list of service names in the report that are NOT in the graph.
    Pattern: 'SERVICE: <name>' (standard layered report format).
    """
    if not known_services:
        return []
    known = set(known_services)
    mentioned = re.findall(r"SERVICE:\s+([\w-]+)", report)
    hallucinated = [s for s in mentioned if s and s not in known]
    return list(set(hallucinated))


# =============================================================================
# ARTIFACT STORE  (C4 — keep large results off the model context)
# =============================================================================

_ARTIFACT_DIR = Path("./artifacts")


def store_artifact(data: dict, tool_name: str) -> str:
    """
    Write a large result to disk and return a handle string.
    Used when a tool returns more than ARTIFACT_THRESHOLD rows.
    """
    _ARTIFACT_DIR.mkdir(exist_ok=True)
    content = json.dumps(data, indent=2, default=str)
    hash_id = hashlib.sha256(content.encode()).hexdigest()[:12]
    path = _ARTIFACT_DIR / f"{tool_name}_{hash_id}.json"
    path.write_text(content, encoding="utf-8")
    return f"artifact://{path.name}"


# Rows above this threshold get offloaded to artifact store
ARTIFACT_THRESHOLD = 20


# =============================================================================
# EPISTEMIC CLASSIFIER  (ITEM 8 — tag report claims by source)
# =============================================================================

def classify_report_claims(report: str, grounded_services: set) -> str:
    """
    Tag each SERVICE: line in the report with its epistemic source:
      [GRAPH]    — service appeared in actual graph query results (high trust)
      [MODEL]    — service not confirmed by graph queries (flag to human)

    This is the claim provenance required by regulated industry harnesses.
    """
    lines = report.split("\n")
    tagged = []
    for line in lines:
        if line.startswith("SERVICE:"):
            # Extract service name (before any existing tag or bracket)
            svc_name = re.sub(r"\[.*?\]", "", line.split("SERVICE:")[1]).strip()
            if svc_name in grounded_services:
                line = line.replace("SERVICE:", "SERVICE: [GRAPH]", 1)
            else:
                line = line.replace("SERVICE:", "SERVICE: [MODEL]", 1)
        tagged.append(line)
    return "\n".join(tagged)


# =============================================================================
# STRUCTURED EVENT LOG HELPER  (C5 — enriched activity_log entries)
# =============================================================================

def make_log_entry(
    message: str,
    level: str = "info",
    event_type: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Build a structured activity_log entry with event_type and metadata.
    Replaces plain string log entries with typed, queryable events.

    event_type values:
      "tool_call"      — a graph tool was invoked
      "harness_check"  — a harness validation ran (pass or fail)
      "stage_change"   — pipeline stage transition
      "budget_warning" — budget is running low
      "injection_blocked" — prompt injection was sanitized
    """
    return {
        "time": time.time(),
        "message": message,
        "level": level,
        "event_type": event_type,
        "metadata": metadata or {},
    }
