"""
backfill_tokens.py — Re-run old impact cache entries via the live server API
to backfill real token usage.

Calls the running server at http://localhost:8000, submits each old impact entry
as a new pipeline, waits for completion, and approves — which overwrites the
cache entry with real token data.

Usage:
    python backfill_tokens.py
"""

import asyncio
import time
import sys
import json
from pathlib import Path
import urllib.request
import urllib.error


BASE = "http://localhost:8000"


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as r:
        return json.loads(r.read())


def _post(path: str, body: dict = None, timeout: int = 30) -> dict:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _delete(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def wait_for_stage(pipeline_id: str, target_stages: list, timeout_s: int = 300) -> dict:
    """Poll pipeline until it reaches one of target_stages."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = _get(f"/pipeline/{pipeline_id}")
        stage = state.get("stage", "")
        if stage in target_stages:
            return state
        if stage in ("failed", "rejected"):
            raise RuntimeError(f"Pipeline failed: {state.get('error', stage)}")
        time.sleep(3)
    raise TimeoutError(f"Pipeline {pipeline_id} didn't reach {target_stages} in {timeout_s}s")


async def backfill():
    print("Fetching cache entries...")
    entries = _get("/cache")
    to_backfill = [
        e for e in entries
        if e["pipeline_type"] == "impact"
        and not (e.get("token_usage") or {}).get("totals", {}).get("calls", 0)
    ]

    print(f"Found {len(to_backfill)} impact entries without token data\n")
    if not to_backfill:
        print("Nothing to backfill — all entries already have token data.")
        return

    # Fetch full details for each entry to get the input/description
    full_entries = []
    for e in to_backfill:
        try:
            full = _get(f"/cache/{e['id']}")
            full_entries.append(full)
        except Exception as ex:
            print(f"  Could not fetch {e['id'][:8]}: {ex}")

    success = 0
    failed = 0

    for i, entry in enumerate(full_entries):
        label = entry["label"][:55]
        req = entry.get("input") or {}
        description = req.get("description", "") if isinstance(req, dict) else ""

        if not description:
            print(f"  [{i+1}/{len(to_backfill)}] SKIP (no description): {label}")
            continue

        print(f"  [{i+1}/{len(to_backfill)}] {label}")
        old_id = entry["id"]

        try:
            # 1. Start pipeline — inject the full requirements dict directly
            # by starting with the complete description and confirming immediately
            state = _post("/pipeline/start", {"message": description}, timeout=120)
            pipe_id = state["id"]

            # Wait for gathering/requirements_ready
            state = wait_for_stage(pipe_id, ["requirements_ready", "awaiting_approval"], timeout_s=180)

            # If still gathering, respond with the full description + services to force completion
            attempts = 0
            while state["stage"] == "gathering" and attempts < 3:
                services = req.get("services", [])
                svc_str = ", ".join(services) if services else "auto"
                state = _post(f"/pipeline/{pipe_id}/respond",
                              {"message": f"Yes. Target services: {svc_str}. Proceed."}, timeout=60)
                state = wait_for_stage(pipe_id, ["requirements_ready", "awaiting_approval"], timeout_s=120)
                attempts += 1

            # 3. Confirm requirements → starts analysis
            if state["stage"] == "requirements_ready":
                _post(f"/pipeline/{pipe_id}/confirm", timeout=30)

            # 4. Wait for analysis (up to 5 minutes)
            print(f"       Analyzing... (pipeline {pipe_id[:8]})")
            state = wait_for_stage(pipe_id, ["awaiting_approval"], timeout_s=600)

            # 5. Approve — this triggers cache.save() with token data, using the NEW pipeline ID
            _post(f"/pipeline/{pipe_id}/approve", {"approved": True}, timeout=30)

            # 6. Read token data from new entry
            new_entry = _get(f"/cache/{pipe_id}")
            totals = new_entry.get("token_usage", {}).get("totals", {})
            calls = totals.get("calls", 0)

            if calls > 0:
                print(f"       ✅ {totals['input_tokens']:,} in · {totals['output_tokens']:,} out · ${totals['cost_usd']:.4f}")
                # Delete old entry (no tokens) if it's a different ID
                if pipe_id != old_id:
                    try:
                        _delete(f"/cache/{old_id}")
                        print(f"       🗑  Removed old entry {old_id[:8]}")
                    except Exception:
                        pass
                success += 1
            else:
                print(f"       ⚠️  No tokens captured")
                failed += 1

        except Exception as e:
            print(f"       ❌ Error: {e}")
            failed += 1

        # Pause between runs to avoid rate limiting
        if i < len(full_entries) - 1:
            print(f"       Waiting 3s before next run...")
            await asyncio.sleep(3)

    print(f"\n{'='*50}")
    print(f"Done. ✅ {success} backfilled, ❌ {failed} failed")
    print("Refresh http://localhost:8000 to see token data on all entries.")


if __name__ == "__main__":
    asyncio.run(backfill())
