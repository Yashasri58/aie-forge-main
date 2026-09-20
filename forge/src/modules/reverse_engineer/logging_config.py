"""
Logging configuration for Reverse Engineer module.

Provides structured logging for:
- Log Parser (Stage 1 — deterministic)
- Template Extractor (Stage 2 — Drain3)
- Inference Agent (Stage 3 — LLM)
- Gap Agent (Stage 4 — LLM)
- Spec Writer Agent (Stage 5 — LLM)
- Orchestrator / Harness
"""

import logging
import sys
from typing import Optional
from datetime import datetime


# ─── Per-stage loggers ───────────────────────────────────────────────────────

parser_logger = logging.getLogger("forge.re.parser")
extractor_logger = logging.getLogger("forge.re.extractor")
inference_logger = logging.getLogger("forge.re.inference")
gap_logger = logging.getLogger("forge.re.gap")
spec_logger = logging.getLogger("forge.re.spec")
orchestrator_logger = logging.getLogger("forge.re.orchestrator")
harness_logger = logging.getLogger("forge.re.harness")


# ─── Formatter ───────────────────────────────────────────────────────────────

class REFormatter(logging.Formatter):
    """Color-coded formatter matching the codegen module style."""

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    ICONS = {
        "DEBUG": "[DBG]",
        "INFO": "[INF]",
        "WARNING": "[WRN]",
        "ERROR": "[ERR]",
        "CRITICAL": "[CRT]",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = self.COLORS.get(record.levelname, "")
        icon = self.ICONS.get(record.levelname, "")
        suffix = record.name.split(".")[-1].upper()

        msg = (
            f"{color}[{ts}] {icon} [RE:{suffix}] "
            f"{record.getMessage()}{self.RESET}"
        )

        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"

        return msg


# ─── Setup ───────────────────────────────────────────────────────────────────

def setup_logging(level: str = "DEBUG") -> None:
    """Configure all reverse-engineer loggers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(REFormatter())

    root = logging.getLogger("forge.re")
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    if not root.handlers:
        root.addHandler(handler)

    root.propagate = False


# ─── Helpers (mirror codegen logging_config.py helpers) ─────────────────────

def log_stage_start(logger: logging.Logger, stage: str, detail: str = "") -> None:
    detail_str = f" -- {detail}" if detail else ""
    logger.info(f">> STAGE START: {stage}{detail_str}")


def log_stage_complete(
    logger: logging.Logger,
    stage: str,
    duration_ms: Optional[float] = None,
    detail: str = "",
) -> None:
    dur = f" in {duration_ms:.0f}ms" if duration_ms is not None else ""
    detail_str = f" -- {detail}" if detail else ""
    logger.info(f"[OK] STAGE COMPLETE: {stage}{dur}{detail_str}")


def log_stage_error(
    logger: logging.Logger, stage: str, error: str, detail: str = ""
) -> None:
    detail_str = f" -- {detail}" if detail else ""
    logger.error(f"[FAIL] STAGE FAILED: {stage} -- {error}{detail_str}")


def log_extract(
    logger: logging.Logger, item_type: str, count: int, detail: str = ""
) -> None:
    detail_str = f" ({detail})" if detail else ""
    logger.info(f"📦 EXTRACTED: {count} {item_type}{detail_str}")


def log_llm_call(
    logger: logging.Logger, model: str, prompt_preview: str
) -> None:
    logger.info(f"🤖 LLM: {model}")
    logger.debug(f"   └─ Prompt: {prompt_preview[:120]}...")


def log_harness_check(
    logger: logging.Logger, check: str, passed: bool, detail: str = ""
) -> None:
    icon = "[OK]" if passed else "[BLOCK]"
    detail_str = f" -- {detail}" if detail else ""
    logger.info(f"{icon} HARNESS [{check}]: {'PASS' if passed else 'FAIL'}{detail_str}")


def log_confidence(
    logger: logging.Logger,
    confirmed: int,
    inferred: int,
    gaps: int,
) -> None:
    total = confirmed + inferred + gaps or 1
    pct = int(confirmed / total * 100)
    logger.info(
        f"📊 CONFIDENCE: {confirmed} CONFIRMED / {inferred} INFERRED / "
        f"{gaps} GAP — {pct}% grounded"
    )


# Auto-setup on import
setup_logging("DEBUG")


__all__ = [
    "parser_logger",
    "extractor_logger",
    "inference_logger",
    "gap_logger",
    "spec_logger",
    "orchestrator_logger",
    "harness_logger",
    "setup_logging",
    "log_stage_start",
    "log_stage_complete",
    "log_stage_error",
    "log_extract",
    "log_llm_call",
    "log_harness_check",
    "log_confidence",
]
