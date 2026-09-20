"""
Stage 2 — Template Extractor (Drain3 template mining).

Takes the raw log lines and produces log templates using Drain3.
Templates reduce 50+ raw lines → ~15 semantic patterns, cutting LLM context
by ~70% before Stage 3 (InferenceAgent).

Masking config handles our specific ID patterns:
  ORD-20260917-5541 → <ORDER_ID>
  USR-88412         → <USER_ID>
  TXN-9f3e7a21      → <TXN_ID>
  UUIDs             → <UUID>
  Timestamps        → <DATETIME>

Falls back gracefully if drain3 is not installed — returns raw line
clusters instead of templates so the pipeline still works.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging_config import (
    extractor_logger,
    log_stage_start,
    log_stage_complete,
    log_extract,
)
from .schemas import ExtractedFacts

# ─── Try importing drain3 ────────────────────────────────────────────────────

try:
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    DRAIN3_AVAILABLE = True
except ImportError:
    DRAIN3_AVAILABLE = False
    extractor_logger.warning(
        "drain3 not installed. Falling back to regex clustering. "
        "Install with: pip install drain3"
    )


# ─── Pre-masking patterns (applied BEFORE Drain3) ────────────────────────────
# Drain3 works better when variable ID-like tokens are masked first.

_PRE_MASKS: List[tuple] = [
    # UUIDs
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<UUID>"),
    # ISO timestamps inside messages
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"), "<DATETIME>"),
    # Date-only  2026-09-17
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "<DATE>"),
    # Order IDs:  ORD-20260917-5541
    (re.compile(r"ORD-[\d\w-]+"), "<ORDER_ID>"),
    # User IDs:   USR-88412
    (re.compile(r"USR-\d+"), "<USER_ID>"),
    # Transaction IDs:  TXN-9f3e7a21
    (re.compile(r"TXN-[0-9a-f]+"), "<TXN_ID>"),
    # Settlement IDs:   SETTLE-2026-09-16
    (re.compile(r"SETTLE-[\d-]+"), "<SETTLE_ID>"),
    # FCM device tokens
    (re.compile(r"FCM-tk-\d+"), "<FCM_TOKEN>"),
    # SES message IDs
    (re.compile(r"[0-9a-f]{16}"), "<HEX_ID>"),
    # IP addresses
    (re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"), "<IP>"),
    # Port numbers like :8082
    (re.compile(r":\d{4,5}\b"), ":<PORT>"),
    # Kubernetes pod names  order-svc-7d9f4b-x2klp
    (re.compile(r"[a-z]+-[a-z]+-[0-9a-f]+-[a-z0-9]+"), "<K8S_POD>"),
    # Generic long hex strings
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "<HEX>"),
    # Numbers in the middle of messages (counts, amounts, latencies)
    (re.compile(r"\b\d{4,}\b"), "<NUM>"),
    # Monetary amounts  $247.50  $1,299.00
    (re.compile(r"\$[\d,]+\.\d{2}"), "<AMOUNT>"),
    # Percentages and decimal metrics
    (re.compile(r"\d+\.\d+%?"), "<METRIC>"),
    # Card endings  card_ending_4421
    (re.compile(r"card_ending_\d+"), "<CARD>"),
    # SKU codes  SKU-100  SKU-245
    (re.compile(r"SKU-\d+"), "<SKU>"),
    # Batch IDs
    (re.compile(r"batch_id=\S+"), "batch_id=<BATCH_ID>"),
]

# ─── Log-line prefix stripper ────────────────────────────────────────────────
# Strip the structured prefix (timestamp, level, [service], [traceId], [spanId])
# so Drain3 only sees the message body.

_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+\w+\s+"
    r"\[[^\]]+\]"              # [service]
    r"(?:\s+\[[^\]]+\])?"     # optional [traceId=...]
    r"(?:\s+\[[^\]]+\])?"     # optional [spanId=...]
    r"\s+"
)


def _strip_prefix(line: str) -> str:
    m = _PREFIX.match(line)
    return line[m.end():] if m else line


def _apply_masks(text: str) -> str:
    for pattern, replacement in _PRE_MASKS:
        text = pattern.sub(replacement, text)
    return text


# ─── Drain3 template extractor ───────────────────────────────────────────────

def _extract_with_drain3(
    messages: List[str],
) -> List[Dict[str, Any]]:
    """
    Run Drain3 on a list of pre-processed message strings.
    Returns list of: { template, count, parameters, services }
    """
    config = TemplateMinerConfig()
    config.drain_sim_th = 0.5
    config.drain_depth = 5
    config.drain_max_children = 100

    miner = TemplateMiner(config=config)

    cluster_params: Dict[int, List[List[str]]] = defaultdict(list)
    cluster_services: Dict[int, set] = defaultdict(set)

    for msg, svc in messages:
        masked = _apply_masks(msg)
        result = miner.add_log_message(masked)
        if result and result.get("cluster"):
            cid = result["cluster"].cluster_id
            cluster_params[cid].append(result.get("parameters") or [])
            cluster_services[cid].add(svc)

    templates = []
    for cluster in miner.drain.id_to_cluster.values():
        templates.append({
            "template": cluster.get_template(),
            "count": cluster.size,
            "parameters": list(cluster_params.get(cluster.cluster_id, [])),
            "services": list(cluster_services.get(cluster.cluster_id, set())),
        })

    return sorted(templates, key=lambda t: -t["count"])


# ─── Fallback: simple regex clustering ───────────────────────────────────────

def _extract_fallback(messages: List[tuple]) -> List[Dict[str, Any]]:
    """
    Simple fallback clustering when drain3 is not installed.
    Groups messages by their first 4 words (after masking).
    """
    clusters: Dict[str, Dict] = defaultdict(lambda: {
        "count": 0, "services": set(), "example": ""
    })

    for msg, svc in messages:
        masked = _apply_masks(msg)
        words = masked.split()[:4]
        key = " ".join(words)
        clusters[key]["count"] += 1
        clusters[key]["services"].add(svc)
        if not clusters[key]["example"]:
            clusters[key]["example"] = masked

    result = []
    for key, data in clusters.items():
        result.append({
            "template": data["example"],
            "count": data["count"],
            "parameters": [],
            "services": list(data["services"]),
        })

    return sorted(result, key=lambda t: -t["count"])


# ─── Public function ─────────────────────────────────────────────────────────

def extract_templates(
    log_file_path: str,
    extracted_facts: ExtractedFacts,
) -> ExtractedFacts:
    """
    Stage 2: Mine log templates from the raw log file using Drain3.

    Adds `log_templates` to the `extracted_facts` object in-place and returns it.

    Args:
        log_file_path:    Path to the original log file
        extracted_facts:  Stage 1 output (will be mutated with templates)

    Returns:
        Same ExtractedFacts object with log_templates populated
    """
    start = time.time()
    log_stage_start(extractor_logger, "TEMPLATE_EXTRACTOR", log_file_path)

    # Read and strip prefix from every line
    path = Path(log_file_path)
    if not path.exists():
        extractor_logger.warning(f"Log file not found: {log_file_path}")
        return extracted_facts

    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    extractor_logger.debug(f"   Processing {len(raw_lines)} lines")

    # Build (message, service) pairs for Drain3
    # We need service context so templates know which service they belong to
    _SVC_RE = re.compile(r"^\S+\s+\w+\s+\[([^\]]+)\]")
    msg_svc_pairs: List[tuple] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        svc_m = _SVC_RE.match(line)
        svc = svc_m.group(1) if svc_m else "unknown"
        msg = _strip_prefix(line)
        if msg:
            msg_svc_pairs.append((msg, svc))

    if not msg_svc_pairs:
        extractor_logger.warning("   No parseable messages found for template extraction")
        return extracted_facts

    # Extract templates
    if DRAIN3_AVAILABLE:
        extractor_logger.info("   Using drain3 (tree-sitter-style log mining)")
        try:
            templates = _extract_with_drain3(msg_svc_pairs)
            method = "drain3"
        except Exception as e:
            extractor_logger.warning(f"   drain3 failed ({e}), using fallback")
            templates = _extract_fallback(msg_svc_pairs)
            method = "fallback"
    else:
        templates = _extract_fallback(msg_svc_pairs)
        method = "fallback"

    # Filter: keep templates with count >= 1 (all unique events matter)
    # But limit to 50 templates to bound LLM context
    templates = templates[:50]

    log_extract(
        extractor_logger, "templates", len(templates),
        f"from {len(raw_lines)} lines using {method}"
    )

    # Log a few examples
    for t in templates[:5]:
        extractor_logger.debug(
            f"   Template (×{t['count']}): {t['template'][:100]}"
        )
    if len(templates) > 5:
        extractor_logger.debug(f"   ... and {len(templates) - 5} more templates")

    # Attach to extracted_facts
    extracted_facts.log_templates = templates

    duration_ms = (time.time() - start) * 1000
    log_stage_complete(
        extractor_logger, "TEMPLATE_EXTRACTOR", duration_ms,
        f"{len(templates)} templates"
    )

    return extracted_facts
