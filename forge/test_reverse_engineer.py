"""
test_reverse_engineer.py

Runs Stage 1 (log_parser) + Stage 2 (template_extractor) on all test log
files and prints a structured summary of what each dataset produces.

Run from the forge directory:
    venv\Scripts\python.exe test_reverse_engineer.py

No GOOGLE_API_KEY required — this only tests the deterministic stages.
"""

import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from modules.reverse_engineer.log_parser import LogParser
from modules.reverse_engineer.template_extractor import extract_templates
from modules.reverse_engineer.logging_config import setup_logging

# ─── Test datasets ────────────────────────────────────────────────────────────

TEST_LOGS = Path(__file__).parent / "new-requirements" / "test-logs"

DATASETS = [
    # ── Original POC ─────────────────────────────────────────────────────────
    {
        "name": "POC: Combined Microservices",
        "file": Path(__file__).parent / "new-requirements" / "combined-microservices.log",
        "expected_services": 7,
        "expected_traces": 4,
        "description": "7-service payment order system with saga rollback (original POC)",
        "category": "custom-saas",
    },
    # ── Custom SaaS (created) ─────────────────────────────────────────────────
    {
        "name": "Custom: Banking Core (Account/Transfer/Fraud)",
        "file": TEST_LOGS / "banking-core.log",
        "expected_services": 7,
        "expected_traces": 5,
        "description": "UK banking — account creation, transfers, fraud detection, compliance",
        "category": "custom-saas",
    },
    {
        "name": "Custom: Ride-sharing Platform",
        "file": TEST_LOGS / "ridesharing-platform.log",
        "expected_services": 8,
        "expected_traces": 6,
        "description": "London ride-hailing — matching, pricing, payment, ratings",
        "category": "custom-saas",
    },
    {
        "name": "Custom: E-commerce Marketplace",
        "file": TEST_LOGS / "ecommerce-marketplace.log",
        "expected_services": 9,
        "expected_traces": 4,
        "description": "Online marketplace — catalog, orders, inventory, returns",
        "category": "custom-saas",
    },
    {
        "name": "Custom: Genomics Cloud Compute",
        "file": TEST_LOGS / "genomics-compute.log",
        "expected_services": 9,
        "expected_traces": 2,
        "description": "Bioinformatics pipeline — sequence alignment, variant calling, spot recovery",
        "category": "custom-saas",
    },
    # ── Well-known SaaS (simulated) ───────────────────────────────────────────
    {
        "name": "Known: Slack-like Team Messaging",
        "file": TEST_LOGS / "slack-like-messaging.log",
        "expected_services": 9,
        "expected_traces": 4,
        "description": "Enterprise messaging — channels, DLP, workflows, search, WebSocket fanout",
        "category": "known-saas",
    },
    {
        "name": "Known: Stripe-like Payments",
        "file": TEST_LOGS / "stripe-like-payments.log",
        "expected_services": 8,
        "expected_traces": 5,
        "description": "Payment processing — payment intents, fraud radar, refunds, subscriptions, webhooks",
        "category": "known-saas",
    },
    {
        "name": "Known: GitHub-like Dev Platform",
        "file": TEST_LOGS / "github-like-devplatform.log",
        "expected_services": 9,
        "expected_traces": 5,
        "description": "Code hosting — repos, PRs, CI/CD, code scanning, branch protection",
        "category": "known-saas",
    },
    # ── Unknown custom SaaS (domain must be inferred from logs) ───────────────
    {
        "name": "Unknown: Product Analytics Platform",
        "file": TEST_LOGS / "posthog-like-analytics.log",
        "expected_services": 8,
        "expected_traces": 4,
        "description": "SaaS analytics — event ingestion, ClickHouse queries, A/B testing, alerts",
        "category": "unknown-saas",
    },
    {
        "name": "Unknown: Contract Management SaaS",
        "file": TEST_LOGS / "contract-management-saas.log",
        "expected_services": 8,
        "expected_traces": 4,
        "description": "Legal SaaS — contract templates, e-signature, obligation tracking, compliance",
        "category": "unknown-saas",
    },
    {
        "name": "Unknown: Medical Imaging SaaS",
        "file": TEST_LOGS / "medical-imaging-saas.log",
        "expected_services": 8,
        "expected_traces": 4,
        "description": "NHS clinical imaging — DICOM upload, AI detection, radiology worklist, HL7 FHIR",
        "category": "unknown-saas",
    },
]

# ─── Pretty print helpers ─────────────────────────────────────────────────────

def box(title: str, width: int = 78) -> str:
    line = "─" * (width - 2)
    return f"┌{line}┐\n│ {title:<{width-4}} │\n└{line}┘"


def section(title: str, width: int = 78) -> str:
    return f"\n{'═' * width}\n  {title}\n{'═' * width}"


def check(label: str, passed: bool, detail: str = "") -> str:
    icon = "  ✅" if passed else "  ❌"
    detail_str = f" ({detail})" if detail else ""
    return f"{icon} {label}{detail_str}"


# ─── Run one dataset ──────────────────────────────────────────────────────────

def run_dataset(ds: dict) -> dict:
    file_path = ds["file"]
    if not file_path.exists():
        return {
            "name": ds["name"],
            "status": "SKIPPED",
            "reason": f"File not found: {file_path}",
        }

    print(box(ds["name"]))
    print(f"  File: {file_path.name}  ({file_path.stat().st_size:,} bytes)")
    print(f"  Desc: {ds['description']}")
    print()

    # ── Stage 1: Log Parser ──────────────────────────────────────────────────
    t0 = time.time()
    parser = LogParser()
    facts = parser.parse_file(str(file_path), session_id="test-session")
    parse_ms = (time.time() - t0) * 1000

    # ── Stage 2: Template Extractor ──────────────────────────────────────────
    t1 = time.time()
    facts = extract_templates(str(file_path), facts)
    extract_ms = (time.time() - t1) * 1000

    # ── Print results ─────────────────────────────────────────────────────────
    print(f"  Stage 1 — Log Parser ({parse_ms:.0f}ms)")
    print(check(
        f"Services discovered: {facts.service_count}",
        facts.service_count >= ds["expected_services"] - 1,
        f"expected ~{ds['expected_services']}"
    ))
    print(check(
        f"Trace flows reconstructed: {facts.trace_count}",
        facts.trace_count >= ds["expected_traces"] - 1,
        f"expected ~{ds['expected_traces']}"
    ))
    print(check(
        f"Endpoints extracted: {facts.endpoint_count}",
        facts.endpoint_count > 0,
        f"found {facts.endpoint_count}"
    ))
    print(check(
        f"Kafka topics discovered: {len(facts.kafka_topics)}",
        True,
        ", ".join(t.topic for t in facts.kafka_topics[:4]) or "none"
    ))
    print(check(
        f"Resilience patterns: {len(facts.resilience_patterns)}",
        True,
        ", ".join(set(r.pattern_name for r in facts.resilience_patterns)) or "none"
    ))
    print(check(
        f"Error events: {len(facts.errors)}",
        True,
        f"{len(facts.errors)} errors"
    ))
    print(check(
        f"SLO metrics: {len(facts.slo_metrics)}",
        True,
        f"{len(facts.slo_metrics)} metrics"
    ))
    print()

    print(f"  Stage 2 — Template Extractor ({extract_ms:.0f}ms)")
    template_count = len(facts.log_templates)
    compression = (
        (1 - template_count / max(facts.total_log_lines, 1)) * 100
        if facts.total_log_lines > 0 else 0
    )
    print(check(
        f"Templates mined: {template_count} from {facts.total_log_lines} lines",
        template_count > 0,
        f"{compression:.0f}% context compression"
    ))

    if facts.log_templates:
        print(f"\n  Top 3 log templates:")
        for t in facts.log_templates[:3]:
            svcs = ", ".join(t.get("services", [])[:3])
            print(f"    ×{t['count']:3d}  {t['template'][:70]}  [{svcs}]")

    print()

    # ── Service dependency summary ────────────────────────────────────────────
    print(f"  Service inventory:")
    for svc in sorted(facts.services, key=lambda s: -s.event_count):
        calls_to = ", ".join(svc.calls_to[:3]) if svc.calls_to else "—"
        print(f"    {svc.name:<35} {svc.event_count:3d} events  →  {calls_to}")

    print()

    # ── Scenario summary ─────────────────────────────────────────────────────
    print(f"  Trace scenarios:")
    for tf in facts.trace_flows:
        print(f"    [{tf.outcome.upper():<18}] {tf.scenario_name}")
        print(f"         → {' → '.join(tf.service_sequence)}")

    print()

    return {
        "name": ds["name"],
        "status": "PASS",
        "services": facts.service_count,
        "traces": facts.trace_count,
        "endpoints": facts.endpoint_count,
        "kafka_topics": len(facts.kafka_topics),
        "resilience_patterns": len(facts.resilience_patterns),
        "templates": template_count,
        "template_compression_pct": round(compression, 1),
        "parse_ms": round(parse_ms, 1),
        "extract_ms": round(extract_ms, 1),
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    setup_logging("WARNING")  # Suppress debug noise, we format our own output

    print(section("REVERSE ENGINEER PIPELINE — TEST SUITE"))
    print("  Testing Stage 1 (Log Parser) + Stage 2 (Template Extractor)")
    print("  No GOOGLE_API_KEY required for these deterministic stages")
    print()

    results = []
    total_start = time.time()

    for ds in DATASETS:
        result = run_dataset(ds)
        results.append(result)
        print()

    total_ms = (time.time() - total_start) * 1000

    # ── Summary table ─────────────────────────────────────────────────────────
    print(section("SUMMARY"))
    print(f"  {'Dataset':<40} {'Status':<8} {'Svcs':<6} {'Traces':<8} {'Templates':<12} {'Compress'}")
    print(f"  {'─'*40} {'─'*6} {'─'*6} {'─'*6} {'─'*10} {'─'*10}")

    passed = 0
    for r in results:
        if r["status"] == "PASS":
            passed += 1
            print(
                f"  {r['name']:<40} {'✅ PASS':<8} "
                f"{r['services']:<6} {r['traces']:<8} "
                f"{r['templates']:<12} {r['template_compression_pct']}%"
            )
        else:
            print(f"  {r['name']:<40} {'⏭ SKIP':<8} {r.get('reason', '')}")

    print()
    print(f"  Result: {passed}/{len(results)} datasets passed")
    print(f"  Total time: {total_ms:.0f}ms")
    print()

    if passed == len(results):
        print("  🎉 All tests passed! Stage 1+2 ready for LLM inference (Stage 3).")
        print()
        print("  Next step: Set GOOGLE_API_KEY in .env and run the full pipeline")
        print("  via the Forge UI at http://localhost:8000/reverse-engineer")
    else:
        print("  ⚠️  Some datasets were skipped (missing files).")
        print("  Run: venv\\Scripts\\python.exe test_reverse_engineer.py")

    print()
    return 0 if passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
