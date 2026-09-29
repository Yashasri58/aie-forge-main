# Apply Diffs → Sync Graph Feature

**What this is:** When a user approves AI-generated code changes in Forge, those changes now actually land on disk, get committed to git, and the live code graph hot-swaps to reflect the new codebase — all automatically, in the background.

---

## The Problem It Solves

Before this feature, approving AI-generated diffs in the UI did nothing to the actual files. The diffs were just shown on screen. The code graph never knew the code changed. There was no history of what the AI touched.

After this feature:
1. Files are **written to disk** atomically (all-or-none)
2. A **git commit** is created with an `AI-Generated-By` trailer
3. The **code graph rebuilds** itself in-process and hot-swaps — no server restart needed

---

## Architecture Overview

```
User clicks Approve
        │
        ▼
CodeGenOrchestrator.approve()
        │
        ├── returns state to API immediately (non-blocking)
        │
        └── asyncio.create_task(_post_approval_sync(state))
                │
                ├── [1] DiffApplier.apply()         ← writes files to disk
                │
                ├── [2] VersionManager.commit()     ← creates git commit
                │
                └── [3] GraphRebuilder.rebuild()    ← hot-swaps code graph
```

Enable with one env var:

```bash
SYNC_GRAPH_ON_APPROVE=true   # in aie-forge-main/forge/.env
```

---

## Component 1 — DiffApplier

**File:** `src/modules/codegen/diff_applier.py`

Applies AI-generated unified diffs to files in the `services/` directory using a two-phase atomic strategy.

### How it works

**Phase 1 — Validate & Test (nothing written to disk yet)**
- Resolves every target path and checks it's under `services/` (path traversal prevention)
- Mirrors the original file into a temp directory with CRLF → LF normalization
- Runs `git apply --whitespace=fix -c core.autocrlf=false -p1` against the temp dir
- If any patch fails → abort the whole batch, return failure

**Phase 2 — Write to disk atomically**
- Snapshots every target file before touching it (pre-write backup)
- Writes all patched files in one pass
- If any single write fails → rolls back every already-written file from the snapshot

### Why `git apply` instead of `patch-ng`

`patch-ng` is strict about context line matching. AI-generated diffs have CRLF/whitespace mismatches that make it fail constantly. `git apply --whitespace=fix` handles all of that with fuzzy matching.

### Windows-specific fixes baked in

Three separate Windows gotchas that would kill a naive implementation:

| Problem | Fix |
|---|---|
| File has CRLF, diff has LF — context match fails | Normalize mirror to LF before writing to temp dir |
| `core.autocrlf=true` in system git config re-adds `\r` | Pass `-c core.autocrlf=false` as a CLI flag (overrides system config) |
| `write_text()` converts `\n` → `\r\n` in the patch file itself | Write patch file with `write_bytes(diff.encode("utf-8"))` instead |

---

## Component 2 — VersionManager

**File:** `src/modules/codegen/version_manager.py`

Every approved run creates a git commit in `services/` with a structured message and git trailers. This is how you track, download, or undo what the AI did.

### Commit format

```
AI codegen: Add rate limiting to payment-service

Forge-State-ID: 8d989fd7-f128-449a-a89b-2a303a280a10
AI-Generated-By: forge-codegen
```

The `AI-Generated-By: forge-codegen` trailer is how `list_versions()` filters the log to only show AI-generated commits (not manual ones).

### Operations

```python
vm = VersionManager(services_root=Path("../services"))

# Create a commit for approved diffs
result = vm.commit(patched_file_paths, state)
# result.commit_hash → "8e034eb35210..."

# List all AI commits (newest first)
versions = vm.list_versions()
# [VersionEntry(short_hash="8e034eb3", message="AI codegen: ...", changed_files=[...])]

# Download the repo state at a specific commit as a zip
zip_bytes = vm.download_version("8e034eb3")

# Revert a specific AI commit (creates a new revert commit)
result = vm.revert_version("8e034eb3")
# result.revert_commit_hash → "a9e7a92e..."
```

### Security

Commit hash inputs are validated against `[0-9a-f]{4,40}` before use in subprocess args — prevents shell injection. Git is invoked via `subprocess.run()` with an explicit args list (never `shell=True`).

---

## Component 3 — GraphRebuilder

**File:** `src/modules/codegen/graph_rebuilder.py`

After files land on disk, the code graph needs to know about them. GraphRebuilder does a full in-process rebuild and hot-swaps all the live globals in `main.py` — the Kuzu store, tools, agents, orchestrators — all in one shot.

### Rebuild sequence

```
Step 1: _rebuild_code() from codegraph-tools
        Re-extracts changed files → writes new combined_extraction.json
        (non-fatal if it fails — falls back to existing extraction)

Step 2 (under asyncio.Lock):
        Close old KuzuCodeGraphStore (releases file lock)
        Delete code_graph.kuzu + code_graph.kuzu.wal (stale WAL causes crash)
        KuzuCodeGraphStore(new) → init_schema()
        HttpLinker → detect service-to-service HTTP calls
        load_extraction() → loads all symbols into Kuzu
        CodeGraphEnricher → packages, DB schemas, API endpoints, env vars
        CodeGraphTools(new) → wraps the new store
        ImpactAgent + PipelineOrchestrator + CodeGenOrchestrator (new instances)

Step 3: set_globals_fn(store, tools, agent, orch, codegen_orch)
        Atomically swaps all Graph_Globals in main.py
        Re-wires all FastAPI router dependencies
```

The `asyncio.Lock` is held during steps 2–3 (~15–20 seconds). Any request that hits a graph-dependent route during that window gets a 503 "Graph updating" response (the lock is short-lived).

### Wiring in main.py

```python
# main.py (inside lifespan)
_graph_lock = asyncio.Lock()

_graph_rebuilder = GraphRebuilder(
    services_root   = services_path,
    kuzu_db_path    = kuzu_db_path,
    extraction_path = extraction_path,
    set_globals_fn  = set_graph_globals,   # ← callback that swaps all globals
    graph_lock      = _graph_lock,
)
_codegen_orchestrator._graph_rebuilder = _graph_rebuilder
```

`set_graph_globals()` is a function in `main.py` that updates `_store`, `_tools`, `_agent`, `_orchestrator`, `_codegen_orchestrator` and re-wires all the router dependencies atomically.

### Windows-specific fixes

| Problem | Fix |
|---|---|
| `_rebuild_code()` prints `→` arrow to console → `charmap` codec crash on cp1252 | Redirect stdout/stderr to `io.StringIO()` during the call, log output via our UTF-8-safe logger |
| `shutil.rmtree()` fails on Kuzu single-file DB | `_safe_delete_kuzu()` checks `is_dir()` vs `is_file()` and uses `unlink()` for files |
| Orphaned `.wal` file from crashed session → `unordered_map` error on next DB open | Also delete `code_graph.kuzu.wal` alongside the main DB file |

---

## API Endpoints

All endpoints live under `/codegen` and require `SYNC_GRAPH_ON_APPROVE=true`.

### List all AI-generated versions

```http
GET /codegen/versions
```

Returns all commits tagged with `AI-Generated-By: forge-codegen`, newest first.

```json
[
  {
    "commit_hash": "8e034eb35210bb20c51d9318ef50747d3c92bf25",
    "short_hash": "8e034eb3",
    "message": "AI codegen: Add rate limiting to payment-service",
    "timestamp": "2026-09-28T15:57:08+05:30",
    "state_id": "7a3612a7-91a8-4df2-9d23-e091c7b1406b",
    "changed_files": ["payment-processor/src/middleware/rateLimit.js"]
  }
]
```

### Download a version as zip

```http
GET /codegen/versions/{commit_hash}/download
```

Streams a `.zip` of the entire `services/` directory at that commit point (using `git archive`). Response has `Content-Disposition: attachment; filename="forge-{short_hash}.zip"`.

### Revert a state

```http
POST /codegen/{state_id}/revert
```

Creates a `git revert` commit that undoes the AI's changes. Also triggers a graph rebuild in the background so the code graph reflects the reverted state.

```json
{
  "status": "reverted",
  "revert_commit": "a9e7a92eed61...",
  "original_commit": "8e034eb35210..."
}
```

---

## State fields added to CodeGenState

```python
state.sync_status     # "applying" | "committing" | "rebuilding" | "complete" | "failed"
state.sync_error      # string error if sync_status == "failed"
state.git_commit_hash # full 40-char SHA of the commit created, or None
```

These are returned in every `GET /codegen/{state_id}` response so the frontend can show sync progress.

---

## Testing Without Running the Full Pipeline

The full code generation pipeline takes 15–20 minutes (LLM calls for design, implementation, verification). There's a fast test script that bypasses all of that and exercises the sync chain directly:

```bash
cd aie-forge-main/forge
python test_sync_direct.py
```

It creates a synthetic approved state with a real diff (appends a comment to `account-service/src/index.js`), calls `_post_approval_sync` directly, and checks:

- Was the file written to disk?
- Does the git log in `services/` show a new commit?
- Did the GraphRebuilder swap in a new store?

Runs in ~20 seconds. Clean slate: after each successful test run, the test commit can be reverted with `git -C services/ revert HEAD --no-edit`.

---

## File Map

```
aie-forge-main/forge/
│
├── src/modules/codegen/
│   ├── diff_applier.py       ← Phase 1/2 atomic patch application (git apply)
│   ├── version_manager.py    ← git commit / list / download / revert
│   ├── graph_rebuilder.py    ← Kuzu teardown → rebuild → hot-swap
│   ├── orchestrator.py       ← _post_approval_sync() wires all three together
│   └── schemas.py            ← sync_status, sync_error, git_commit_hash fields
│
├── src/interfaces/api/
│   └── codegen_routes.py     ← GET /codegen/versions
│                                GET /codegen/versions/{hash}/download
│                                POST /codegen/{id}/revert
│
├── main.py                   ← set_graph_globals(), _graph_lock, GraphRebuilder wiring
├── test_sync_direct.py       ← fast end-to-end test (no full pipeline)
└── .env                      ← SYNC_GRAPH_ON_APPROVE=true
```

---

## Sequence Diagram

```
User                  API            Orchestrator    DiffApplier   VersionManager  GraphRebuilder
 │                     │                  │               │               │               │
 │── POST /approve ───>│                  │               │               │               │
 │                     │── approve() ────>│               │               │               │
 │                     │<── state dict ───│               │               │               │
 │<── 200 OK ──────────│                  │               │               │               │
 │                     │           (background task)      │               │               │
 │                     │                  │── apply() ───>│               │               │
 │                     │                  │               │ (git apply)   │               │
 │                     │                  │               │── write ─────>│               │
 │                     │                  │<── success ───│               │               │
 │                     │                  │── commit() ──────────────────>│               │
 │                     │                  │<── hash ──────────────────────│               │
 │                     │                  │── rebuild() ─────────────────────────────────>│
 │                     │                  │                               │  (close Kuzu) │
 │                     │                  │                               │  (delete .kuzu│
 │                     │                  │                               │  + .wal)      │
 │                     │                  │                               │  (reload      │
 │                     │                  │                               │  extraction)  │
 │                     │                  │                               │  (set_globals)│
 │                     │                  │<── complete ──────────────────────────────────│
```
