"""
Direct test of the apply-diffs-sync-graph feature.
Bypasses the full pipeline — creates a synthetic approved state
with real diffs and calls _post_approval_sync directly.

Tests the full chain:
  1. DiffApplier — writes file to disk atomically
  2. VersionManager — git commit in services/
  3. GraphRebuilder — re-indexes services/, hot-swaps Kuzu store

Run: python test_sync_direct.py
"""
import sys, os, asyncio, difflib, logging
from pathlib import Path

# Force sync enabled
os.environ["SYNC_GRAPH_ON_APPROVE"] = "true"

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# Enable all logging so we see exactly what happens
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

ROOT     = Path(__file__).parent
SERVICES = ROOT.parent / "services"

KUZU_DB_PATH     = SERVICES / "codegraph-out" / "code_graph.kuzu"
EXTRACTION_PATH  = SERVICES / "codegraph-out" / "combined_extraction.json"


def make_diff(original: str, patched: str, filepath: str) -> str:
    """Generate a unified diff."""
    orig_lines = original.splitlines(keepends=True)
    new_lines  = patched.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, new_lines,
        fromfile=f"a/{filepath}", tofile=f"b/{filepath}"
    ))
    return "".join(diff)


# Track what the GraphRebuilder hands back so we can print it
_rebuilt_store = None
_rebuilt_tools = None

def _test_set_globals(store, tools, agent, orch, codegen_orch):
    """Simulates main.py's set_graph_globals — just captures the new objects."""
    global _rebuilt_store, _rebuilt_tools
    _rebuilt_store = store
    _rebuilt_tools = tools
    print(f"  [set_globals] store={type(store).__name__} "
          f"tools={type(tools).__name__ if tools else None} "
          f"symbols={len(tools.all_symbols) if tools else 'N/A'}")


async def main():
    print("=" * 60)
    print("DIRECT SYNC TEST — bypasses full pipeline")
    print("=" * 60)

    # 1. Check services dir exists
    if not SERVICES.exists():
        print(f"FAIL: services/ not found at {SERVICES}")
        return

    # 2. Find a real file to patch
    target_file = SERVICES / "account-service" / "src" / "index.js"
    if not target_file.exists():
        print(f"FAIL: target file not found: {target_file}")
        return

    original = target_file.read_text(encoding="utf-8")
    patched  = original + "\n// Added by Forge AI test\n"
    diff_text = make_diff(original, patched, "account-service/src/index.js")

    print(f"\n[1] Target file:    {target_file}")
    print(f"[2] Diff length:    {len(diff_text)} chars")
    print(f"[3] kuzu_db_path:   {KUZU_DB_PATH}")
    print(f"[4] extraction:     {EXTRACTION_PATH} (exists={EXTRACTION_PATH.exists()})")

    if not EXTRACTION_PATH.exists():
        print("FAIL: combined_extraction.json not found — run the server once first to build it")
        return

    # 3. Create a minimal fake state
    from modules.codegen.schemas import CodeGenState, AgentOutput, CodeGenStage

    state = CodeGenState.create({
        "change_request": "Test sync: add comment to index.js",
        "pipeline_id": "test-direct-sync"
    })
    state.stage = CodeGenStage.APPROVED

    fake_diff = AgentOutput(
        task_id="test-task-1",
        file="account-service/src/index.js",
        diff=diff_text,
        status="success",
    )
    state.diffs = [fake_diff]

    print(f"\n[5] Created fake state: {state.id}")
    print(f"[6] SYNC_GRAPH_ON_APPROVE: {os.getenv('SYNC_GRAPH_ON_APPROVE')}")

    from modules.codegen.orchestrator import _sync_enabled
    print(f"[7] _sync_enabled(): {_sync_enabled()}")

    # 4. Wire up a real GraphRebuilder
    from modules.codegen.graph_rebuilder import GraphRebuilder

    graph_lock = asyncio.Lock()
    rebuilder = GraphRebuilder(
        services_root   = SERVICES,
        kuzu_db_path    = KUZU_DB_PATH,
        extraction_path = EXTRACTION_PATH,
        set_globals_fn  = _test_set_globals,
        graph_lock      = graph_lock,
    )
    print(f"[8] GraphRebuilder wired (services_root={SERVICES})")

    # 5. Build the orchestrator with the real rebuilder attached
    class MinimalOrchestrator:
        _services_path    = str(SERVICES)
        _graph_rebuilder  = rebuilder          # ← real GraphRebuilder

        async def _post_approval_sync(self, state):
            from modules.codegen.orchestrator import CodeGenOrchestrator
            await CodeGenOrchestrator._post_approval_sync(self, state)

    orch = MinimalOrchestrator()

    print("\n[9] Calling _post_approval_sync (diff + git commit + graph rebuild)...")
    try:
        await orch._post_approval_sync(state)
    except Exception as e:
        import traceback
        print(f"EXCEPTION in _post_approval_sync: {e}")
        traceback.print_exc()
        return

    # 6. Print results
    print(f"\n{'='*60}")
    print(f"[10] sync_status: {state.sync_status}")
    print(f"[11] sync_error:  {state.sync_error}")
    print(f"[12] git_commit:  {state.git_commit_hash}")
    print(f"\n[13] Activity log:")
    for entry in state.activity_log:
        print(f"     [{entry['level'].upper():7}] {entry['message']}")

    # 7. Check file on disk
    current = target_file.read_text(encoding="utf-8")
    print()
    if current != original:
        print(f"[OK] FILE CHANGED on disk!")
        print(f"     Before: {len(original)} chars")
        print(f"     After:  {len(current)} chars")
        print(f"     Last 2 lines: {current.splitlines()[-2:]}")
    else:
        print(f"[FAIL] File was NOT changed on disk")

    # 8. Check graph rebuild
    if _rebuilt_tools is not None:
        print(f"\n[OK] GRAPH REBUILT — {len(_rebuilt_tools.all_symbols)} symbols loaded")
    else:
        print(f"\n[INFO] Graph not rebuilt (check activity log above)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
