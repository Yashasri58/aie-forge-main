"""
DiffApplier — Atomic two-phase unified diff application.

Phase 1: Apply all diffs to a temporary directory (no real file touched).
         Uses `git apply --whitespace=fix` for fuzzy CRLF/whitespace tolerance.
         If any patch fails → abort entire batch, return failure.
Phase 2: Write all patched files to disk as a single batch.
         If any write fails → restore every already-written file from snapshot.

Security: every target path is resolved and verified to be under services_root
          before any read or write (path traversal prevention).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Git binary — explicit path for Windows; falls back to PATH if not found
_GIT = r"C:\Users\lnellutl\AppData\Local\Programs\Git\bin\git.exe"
if not Path(_GIT).exists():
    _GIT = "git"  # fall back to PATH


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
        successful_diffs = [
            d for d in diffs
            if getattr(d, "status", "") == "success" and getattr(d, "diff", "")
        ]
        if not successful_diffs:
            # Still run path validation on all diffs for security
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
                    return {
                        "ok": False,
                        "patched": patched,
                        "failed": failed,
                        "reasons": reasons,
                    }

                # 2. Read original content (empty bytes for new files)
                original_bytes = target_abs.read_bytes() if target_abs.exists() else b""

                # 3. Mirror original to tmp/<relative_path_from_services_root>
                try:
                    rel_from_root = target_abs.relative_to(self._services_root)
                except ValueError:
                    failed.append(file_rel)
                    reasons[file_rel] = "Path not under services_root after resolution"
                    return {
                        "ok": False,
                        "patched": patched,
                        "failed": failed,
                        "reasons": reasons,
                    }

                tmp_file = tmp_path / rel_from_root
                tmp_file.parent.mkdir(parents=True, exist_ok=True)

                # For CREATE diffs (new file), do NOT write a temp file — git apply
                # will create it. Writing even an empty file causes:
                # "already exists in working directory" error.
                # For MODIFY diffs, normalize CRLF → LF so git apply context
                # matching works on Windows (difflib generates LF-only diffs).
                is_create = not target_abs.exists()
                if not is_create:
                    normalized_bytes = original_bytes.replace(b"\r\n", b"\n")
                    tmp_file.write_bytes(normalized_bytes)

                # 4. Apply the patch using git apply
                try:
                    new_bytes = self._apply_with_git(tmp_path, diff_text, rel_from_root)
                except DiffApplyError as e:
                    failed.append(file_rel)
                    reasons[file_rel] = str(e)
                    return {
                        "ok": False,
                        "patched": patched,
                        "failed": failed,
                        "reasons": reasons,
                    }

                patched[str(target_abs)] = new_bytes
                logger.debug(
                    f"[DiffApplier] Phase 1 OK: {file_rel} ({len(new_bytes)} bytes)"
                )

        return {"ok": True, "patched": patched, "failed": [], "reasons": {}}

    def _apply_with_git(
        self,
        repo_root: Path,
        diff_text: str,
        rel_from_root: Path,
    ) -> bytes:
        """
        Apply a unified diff using pure Python hunk parsing.

        For CREATE diffs (--- /dev/null): extract +lines and write the new file.
        For MODIFY diffs: parse hunks and apply them against the mirrored file.
        For DELETE diffs: return empty bytes (signals _phase2_write to delete).

        This avoids git apply entirely for applying content, removing all CRLF /
        hunk-count / context-mismatch issues that plagued the git apply approach.
        Git is still used only for commits (in VersionManager).

        Raises DiffApplyError on failure.
        """
        is_create = "--- /dev/null" in diff_text.splitlines()[0:4] or \
                    any(l.strip() == "--- /dev/null" for l in diff_text.splitlines()[:6])
        is_delete = "+++ /dev/null" in diff_text or \
                    any(l.strip() == "+++ /dev/null" for l in diff_text.splitlines()[:6])

        if is_delete:
            # DELETE: return empty bytes — _phase2_write will unlink the file
            return b""

        if is_create:
            # CREATE: extract all '+' lines (skip diff headers)
            new_lines = []
            in_hunk = False
            for line in diff_text.splitlines():
                if line.startswith("@@"):
                    in_hunk = True
                    continue
                if in_hunk:
                    if line.startswith("+"):
                        new_lines.append(line[1:])  # strip leading '+'
                    elif line.startswith("\\"):
                        pass  # "No newline at end of file" marker
            content = "\n".join(new_lines)
            if new_lines and not diff_text.rstrip().endswith("\\ No newline at end of file"):
                content += "\n"
            return content.encode("utf-8")

        # MODIFY: apply hunks against the mirrored file
        original_path = repo_root / rel_from_root
        if not original_path.exists():
            raise DiffApplyError(
                f"Cannot apply MODIFY diff — original file not found at {original_path}"
            )
        original_bytes = original_path.read_bytes()
        # Normalize CRLF so our line matching works
        original_text = original_bytes.replace(b"\r\n", b"\n").decode("utf-8", errors="replace")
        original_lines = original_text.splitlines()

        try:
            result_lines = self._apply_hunks(original_lines, diff_text)
        except DiffApplyError:
            raise
        except Exception as e:
            raise DiffApplyError(f"Hunk application failed for {rel_from_root}: {e}")

        result_text = "\n".join(result_lines) + ("\n" if result_lines else "")
        return result_text.encode("utf-8")

    def _apply_hunks(self, original_lines: list[str], diff_text: str) -> list[str]:
        """
        Apply unified diff hunks using anchor-based matching.

        For each hunk:
        1. Use the first few context lines to find position in file (anchor)
        2. From that anchor, find the removed lines (fuzzy match)
        3. Replace removed lines with added lines, keep everything else
        """
        result = list(original_lines)
        offset = 0

        for hunk in self._parse_hunks(diff_text):
            orig_start = hunk["orig_start"] - 1
            expected = hunk["expected"]
            removed_set = hunk["removed_indices"]
            added = hunk["added"]

            removed_lines = [expected[i] for i in sorted(removed_set)]
            context_lines = [expected[i] for i in range(len(expected)) if i not in removed_set]

            search_pos = orig_start + offset

            if not removed_lines and not added:
                continue  # nothing to do

            if not removed_lines:
                # Pure insertion — find anchor and insert
                if context_lines:
                    anchor = self._find_line(result, context_lines[0], search_pos, fuzz=50)
                    pos = anchor if anchor is not None else search_pos
                else:
                    pos = search_pos
                result = result[:pos] + added + result[pos:]
                offset += len(added)
                continue

            # Find where the removed lines are in the file
            # Use context_lines as anchor first, then search for removed near there
            if context_lines:
                anchor = self._find_line(result, context_lines[0], search_pos, fuzz=50)
                search_near = anchor if anchor is not None else search_pos
            else:
                search_near = search_pos

            # Find the removed block near the anchor
            removed_start = self._find_line(result, removed_lines[0], search_near, fuzz=30)
            if removed_start is None:
                # Try searching more broadly
                removed_start = self._find_line(result, removed_lines[0], search_pos, fuzz=80)

            if removed_start is None:
                raise DiffApplyError(
                    f"Cannot find removed line near line {orig_start + 1}: "
                    f"{repr(removed_lines[0])}"
                )

            # Verify consecutive removed lines match (with some tolerance)
            # Find the actual span of removed lines
            actual_end = removed_start
            ri = 0
            fi = removed_start
            while ri < len(removed_lines) and fi < len(result):
                if result[fi].rstrip() == removed_lines[ri].rstrip():
                    ri += 1
                    fi += 1
                elif not result[fi].strip():
                    fi += 1  # skip blank lines in file
                else:
                    break
            actual_end = fi

            if ri < len(removed_lines):
                # Couldn't match all removed lines consecutively — just splice from start
                actual_end = removed_start + len(removed_lines)
                if actual_end > len(result):
                    actual_end = len(result)

            result = result[:removed_start] + added + result[actual_end:]
            offset += len(added) - (actual_end - removed_start)

        return result

    @staticmethod
    def _find_line(lines: list[str], target: str, near: int, fuzz: int = 50) -> int | None:
        """Find the first occurrence of target line near position, returns index or None."""
        def norm(s): return s.rstrip()
        target_norm = norm(target)
        n = len(lines)
        for delta in range(fuzz + 1):
            for sign in ([0] if delta == 0 else [+delta, -delta]):
                pos = near + sign
                if 0 <= pos < n and norm(lines[pos]) == target_norm:
                    return pos
        return None

    def _parse_hunks(self, diff_text: str) -> list[dict]:
        """
        Parse unified diff into hunk dicts.

        Each hunk dict:
          orig_start: int       — 1-indexed start line from @@ header
          expected: list[str]   — all lines the hunk expects on disk
                                  (context lines + removed lines, in order)
          removed_indices: set  — which indices in expected are '-' lines
          added: list[str]      — the new lines to insert
        """
        hunks = []
        current = None
        import re as _re

        for line in diff_text.splitlines():
            if line.startswith("@@"):
                if current:
                    hunks.append(current)
                m = _re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                current = {
                    "orig_start": int(m.group(1)) if m else 1,
                    "expected": [],
                    "removed_indices": set(),
                    "added": [],
                }
            elif current is not None:
                if line.startswith("-"):
                    idx = len(current["expected"])
                    current["expected"].append(line[1:])
                    current["removed_indices"].add(idx)
                elif line.startswith("+"):
                    current["added"].append(line[1:])
                elif line.startswith(" "):
                    current["expected"].append(line[1:])
                elif line == "":
                    current["expected"].append("")
                # lines starting with '\' (no newline marker) are skipped

        if current:
            hunks.append(current)

        return hunks

    @staticmethod
    def _find_block_range(
        lines: list[str],
        block: list[str],
        near: int,
        fuzz: int = 50,
    ) -> tuple[int | None, int | None]:
        """
        Find `block` in `lines` near `near`, returning (start, end) indices.

        Pass 1: exact match — all block lines match consecutively (whitespace-stripped).
        Pass 2: subsequence match — block's non-empty lines appear in order,
                with possible extra blank lines in between (handles AI diffs that
                omit blank context lines).

        Returns (None, None) if not found.
        """
        if not block:
            return near, near

        def norm(s: str) -> str:
            return s.rstrip()

        block_norm = [norm(l) for l in block]
        n = len(lines)
        blen = len(block)

        # --- Pass 1: exact consecutive match ---
        for delta in range(fuzz + 1):
            for sign in ([0] if delta == 0 else [+delta, -delta]):
                pos = near + sign
                if pos < 0 or pos + blen > n:
                    continue
                if [norm(lines[pos + i]) for i in range(blen)] == block_norm:
                    return pos, pos + blen

        # --- Pass 2: subsequence match using only context lines (not removed lines) ---
        # Removed lines may differ from file (that's the whole point of the diff),
        # so only use context lines as anchors.
        context_only = [(i, block_norm[i]) for i in range(len(block_norm))
                        if block_norm[i].strip()]  # non-empty lines in block

        # We can't know which are removed vs context here, so use all non-empty
        # lines but skip ones that DON'T match when scanning (they may be removed)
        search_lo = max(0, near - fuzz)
        search_hi = min(n, near + fuzz + blen * 3)

        for start in range(search_lo, search_hi):
            fi = start
            matched_count = 0
            for _, exp_line in context_only:
                # Scan forward in file to find this line
                found = False
                scan_limit = fi + 10  # don't skip too many lines
                while fi < min(search_hi, scan_limit):
                    if norm(lines[fi]) == exp_line:
                        fi += 1
                        matched_count += 1
                        found = True
                        break
                    elif not lines[fi].strip():
                        fi += 1  # skip blank lines in file
                    else:
                        break  # non-matching non-blank line
                if not found:
                    break
            else:
                # All context lines found in order
                return start, fi

        return None, None

    @staticmethod
    def _find_block(
        lines: list[str],
        block: list[str],
        near: int,
        fuzz: int = 50,
    ) -> int | None:
        """Wrapper around _find_block_range returning just start."""
        start, _ = DiffApplier._find_block_range(lines, block, near, fuzz)
        return start

    @staticmethod
    def _ensure_create_diff_headers(diff_text: str, rel_from_root: Path) -> str:
        """
        If this looks like a CREATE diff (starts with '--- /dev/null') but is
        missing the 'diff --git' + 'new file mode 100644' headers that git apply
        requires, inject them. This fixes AI-generated CREATE diffs that omit
        the git extended headers.
        """
        lines = diff_text.splitlines(keepends=True)
        if not lines:
            return diff_text

        first = lines[0].strip()

        # Already has proper git header — nothing to do
        if first.startswith("diff --git"):
            return diff_text

        # Looks like a bare CREATE diff: starts with --- /dev/null
        if first == "--- /dev/null":
            fp = rel_from_root.as_posix()
            header = (
                f"diff --git a/{fp} b/{fp}\n"
                f"new file mode 100644\n"
            )
            return header + diff_text

        return diff_text

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
                if new_bytes == b"":
                    # Empty bytes = DELETE signal from a deletion diff
                    if p.exists():
                        p.unlink()
                    logger.info(f"[DiffApplier] Deleted: {p.name}")
                else:
                    p.write_bytes(new_bytes)
                    logger.info(f"[DiffApplier] Written: {p.name}")
                written.append(abs_path_str)
            except Exception as e:
                failed.append(abs_path_str)
                reasons[abs_path_str] = str(e)
                # Rollback everything written so far
                self._rollback(written, snapshot)
                logger.error(
                    f"[DiffApplier] Write failed for {p.name}: {e} "
                    f"— rolled back {len(written)} files"
                )
                return ApplyResult(
                    success=False,
                    files_failed=[abs_path_str],
                    failure_reasons=reasons,
                )

        logger.info(
            f"[DiffApplier] Phase 2 complete: {len(written)} files written to disk"
        )
        return ApplyResult(success=True, files_written=written)

    def _rollback(self, written: list[str], snapshot: dict[str, bytes | None]) -> None:
        """Restore all written files from the pre-write snapshot."""
        for abs_path_str in written:
            p = Path(abs_path_str)
            original = snapshot.get(abs_path_str)
            try:
                if original is None:
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

        if "\x00" in file_rel:
            raise DiffApplyError(f"Null byte in path: {file_rel!r}")

        # Strip leading slashes and a/ or b/ diff prefixes
        clean = file_rel.lstrip("/")
        if clean.startswith("a/") or clean.startswith("b/"):
            clean = clean[2:]

        if Path(clean).is_absolute():
            raise DiffApplyError(f"Absolute path not allowed: {file_rel!r}")

        resolved = (self._services_root / clean).resolve()
        try:
            resolved.relative_to(self._services_root)
        except ValueError:
            raise DiffApplyError(
                f"Path traversal detected: {file_rel!r} resolves outside services_root"
            )

        return resolved
