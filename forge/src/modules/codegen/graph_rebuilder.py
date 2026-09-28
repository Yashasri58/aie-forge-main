"""
GraphRebuilder — In-process incremental code graph rebuild + hot-swap.

After DiffApplier writes files to disk, GraphRebuilder:
1. Runs _rebuild_code() from codegraph-tools (incremental — only changed files re-parsed)
2. Closes the live Kuzu store (releases file lock)
3. Deletes the stale code_graph.kuzu directory
4. Reinitializes the full graph pipeline (KuzuStore → HttpLinker → Enricher → tools → agents)
5. Atomically swaps all Graph_Globals in main.py via the set_globals_fn callback
6. Releases the asyncio.Lock so other requests can proceed

The asyncio.Lock is held for ~5–10 seconds during steps 2–5. While locked,
graph-dependent routes should return 503 "Graph updating, retry in a moment."

On any exception: logs the error, leaves old globals in place, returns failure result.
The server never crashes due to a failed rebuild.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class RebuildResult:
    success: bool
    symbol_count: int = 0
    duration_ms: float = 0.0
    error: str = ""


class GraphRebuilder:
    """
    Rebuilds the code graph after diffs are applied to services/.

    Args:
        services_root:    Path to services/ directory
        kuzu_db_path:     Path to services/codegraph-out/code_graph.kuzu
        extraction_path:  Path to services/codegraph-out/combined_extraction.json
        set_globals_fn:   Callable(store, tools, agent, orch, codegen_orch) —
                          updates Graph_Globals in main.py after rebuild
        graph_lock:       asyncio.Lock shared with main.py; held during hot-swap
    """

    def __init__(
        self,
        services_root: Path,
        kuzu_db_path: Path,
        extraction_path: Path,
        set_globals_fn: Callable,
        graph_lock: asyncio.Lock,
    ) -> None:
        self._services_root = services_root.resolve()
        self._kuzu_db_path  = kuzu_db_path.resolve()
        self._extraction_path = extraction_path.resolve()
        self._set_globals = set_globals_fn
        self._lock = graph_lock

    async def rebuild(self, state=None) -> RebuildResult:
        """
        Full incremental graph rebuild and hot-swap.

        Args:
            state: Optional CodeGenState for activity log entries.

        Returns:
            RebuildResult indicating success/failure and symbol count.
        """
        start = time.time()

        def _log(msg: str, level: str = "info") -> None:
            if level == "error":
                logger.error(f"[GraphRebuilder] {msg}")
            else:
                logger.info(f"[GraphRebuilder] {msg}")
            if state and hasattr(state, "log"):
                state.log(msg, level)

        # ── Step 1: codegraph-tools incremental rebuild ────────────────────
        _log("Running codegraph incremental extraction...")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._run_codegraph_rebuild
            )
            _log("Codegraph extraction complete")
        except Exception as e:
            _log(f"codegraph rebuild failed: {e}", "error")
            return RebuildResult(success=False, error=str(e))

        # ── Steps 2–6: close old store, reinit, hot-swap (under lock) ─────
        _log("Acquiring graph lock for hot-swap...")
        async with self._lock:
            _log("Hot-swap: closing old Kuzu store...")
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._reinit_graph
                )
            except Exception as e:
                _log(f"Graph reinit failed: {e}", "error")
                return RebuildResult(
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - start) * 1000,
                )

        duration_ms = (time.time() - start) * 1000
        _log(f"Graph rebuild complete — {result['symbol_count']} symbols loaded ({duration_ms:.0f}ms)")
        return RebuildResult(
            success=True,
            symbol_count=result["symbol_count"],
            duration_ms=duration_ms,
        )

    # ─── codegraph-tools rebuild ──────────────────────────────────────────────

    def _run_codegraph_rebuild(self) -> None:
        """
        Run _rebuild_code() from codegraph.watch.
        This re-extracts only changed files (cache-based) and writes a new
        combined_extraction.json + graph.json.
        """
        try:
            from codegraph.watch import _rebuild_code
            ok = _rebuild_code(self._services_root)
            if not ok:
                raise RuntimeError("_rebuild_code() returned False")
        except ImportError:
            # codegraph-tools not installed — skip this step, use existing extraction
            logger.warning("[GraphRebuilder] codegraph-tools not available — using existing extraction")

    # ─── Kuzu reinit ─────────────────────────────────────────────────────────

    def _reinit_graph(self) -> dict:
        """
        Close the old Kuzu store, delete the db dir, rebuild from scratch.
        Returns {"symbol_count": N}.
        This runs in an executor thread (blocking I/O).
        """
        from modules.codegraph.kuzu_store import KuzuCodeGraphStore
        from modules.codegraph.tools import CodeGraphTools
        from modules.codegraph.http_linker import HttpLinker
        from modules.codegraph.enricher import CodeGraphEnricher

        # Import main module globals to close old store
        import sys
        main_mod = sys.modules.get("__main__") or sys.modules.get("main")

        # Close old store if accessible
        old_store = getattr(main_mod, "_store", None) if main_mod else None
        if old_store:
            try:
                old_store.close()
                logger.info("[GraphRebuilder] Old Kuzu store closed")
            except Exception as e:
                logger.warning(f"[GraphRebuilder] Error closing old store (continuing): {e}")

        # Validate and delete old kuzu db directory
        self._safe_delete_kuzu()

        # Create new Kuzu store
        new_store = KuzuCodeGraphStore(str(self._kuzu_db_path))
        new_store.init_schema()

        # Run HTTP linker
        http_data = None
        try:
            linker = HttpLinker(str(self._services_root))
            routes = linker.extract_all_routes()
            edges  = linker.link_services()
            http_data = {
                "routes": [{"service": r.service, "method": r.method, "path": r.path, "handler": r.handler} for r in routes],
                "calls":  [{"from_service": e.source, "to_service": e.target, "method": e.method, "path": e.route} for e in edges],
            }
        except Exception as e:
            logger.warning(f"[GraphRebuilder] HTTP linker failed (non-fatal): {e}")

        # Load extraction
        if self._extraction_path.exists():
            new_store.load_extraction(str(self._extraction_path), http_data=http_data)
        else:
            logger.warning("[GraphRebuilder] combined_extraction.json not found — graph may be empty")

        # Run enricher
        try:
            enricher = CodeGraphEnricher(str(self._services_root))
            enrichment = enricher.extract_all()
            new_store.load_enrichment(enrichment)
        except Exception as e:
            logger.warning(f"[GraphRebuilder] Enricher failed (non-fatal): {e}")

        # Build tools + agents
        new_tools = CodeGraphTools(kuzu_store=new_store, services_path=str(self._services_root))
        symbol_count = len(new_tools.all_symbols)

        new_agent = None
        new_orch  = None
        new_cg    = None
        try:
            from modules.agents.impact import ImpactAgent
            from modules.agents import PipelineOrchestrator
            from modules.codegen import CodeGenOrchestrator
            new_agent = ImpactAgent(new_store, new_tools)
            new_orch  = PipelineOrchestrator(new_agent)
            new_cg    = CodeGenOrchestrator(new_store, str(self._services_root))
        except Exception as e:
            logger.warning(f"[GraphRebuilder] Agent init failed (non-fatal): {e}")

        # Swap all globals via the main.py callback
        self._set_globals(new_store, new_tools, new_agent, new_orch, new_cg)
        logger.info(f"[GraphRebuilder] Graph globals swapped: {symbol_count} symbols")

        return {"symbol_count": symbol_count}

    def _safe_delete_kuzu(self) -> None:
        """
        Delete the Kuzu database directory with path safety check.
        Only deletes code_graph.kuzu and only if it's under services_root.
        """
        kuzu_path = self._kuzu_db_path.resolve()

        # Safety: must be under services_root
        try:
            kuzu_path.relative_to(self._services_root)
        except ValueError:
            raise RuntimeError(
                f"[GraphRebuilder] SAFETY: kuzu_db_path {kuzu_path} is not under services_root {self._services_root}"
            )

        # Must be named code_graph.kuzu (extra guard)
        if kuzu_path.name != "code_graph.kuzu":
            raise RuntimeError(
                f"[GraphRebuilder] SAFETY: refusing to delete directory not named 'code_graph.kuzu': {kuzu_path}"
            )

        if kuzu_path.exists():
            shutil.rmtree(kuzu_path)
            logger.info(f"[GraphRebuilder] Deleted stale kuzu db: {kuzu_path}")
