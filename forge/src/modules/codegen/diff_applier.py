"""
DiffApplier — Atomic two-phase unified diff application.

Phase 1: Apply all diffs to a temporary directory in memory (no real file touched).
         If any patch fails → abort entire batch, return failure.
Phase 2: Write all patched files to disk as a single batch.
         If any write fails → restore every already-written file from snapshot.

Security: every target path is resolved and verified to be under services_root
          before any read or write (path traversal prevention).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of a DiffApplier.apply() call."""
    success: bool
    files_written: list[str] = field(default_factory=list)
    files_failed: list[str] = field(default_factory=list)
    failure_reasons: dict[str, str] = field(default_factory=dict)


class DiffApplyError(Exception):
    """Raised when a diff cannot be applied."""


class DiffApplier:
    """
    Applies a list of unified diffs atomically to a services directory.

    Usage:
        applier = DiffApplier(services_root=Path("../services"))
        result = applier.apply(state.diffs)
        if result.success:
            print(f"Applied {len(result.files_written)} files")
    """

    def __init__(self, services_root: Path) -> None:
        self._services_root = services_root.resolve()

    # ─── Public API ───────────────────────────────────────────────────────────

    def apply(self, diffs) -> ApplyResult:
        """
        Atomically apply all successful diffs to disk.

        Args:
            diffs: list of AgentOutput objects with .file and .diff attributes.

        Returns:
            ApplyResult with success flag and file lists.
        """
        # Only process successful diffs that have content
        successful_diffs = [d for d in diffs if getattr(d, "status", "") == "success" and getattr(d, "diff", "")]
        if not successful_diffs:
            # Still run path validation on all diffs for security, even empty ones
            for d in diffs:
                file_rel = getattr(d, "file", "")
                if file_rel:
                    try:
                        self._validate_path(file_rel)
                    except Exception as e:
                        return ApplyResult(
                            success=False,
                            files_failed=[file_rel],
                            failure_reasons={file_rel: str(e)},
                        )
            return ApplyResult(success=True)

        # ── Phase 1: validate paths + apply to tempdir ─────────────────────
        phase1_result = self._phase1_validate_and_patch(successful_diffs)
        if not phase1_result["ok"]:
            return ApplyResult(
                success=False,
                files_failed=phase1_result["failed"],
                failure_reasons=phase1_result["reasons"],
            )

        patched_contents: dict[str, bytes] = phase1_result["patched"]

        # ── Phase 2: write to disk with rollback ────────────────────────────
        return self._phase2_write(patched_contents)

    # ─── Phase 1 ──────────────────────────────────────────────────────────────

    def _phase1_validate_and_patch(self, diffs) -> dict:
        """
        Validate paths and apply each diff to a temporary directory.
        Returns dict with ok, patched (filepath->bytes), failed, reasons.
        """
        patched: dict[str, bytes] = {}
        failed: list[str] = []
        reasons: dict[str, str] = {}

        with tempfile.TemporaryDirectory(prefix="forge_diff_") as tmp:
            tmp_path = Path(tmp)

            for agent_output in diffs:
                file_rel: str = agent_output.file
                diff_text: str = agent_output.diff

                # 1. Validate path
                try:
                    target_abs = self._validate_path(file_rel)
                except DiffApplyError as e:
                    failed.append(file_rel)
                    reasons[file_rel] = str(e)
                    return {"ok": False, "patched": patched, "failed": failed, "reasons": reasons}

                # 2. Read original content (empty bytes for CREATE)
                if target_abs.exists():
                    original_bytes = target_abs.read_bytes()
                else:
                    original_bytes = b""

                # 3. Write original to a mirrored tmp path
                #    mirror: tmp/<relative_path_from_services_root>
                try:
                    rel_from_root = target_abs.relative_to(self._services_root)
                except ValueError:
                    failed.append(file_rel)
                    reasons[file_rel] = "Path not under services_root after resolution"
                    return {"ok": False, "patched": patched, "failed": failed, "reasons": reasons}

                tmp_file = tmp_path / rel_from_root
                tmp_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_file.write_bytes(original_bytes)

                # 4. Apply the patch using patch-ng
                try:
                    new_bytes = self._apply_patch_in_memory(tmp_file, diff_text)
                except DiffApplyError as e:
                    failed.append(file_rel)
                    reasons[file_rel] = str(e)
                    return {"ok": False, "patched": patched, "failed": failed, "reasons": reasons}

                patched[str(target_abs)] = new_bytes
                logger.debug(f"[DiffApplier] Phase 1 OK: {file_rel} ({len(new_bytes)} bytes)")

        return {"ok": True, "patched": patched, "failed": [], "reasons": {}}

    def _apply_patch_in_memory(self, tmp_file: Path, diff_text: str) -> bytes:
        """
        Apply a unified diff to a file in a temp directory using patch-ng.
        Returns the patched file bytes.
        Raises DiffApplyError on failure.

        patch-ng resolves paths relative to root using the path in the diff header.
        The diff header may have 'a/' or 'b/' prefixes which patch-ng strips automatically.
        We write the original to a path that matches the stripped header path under tmp.
        """
        try:
            import patch_ng
        except ImportError:
            raise DiffApplyError("patch-ng not installed. Run: pip install patch-ng")

        # patch-ng needs the diff as bytes
        diff_bytes = diff_text.encode("utf-8", errors="replace")

        try:
            pset = patch_ng.fromstring(diff_bytes)
        except Exception as e:
            raise DiffApplyError(f"Could not parse diff: {e}")

        if not pset:
            raise DiffApplyError("patch-ng returned empty patchset — diff may be malformed")

        # patch-ng strips 'a/' and 'b/' and applies relative to root.
        # tmp_file was already written to the correct mirrored path under tmp.
        # root must be the temp directory BASE (not the file's parent), because
        # patch-ng constructs: root / stripped_diff_path.
        # Find the common ancestor of tmp_file up to where the relative path starts.
        # We use tmp_file.parent's ancestor up to where the diff path segment begins.
        # The simplest approach: root = tmp parent at the level that matches the diff path.

        # Extract the target path from the patchset (strip a/b prefix)
        try:
            diff_target = pset.items[0].target.decode("utf-8").lstrip("/")
            if diff_target.startswith("b/"):
                diff_target = diff_target[2:]
            elif diff_target.startswith("a/"):
                diff_target = diff_target[2:]
        except Exception:
            diff_target = None

        # root = the directory such that root/diff_target == tmp_file
        if diff_target and diff_target != "/dev/null":
            # Walk up from tmp_file until root/diff_target resolves to tmp_file
            candidate = tmp_file
            parts = Path(diff_target).parts
            for _ in parts:
                candidate = candidate.parent
            root = str(candidate)
        else:
            root = str(tmp_file.parent)

        ok = pset.apply(root=root)
        if not ok:
            raise DiffApplyError(f"patch-ng failed to apply diff to {tmp_file.name}")

        # For CREATE diffs, patch-ng writes to root/diff_target
        if diff_target and diff_target != "/dev/null":
            result_path = Path(root) / diff_target
        else:
            result_path = tmp_file

        if not result_path.exists():
            raise DiffApplyError(f"Patched file not found at {result_path} after apply")

        return result_path.read_bytes()

    # ─── Phase 2 ──────────────────────────────────────────────────────────────

    def _phase2_write(self, patched_contents: dict[str, bytes]) -> ApplyResult:
        """
        Write all patched files to disk.
        On any failure: restore previously written files from pre-write snapshot.
        """
        # Take pre-write snapshot of all target files
        snapshot: dict[str, bytes | None] = {}
        for abs_path_str in patched_contents:
            p = Path(abs_path_str)
            snapshot[abs_path_str] = p.read_bytes() if p.exists() else None

        written: list[str] = []
        failed: list[str] = []
        reasons: dict[str, str] = {}

        for abs_path_str, new_bytes in patched_contents.items():
            p = Path(abs_path_str)
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(new_bytes)
                written.append(abs_path_str)
                logger.info(f"[DiffApplier] Written: {p.name}")
            except Exception as e:
                failed.append(abs_path_str)
                reasons[abs_path_str] = str(e)
                # Rollback everything written so far
                self._rollback(written, snapshot)
                logger.error(f"[DiffApplier] Write failed for {p.name}: {e} — rolled back {len(written)} files")
                return ApplyResult(success=False, files_failed=[abs_path_str], failure_reasons=reasons)

        logger.info(f"[DiffApplier] Phase 2 complete: {len(written)} files written to disk")
        return ApplyResult(success=True, files_written=written)

    def _rollback(self, written: list[str], snapshot: dict[str, bytes | None]) -> None:
        """Restore all written files from the pre-write snapshot."""
        for abs_path_str in written:
            p = Path(abs_path_str)
            original = snapshot.get(abs_path_str)
            try:
                if original is None:
                    # File didn't exist before — delete it
                    if p.exists():
                        p.unlink()
                else:
                    p.write_bytes(original)
            except Exception as e:
                logger.error(f"[DiffApplier] Rollback failed for {p}: {e}")

    # ─── Path validation ──────────────────────────────────────────────────────

    def _validate_path(self, file_rel: str) -> Path:
        """
        Resolve a service-relative file path and assert it stays under services_root.
        Raises DiffApplyError on traversal attempts or invalid paths.
        """
        if not file_rel:
            raise DiffApplyError("Empty file path in diff")

        # Reject null bytes
        if "\x00" in file_rel:
            raise DiffApplyError(f"Null byte in path: {file_rel!r}")

        # Strip leading a/ or b/ from unified diff headers (--- a/file, +++ b/file)
        clean = file_rel.lstrip("/")
        if clean.startswith("a/") or clean.startswith("b/"):
            clean = clean[2:]

        # Reject absolute paths
        if Path(clean).is_absolute():
            raise DiffApplyError(f"Absolute path not allowed: {file_rel!r}")

        # Resolve and check boundary
        resolved = (self._services_root / clean).resolve()
        try:
            resolved.relative_to(self._services_root)
        except ValueError:
            raise DiffApplyError(
                f"Path traversal detected: {file_rel!r} resolves outside services_root"
            )

        return resolved
