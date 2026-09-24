"""
Standalone pipeline tests — exact same initialization as main.py, real LLM calls.

Usage (run from forge/ directory with venv active):
    python test_pipelines.py impact    # Impact Analysis pipeline only
    python test_pipelines.py codegen   # CodeGen pipeline only
    python test_pipelines.py re        # Reverse Engineer pipeline only
    python test_pipelines.py all       # All three

Each test drives the real pipeline end-to-end with real inputs.
No mocks. No browser. No server needed.
"""

import asyncio, sys, time, os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

# ── helpers ──────────────────────────────────────────────────────────────────

def ok(msg):   print(f"  [PASS]  {msg}")
def fail(msg): print(f"  [FAIL]  {msg}")
def info(msg): print(f"          {msg}")

def banner(t):
    print(f"\n{'='*70}\n  {t}\n{'='*70}")

def _init_graph():
    """Load KuzuGraphStore exactly as main.py does."""
    from modules.codegraph.kuzu_store import KuzuCodeGraphStore
    services_path = ROOT.parent / "services"
    kuzu_db_path  = services_path / "codegraph-out" / "code_graph.kuzu"
    assert kuzu_db_path.exists(), f"Kuzu DB missing: {kuzu_db_path}"
    store = KuzuCodeGraphStore(str(kuzu_db_path))
    return store, str(services_path)

# Single shared Kuzu store — only one process can hold the lock at a time
_GRAPH_STORE = None
_SERVICES_PATH = None

def get_graph():
    global _GRAPH_STORE, _SERVICES_PATH
    if _GRAPH_STORE is None:
        _GRAPH_STORE, _SERVICES_PATH = _init_graph()
    return _GRAPH_STORE, _SERVICES_PATH


# ── IMPACT ANALYSIS ───────────────────────────────────────────────────────────

async def test_impact():
    banner("TEST 1 — Impact Analysis Pipeline")
    t0 = time.time()

    store, services_path = get_graph()

    # Same wiring as main.py
    from modules.agents.impact import ImpactAgent
    from modules.codegraph.tools import CodeGraphTools
    from modules.agents import PipelineOrchestrator

    tools = CodeGraphTools(kuzu_store=store, services_path=services_path)
    agent = ImpactAgent(store, tools)
    orch  = PipelineOrchestrator(agent)

    # ── Step 1: start with a realistic change request
    request = "Add rate limiting middleware to the payment-processor service to prevent API abuse"
    info(f"Request: {request!r}")

    state = await orch.start(request)
    info(f"session_id={state.id}  stage={state.stage.value}")

    # ── Step 2: answer any follow-up questions (same as typing in the chat UI)
    MAX_TURNS = 4
    for turn in range(MAX_TURNS):
        if state.stage.value == "requirements_ready":
            break
        q = getattr(state, "current_question", None) or "?"
        info(f"Follow-up Q: {q[:120]}")
        # Give a concrete answer so context gatherer is satisfied
        state = await orch.respond(
            state.id,
            "Fixed window rate limiting, 100 requests per minute per IP address, apply to all endpoints"
        )
        info(f"  → stage={state.stage.value}")

    assert state.stage.value == "requirements_ready", \
        f"Never reached requirements_ready (got {state.stage.value})"
    ok(f"Requirements ready — clarity {state.requirements.get('clarity_score','?')}/10")

    # ── Step 3: confirm (same as clicking 'Confirm & Start Analysis' button)
    info("Confirming requirements and starting analysis...")
    state = await orch.confirm_requirements(state.id)
    info(f"  → stage={state.stage.value}")

    # ── Step 4: poll until awaiting_approval or failed
    DEADLINE = time.time() + 600  # 10 min max
    while state.stage.value not in ("awaiting_approval", "failed"):
        if time.time() > DEADLINE:
            fail("Timed out waiting for analysis"); return False
        await asyncio.sleep(4)
        state = orch.get_state(state.id)
        info(f"  polling… stage={state.stage.value}")

    if state.stage.value == "failed":
        fail(f"Analysis failed: {state.error}"); return False

    ok(f"Analysis complete — stage={state.stage.value} ({time.time()-t0:.0f}s)")

    # ── Step 5: validate outputs
    assert state.report and len(state.report) > 100, "Report is empty!"
    ok(f"Report produced ({len(state.report)} chars)")

    from modules.cache.token_tracker import get_tracker
    snap = get_tracker().snapshot(state.id)
    calls = snap.get("totals", {}).get("calls", 0) if snap else 0
    cost  = snap.get("totals", {}).get("cost_usd", 0) if snap else 0
    if calls:
        ok(f"Token tracking: {calls} LLM calls, ${cost:.4f} USD")
    else:
        fail("Token tracking: no data recorded (non-fatal)")

    ok(f"IMPACT PIPELINE — PASSED ({time.time()-t0:.0f}s)")
    return state  # return state so codegen test can chain it


# ── CODEGEN ───────────────────────────────────────────────────────────────────

async def test_codegen(impact_state=None):
    banner("TEST 2 — CodeGen Pipeline")
    t0 = time.time()

    store, services_path = get_graph()

    from modules.codegen import CodeGenOrchestrator
    orch = CodeGenOrchestrator(store, services_path)

    # Build impact_report in the exact shape produced by Impact Analysis pipeline.
    # If a real state was passed in (from test_impact), use it; otherwise use a
    # realistic hard-coded report that mirrors the real thing.
    if impact_state and getattr(impact_state, "report", None):
        impact_report = {
            "change_request": impact_state.requirements.get("description", "Add retry logic"),
            "report": impact_state.report,
            "requirements": impact_state.requirements,
        }
        info("Using real impact report from test_impact()")
    else:
        impact_report = {
            "change_request": (
                "Add retry logic to the payment-processor service "
                "when calling external services"
            ),
            "report": (
                "════════════════════════════════════════════\n"
                "LAYER 0 — Directly required by the requirement\n"
                "════════════════════════════════════════════\n"
                "SERVICE: [GRAPH] payment-processor [conf: 100%]\n"
                "├── MODIFY function: fetchWithRetry\n"
                "│    WHY: Wrap all outbound HTTP calls with exponential backoff.\n"
                "│    CHANGE: Create src/utils/httpRetry.js with fetchWithRetry().\n"
                "├── MODIFY file: src/clients/accountClient.js\n"
                "│    CHANGE: Replace fetch() with fetchWithRetry().\n"
                "├── MODIFY file: src/clients/auditClient.js\n"
                "│    CHANGE: Replace fetch() with fetchWithRetry().\n"
                "├── MODIFY file: src/clients/fxClient.js\n"
                "│    CHANGE: Replace fetch() with fetchWithRetry().\n"
                "├── MODIFY file: src/clients/ledgerClient.js\n"
                "│    CHANGE: Replace fetch() with fetchWithRetry().\n"
                "└── MODIFY file: src/clients/validationClient.js\n"
                "     CHANGE: Replace fetch() with fetchWithRetry().\n"
                "\n"
                "LAYER 1 — Secondary impact\n"
                "SERVICE: gateway-service\n"
                "└── MODIFY: Handle 503 Retry-Exhausted from payment-processor.\n"
                "\n"
                "SUMMARY: 2 services, 6 files, HIGH confidence.\n"
            ),
            "requirements": {
                "complete": True,
                "clarity_score": 9,
                "description": (
                    "Add exponential backoff retry logic to the payment-processor "
                    "service when calling external services."
                ),
                "services": ["payment-processor"],
                "functions": [],
                "change_type": "add_feature",
                "constraints": [],
            },
        }
        info("Using hard-coded realistic impact report")

    info(f"Starting CodeGen for: {impact_report['requirements']['description'][:80]!r}")

    # ── Step 1: start (Design Agent → plan)
    state = await orch.start(impact_report)
    cg_id = state.id
    info(f"codegen_session={cg_id}  stage={state.stage.value}")

    # ── Step 2: poll through DESIGNING → DISTRIBUTING → IMPLEMENTING → VERIFYING → AWAITING_APPROVAL
    DEADLINE = time.time() + 900   # 15 min (Design Agent alone ~3 min)
    while state.stage.value not in ("awaiting_approval", "failed"):
        if time.time() > DEADLINE:
            fail("Timed out"); return False
        await asyncio.sleep(5)
        state = orch.get_state(cg_id)
        info(f"  polling… stage={state.stage.value}")

    if state.stage.value == "failed":
        fail(f"CodeGen failed: {state.error}"); return False

    ok(f"CodeGen reached awaiting_approval ({time.time()-t0:.0f}s)")

    # ── Step 3: validate diffs
    assert state.diffs, "No diffs produced!"
    ok(f"Diffs: {len(state.diffs)} file(s)")
    for d in state.diffs:
        info(f"    {d.file}  ({len(d.diff)} chars diff)")
        assert d.diff and len(d.diff) > 20, f"Empty diff for {d.file}"
    ok("All diffs non-empty")

    # ── Step 4: token tracking
    from modules.cache.token_tracker import get_tracker
    snap  = get_tracker().snapshot(cg_id)
    calls = snap.get("totals", {}).get("calls", 0) if snap else 0
    cost  = snap.get("totals", {}).get("cost_usd", 0) if snap else 0
    if calls:
        ok(f"Token tracking: {calls} LLM calls, ${cost:.4f} USD")
    else:
        fail("Token tracking: no data (non-fatal)")

    ok(f"CODEGEN PIPELINE — PASSED ({time.time()-t0:.0f}s)")
    return True


# ── REVERSE ENGINEER ──────────────────────────────────────────────────────────

async def test_re():
    banner("TEST 3 — Reverse Engineer Pipeline")
    t0 = time.time()

    # RE orchestrator needs no graph store — same as main.py
    output_dir = ROOT.parent / "reverse-engineer" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    from modules.reverse_engineer import REOrchestrator
    orch = REOrchestrator()

    # Real-looking log from payment-processor (same format as production logs)
    log_bytes = b"""\
2024-01-15T10:00:01.123Z INFO  [payment-processor] POST /payments body={amount:150.00,currency:"USD",accountId:"acc_abc"} 201 Created paymentId=pay_xyz789
2024-01-15T10:00:01.456Z INFO  [payment-processor] Calling account-service GET /accounts/acc_abc 200 OK 23ms
2024-01-15T10:00:01.489Z INFO  [payment-processor] Calling validation-service POST /validate 200 OK 18ms
2024-01-15T10:00:01.512Z INFO  [payment-processor] Calling fx-service GET /rates/USD/EUR 200 OK 31ms rate=0.92
2024-01-15T10:00:01.544Z INFO  [payment-processor] Calling ledger-service POST /ledger/entries 201 Created 44ms
2024-01-15T10:00:01.588Z INFO  [payment-processor] Calling audit-service POST /audit 201 Created 12ms
2024-01-15T10:00:02.000Z INFO  [payment-processor] GET /payments/pay_xyz789 200 OK
2024-01-15T10:00:03.000Z ERROR [payment-processor] POST /payments 422 Unprocessable Entity - {"error":"amount must be positive","field":"amount"}
2024-01-15T10:00:04.000Z WARN  [payment-processor] Calling fx-service GET /rates/GBP/USD 503 Service Unavailable 2012ms - retrying
2024-01-15T10:00:06.100Z ERROR [payment-processor] Payment pay_fail001 failed: fx rate unavailable after 3 retries
2024-01-15T10:00:10.000Z INFO  [payment-processor] GET /health 200 OK
2024-01-15T10:00:15.000Z INFO  [payment-processor] GET /payments?status=pending 200 OK count=5
"""

    info(f"Log size: {len(log_bytes)} bytes")

    # ── Step 1: start (same args as the API route)
    session = await orch.start(
        log_bytes=log_bytes,
        file_name="payment-processor.log",
        user_comments="Production logs from payment-processor service during payment flow"
    )
    sid = session.id
    info(f"re_session={sid}  stage={session.stage}")

    # ── Step 2: poll until complete or failed
    DEADLINE = time.time() + 600
    while session.stage not in ("complete", "failed"):
        if time.time() > DEADLINE:
            fail("Timed out"); return False
        await asyncio.sleep(4)
        session = orch.get_state(sid)
        info(f"  polling… stage={session.stage}")

    if session.stage == "failed":
        fail(f"RE failed: {getattr(session, 'error', 'unknown')}"); return False

    ok(f"RE complete ({time.time()-t0:.0f}s)")

    # ── Step 3: validate spec output
    spec_files = list(output_dir.glob(f"{sid}*"))
    if spec_files:
        ok(f"Spec file(s) on disk: {[f.name for f in spec_files]}")
    # Check in-memory spec sections
    sections = getattr(session, "spec_sections", None) or getattr(session, "spec", None)
    if sections:
        ok(f"Spec sections: {len(sections)}")
        for s in (sections[:3] if isinstance(sections, list) else []):
            title = s.get("title", s.get("section_id", "?")) if isinstance(s, dict) else str(s)[:60]
            info(f"    {title}")
    else:
        info("Spec in DB (not in memory object) — check output dir or /cache")

    # ── Step 4: token tracking
    # The RE orchestrator calls get_tracker().clear() after saving to demo cache,
    # so the live tracker snapshot is empty by this point.
    # Read from the demo cache entry instead.
    try:
        from modules.cache.demo_cache import get_cache
        entry = get_cache().get(sid)
        token_usage = entry.get("token_usage", {}) if entry else {}
        totals = token_usage.get("totals", {})
        calls = totals.get("calls", 0)
        cost  = totals.get("cost_usd", 0)
        if calls:
            ok(f"Token tracking: {calls} LLM calls, ${cost:.4f} USD")
        else:
            fail("Token tracking: no data in cache (non-fatal)")
    except Exception as e:
        fail(f"Token tracking check failed: {e} (non-fatal)")

    ok(f"REVERSE ENGINEER PIPELINE — PASSED ({time.time()-t0:.0f}s)")
    return True


# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    which = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    results = {}

    impact_state = None  # share real impact state into codegen if running both

    if which in ("impact", "all"):
        try:
            r = await test_impact()
            results["impact"] = bool(r)
            if r and r is not True:
                impact_state = r   # PipelineState object
        except Exception as e:
            import traceback; traceback.print_exc()
            fail(f"Impact test crashed: {e}")
            results["impact"] = False

    if which in ("codegen", "all"):
        try:
            results["codegen"] = bool(await test_codegen(impact_state))
        except Exception as e:
            import traceback; traceback.print_exc()
            fail(f"CodeGen test crashed: {e}")
            results["codegen"] = False

    if which in ("re", "all"):
        try:
            results["re"] = bool(await test_re())
        except Exception as e:
            import traceback; traceback.print_exc()
            fail(f"RE test crashed: {e}")
            results["re"] = False

    banner("SUMMARY")
    all_pass = True
    for name, passed in results.items():
        if passed:
            ok(f"{name.upper():10s}  PASS")
        else:
            fail(f"{name.upper():10s}  FAIL")
            all_pass = False

    print()
    if all_pass:
        print("  ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("  SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
