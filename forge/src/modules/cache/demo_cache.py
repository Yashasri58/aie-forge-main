"""
Demo Cache — SQLite-backed store for pipeline inputs and outputs.

Purpose: during live demos the full pipeline takes 3–10 minutes.
This cache lets you run once, save the result, then replay instantly.

Schema (single table):
    demo_cache(id, pipeline_type, label, input_hash, input_json,
               output_json, created_at, last_used_at, use_count)

Usage:
    cache = DemoCache()

    # Save
    cache.save("my-demo", "impact", label="Circuit Breaker", input=req, output=state)

    # Restore (returns dict or None)
    entry = cache.get("my-demo")

    # List all
    entries = cache.list()

    # Auto-key from input hash (dedup identical runs)
    entry = cache.find_by_input("impact", input_dict)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("forge.cache")

# DB lives next to forge_sessions.db at the project root
_DB_PATH = Path(__file__).resolve().parents[4] / "forge_demo_cache.db"


# ─── Schema ──────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS demo_cache (
    id           TEXT PRIMARY KEY,
    pipeline_type TEXT NOT NULL,
    label        TEXT NOT NULL,
    input_hash   TEXT NOT NULL,
    input_json   TEXT NOT NULL,
    output_json  TEXT NOT NULL,
    created_at   REAL NOT NULL,
    last_used_at REAL NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pipeline ON demo_cache(pipeline_type);
CREATE INDEX IF NOT EXISTS idx_hash     ON demo_cache(input_hash);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init():
    with _connect() as conn:
        conn.executescript(_DDL)


# ─── DemoCache class ─────────────────────────────────────────────────────────

class DemoCache:
    """
    SQLite-backed demo cache.
    Thread-safe for reads; writes use WAL mode.
    """

    def __init__(self):
        _init()
        _log.info(f"[CACHE] DemoCache ready — {_DB_PATH}")

    # ── Write ─────────────────────────────────────────────────────────────

    def save(
        self,
        cache_id: str,
        pipeline_type: str,
        label: str,
        input_data: Any,
        output_data: Any,
    ) -> None:
        """
        Save (upsert) a pipeline result to cache.

        Args:
            cache_id:      Unique key, e.g. "circuit-breaker-fx"
            pipeline_type: "impact" | "codegen" | "reverse_engineer"
            label:         Human-readable demo label
            input_data:    Raw input (dict/str — will be JSON-serialised)
            output_data:   Pipeline output (dict — will be JSON-serialised)
        """
        input_json = json.dumps(input_data, default=str)
        output_json = json.dumps(output_data, default=str)
        input_hash = _hash(input_json)
        now = time.time()

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO demo_cache
                    (id, pipeline_type, label, input_hash, input_json,
                     output_json, created_at, last_used_at, use_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET
                    label        = excluded.label,
                    input_hash   = excluded.input_hash,
                    input_json   = excluded.input_json,
                    output_json  = excluded.output_json,
                    last_used_at = excluded.last_used_at
                """,
                (cache_id, pipeline_type, label, input_hash,
                 input_json, output_json, now, now),
            )
        _log.info(f"[CACHE] Saved: id={cache_id!r} type={pipeline_type} label={label!r}")

    # ── Read ──────────────────────────────────────────────────────────────

    def get(self, cache_id: str) -> Optional[Dict]:
        """
        Fetch a cache entry by ID.
        Increments use_count and updates last_used_at.
        Returns None if not found.
        """
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_cache WHERE id = ?", (cache_id,)
            ).fetchone()
            if not row:
                _log.debug(f"[CACHE] MISS: {cache_id!r}")
                return None
            conn.execute(
                "UPDATE demo_cache SET use_count = use_count+1, last_used_at=? WHERE id=?",
                (time.time(), cache_id),
            )
        entry = _row_to_dict(row)
        _log.info(f"[CACHE] HIT:  id={cache_id!r} label={entry['label']!r} use_count={entry['use_count']+1}")
        return entry

    def find_by_input(self, pipeline_type: str, input_data: Any) -> Optional[Dict]:
        """
        Find a cached result by hashing the input.
        Useful for automatic dedup — same request → instant replay.
        """
        input_hash = _hash(json.dumps(input_data, default=str))
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_cache WHERE pipeline_type=? AND input_hash=? LIMIT 1",
                (pipeline_type, input_hash),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE demo_cache SET use_count = use_count+1, last_used_at=? WHERE id=?",
                (time.time(), row["id"]),
            )
        entry = _row_to_dict(row)
        _log.info(f"[CACHE] HIT (by input hash): id={entry['id']!r} label={entry['label']!r}")
        return entry

    def list(self, pipeline_type: Optional[str] = None) -> List[Dict]:
        """List all cache entries, optionally filtered by pipeline type."""
        with _connect() as conn:
            if pipeline_type:
                rows = conn.execute(
                    "SELECT * FROM demo_cache WHERE pipeline_type=? ORDER BY created_at DESC",
                    (pipeline_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM demo_cache ORDER BY created_at DESC"
                ).fetchall()
        entries = [_row_to_dict(r) for r in rows]
        _log.debug(f"[CACHE] List: {len(entries)} entries (filter={pipeline_type!r})")
        return entries

    # ── Delete ────────────────────────────────────────────────────────────

    def delete(self, cache_id: str) -> bool:
        """Delete a single cache entry. Returns True if it existed."""
        with _connect() as conn:
            cur = conn.execute("DELETE FROM demo_cache WHERE id=?", (cache_id,))
        deleted = cur.rowcount > 0
        if deleted:
            _log.info(f"[CACHE] Deleted: {cache_id!r}")
        return deleted

    def clear(self, pipeline_type: Optional[str] = None) -> int:
        """Clear all (or filtered) cache entries. Returns count deleted."""
        with _connect() as conn:
            if pipeline_type:
                cur = conn.execute(
                    "DELETE FROM demo_cache WHERE pipeline_type=?", (pipeline_type,)
                )
            else:
                cur = conn.execute("DELETE FROM demo_cache")
        _log.info(f"[CACHE] Cleared {cur.rowcount} entries (filter={pipeline_type!r})")
        return cur.rowcount

    # ── Stats ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        """Return summary statistics."""
        with _connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM demo_cache").fetchone()[0]
            by_type = conn.execute(
                "SELECT pipeline_type, COUNT(*) as n FROM demo_cache GROUP BY pipeline_type"
            ).fetchall()
        return {
            "total": total,
            "by_type": {r["pipeline_type"]: r["n"] for r in by_type},
            "db_path": str(_DB_PATH),
        }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _row_to_dict(row: sqlite3.Row) -> Dict:
    d = dict(row)
    # Deserialise JSON blobs
    d["input"] = json.loads(d.pop("input_json", "{}"))
    d["output"] = json.loads(d.pop("output_json", "{}"))
    return d


# ─── Module-level singleton ───────────────────────────────────────────────────

_cache: Optional[DemoCache] = None


def get_cache() -> DemoCache:
    """Return the module-level DemoCache singleton."""
    global _cache
    if _cache is None:
        _cache = DemoCache()
    return _cache
