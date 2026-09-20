"""
Harness for the Reverse Engineer pipeline.

Mirrors harness_utils.py used by the impact analysis pipeline but
scoped to the RE pipeline's specific needs:

  REPolicyGate      — blocks file writes, validates input file paths
  REToolReceiptLog  — records every LLM/tool call (proves evidence was cited)
  REBudgetEnforcer  — caps LLM calls + wall-clock time per run
  RELoopDetector    — detects same call with same inputs repeated 3× in a row
  re_policy_gate    — convenience function for file path validation

Key principle: The LLM proposes. The harness verifies.
"""

from __future__ import annotations

import json
import re
import time
from threading import local
from typing import Any, Dict, List, Optional

from .logging_config import harness_logger, log_harness_check


# ─── Policy Gate ─────────────────────────────────────────────────────────────

# Paths the agents must NOT write to
_BLOCKED_PATH_PATTERNS = [
    re.compile(r"\.\./"),           # path traversal
    re.compile(r"^/etc/"),
    re.compile(r"^/usr/"),
    re.compile(r"\.py$"),           # no Python file modifications
    re.compile(r"\.env"),
]

# Allowed log file extensions
_ALLOWED_LOG_EXTENSIONS = {".log", ".txt", ".jsonl", ".json", ".csv", ".tsv"}


def re_policy_gate(
    action: str, file_path: str = ""
) -> tuple[bool, str]:
    """
    Check whether an action is permitted for the RE pipeline.

    Args:
        action:    "read_log" | "write_spec" | "read_facts"
        file_path: File path being accessed

    Returns:
        (allowed: bool, reason: str)
    """
    if action == "read_log":
        if not file_path:
            harness_logger.warning("[RE:POLICY_GATE] DENY read_log — file_path is empty")
            return False, "file_path cannot be empty for read_log action"
        ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext and ext not in _ALLOWED_LOG_EXTENSIONS:
            harness_logger.warning(f"[RE:POLICY_GATE] DENY read_log — extension '{ext}' not in allowlist {_ALLOWED_LOG_EXTENSIONS}")
            return False, (
                f"Log file extension '{ext}' is not allowed. "
                f"Accepted: {', '.join(_ALLOWED_LOG_EXTENSIONS)}"
            )
        harness_logger.debug(f"[RE:POLICY_GATE] ALLOW read_log — {file_path}")
        return True, ""

    if action == "write_spec":
        if not file_path:
            harness_logger.warning("[RE:POLICY_GATE] DENY write_spec — file_path is empty")
            return False, "file_path cannot be empty for write_spec action"
        for pattern in _BLOCKED_PATH_PATTERNS:
            if pattern.search(file_path):
                harness_logger.warning(f"[RE:POLICY_GATE] DENY write_spec — path '{file_path}' matches blocked pattern '{pattern.pattern}'")
                return False, (
                    f"Write blocked: path '{file_path}' matches restricted pattern. "
                    "Spec output must go to the reverse-engineer/output directory."
                )
        harness_logger.debug(f"[RE:POLICY_GATE] ALLOW write_spec — {file_path}")
        return True, ""

    if action == "read_facts":
        harness_logger.debug(f"[RE:POLICY_GATE] ALLOW read_facts")
        return True, ""

    harness_logger.error(f"[RE:POLICY_GATE] DENY — unknown action: '{action}'")
    return False, f"Unknown action: '{action}'"


# ─── Tool Receipt Log ─────────────────────────────────────────────────────────

class REToolReceiptLog:
    """
    Thread-local receipt log for one RE pipeline run.
    Proves that LLM agents actually used evidence when making claims.
    """

    def __init__(self) -> None:
        self._log: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self._log = []

    def log(self, tool_name: str, inputs: Dict, result_count: int) -> None:
        self._log.append({
            "tool": tool_name,
            "inputs": {k: str(v)[:120] for k, v in inputs.items()},
            "result_count": result_count,
            "ts": time.time(),
        })

    def get(self) -> List[Dict]:
        return list(self._log)

    def assert_used(self, min_calls: int = 1) -> tuple[bool, str]:
        if len(self._log) < min_calls:
            tools = [r["tool"] for r in self._log]
            return False, (
                f"RE agent produced output with only {len(self._log)} "
                f"tool/LLM call(s) (minimum required: {min_calls}). "
                f"Calls made: {tools if tools else 'none'}. "
                "This suggests the output was generated from training data."
            )
        return True, ""

    def summary(self) -> str:
        counts: Dict[str, int] = {}
        for r in self._log:
            counts[r["tool"]] = counts.get(r["tool"], 0) + 1
        parts = [f"{tool}×{n}" for tool, n in counts.items()]
        return f"[HARNESS] Receipts ({len(self._log)} calls): {parts}"


# ─── Budget Enforcer ─────────────────────────────────────────────────────────

class REBudgetEnforcer:
    """
    Caps resources for one RE pipeline stage.
    Prevents runaway LLM loops on large log files.
    """

    def __init__(
        self,
        max_llm_calls: int = 30,
        max_seconds: int = 300,
    ) -> None:
        self.max_llm_calls = max_llm_calls
        self.max_seconds = max_seconds
        self.llm_calls = 0
        self._start = time.time()

    def record_llm_call(self) -> None:
        self.llm_calls += 1

    def remaining_calls(self) -> int:
        return max(0, self.max_llm_calls - self.llm_calls)

    def check(self) -> tuple[bool, str]:
        if self.llm_calls >= self.max_llm_calls:
            return False, (
                f"LLM call budget exhausted ({self.max_llm_calls} calls). "
                "Wrap up analysis and produce output with what you have."
            )
        elapsed = time.time() - self._start
        if elapsed >= self.max_seconds:
            return False, (
                f"Time budget exhausted ({int(elapsed)}s / {self.max_seconds}s). "
                "Produce output immediately."
            )
        return True, ""

    def get_budget_warning(self) -> Optional[str]:
        remaining = self.remaining_calls()
        if remaining <= 2:
            return (
                "\n\n[BUDGET] Only 2 calls remaining. "
                "Produce final output NOW with what you have."
            )
        if remaining <= 5:
            return f"\n\nNote: {remaining} calls remaining. Finish current analysis."
        return None


# ─── Loop Detector ────────────────────────────────────────────────────────────

class RELoopDetector:
    """
    Detects when the same tool is called with the same inputs 3+ times
    in a sliding window of 5 calls — indicates the agent is stuck.
    """

    def __init__(self, window: int = 5, threshold: int = 3) -> None:
        self.window = window
        self.threshold = threshold
        self._history: List[tuple] = []

    def record_and_check(
        self, tool: str, inputs: Dict
    ) -> tuple[bool, str]:
        """Record a call and check for loops. Returns (loop_detected, message)."""
        key = (tool, json.dumps(inputs, sort_keys=True, default=str)[:200])
        self._history.append(key)
        if len(self._history) > self.window * 2:
            self._history = self._history[-self.window * 2:]

        recent = self._history[-self.window:] if len(self._history) >= self.window else self._history
        if len(recent) < self.threshold:
            return False, ""

        for candidate in set(recent):
            if recent.count(candidate) >= self.threshold:
                return True, (
                    f"[HARNESS LOOP DETECTED] Tool '{candidate[0]}' called "
                    f"with the same inputs {recent.count(candidate)}× without new results. "
                    "Try a different approach or produce output with what you have."
                )

        return False, ""


# ─── Input sanitization ───────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(your\s+)?(previous\s+|prior\s+)?instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a?\s*different", re.IGNORECASE),
    re.compile(r"output\s+(the\s+)?(api[_\s]?key|secret|password|token)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions|context)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"new\s+persona\s*:", re.IGNORECASE),
]


def sanitize_user_comments(comments: str) -> tuple[str, bool]:
    """
    Strip obvious prompt injection from user-provided comments.
    Returns (sanitized_text, was_modified).
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(comments):
            harness_logger.warning(
                "[HARNESS] Prompt injection attempt detected in user_comments — sanitized"
            )
            return (
                "[User comments contained potentially unsafe content and were sanitized.]",
                True,
            )
    return comments, False
