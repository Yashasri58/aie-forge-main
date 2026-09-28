"""
VersionManager — git versioning for approved AI code changes.

Creates a tagged git commit for every approved codegen run, supports listing,
downloading (as zip), and reverting past changes.

All git ops use subprocess so we work with any git version installed on the VM.
Commit hash inputs are validated against [0-9a-f]{4,40} before use to prevent
shell injection.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Validates commit hashes before use in subprocess args
_HASH_RE = re.compile(r"^[0-9a-f]{4,40}$", re.IGNORECASE)


@dataclass
class VersionEntry:
    """One AI-generated commit in the services/ git history."""
    commit_hash: str          # full 40-char SHA
    short_hash: str           # first 8 chars
    message: str              # first line of commit message
    timestamp: str            # ISO 8601
    state_id: str             # Forge-State-ID trailer value
    changed_files: list[str] = field(default_factory=list)


@dataclass
class CommitResult:
    success: bool
    commit_hash: str = ""
    error: str = ""


@dataclass
class RevertResult:
    success: bool
    revert_commit_hash: str = ""
    error: str = ""
    conflict_details: str = ""


class VersionManager:
    """
    Manages git versioning for AI-generated changes in services/.

    Usage:
        vm = VersionManager(services_root=Path("../services"))
        if vm.is_git_repo():
            result = vm.commit(patched_files, state)
    """

    def __init__(self, services_root: Path) -> None:
        self._root = services_root.resolve()

    # ─── Git repo check ───────────────────────────────────────────────────────

    def is_git_repo(self) -> bool:
        """Return True if services_root is inside a git repository."""
        result = self._run(["status"], check=False)
        return result.returncode == 0

    # ─── Commit ───────────────────────────────────────────────────────────────

    def commit(self, patched_files: list[str], state) -> CommitResult:
        """
        Stage patched files and create a versioned commit.

        Args:
            patched_files: List of absolute path strings that were written.
            state:         CodeGenState — for change_request and state id.

        Returns:
            CommitResult with commit hash or error.
        """
        if not self.is_git_repo():
            return CommitResult(success=False, error="services/ is not a git repository")

        # Stage only the modified files
        for abs_path_str in patched_files:
            try:
                # Pass relative path to git add so it works regardless of cwd
                rel = str(Path(abs_path_str).relative_to(self._root))
            except ValueError:
                rel = abs_path_str
            result = self._run(["add", rel], check=False)
            if result.returncode != 0:
                return CommitResult(
                    success=False,
                    error=f"git add failed for {rel}: {result.stderr.strip()}"
                )

        # Build commit message
        impact = getattr(state, "impact_report", None) or {}
        change_req = ""
        if isinstance(impact, dict):
            change_req = impact.get("change_request", "") or ""
        if not change_req:
            change_req = getattr(state, "id", "unknown")
        change_req_short = change_req[:72].replace("\n", " ")

        state_id = getattr(state, "id", "unknown")
        msg = (
            f"AI codegen: {change_req_short}\n\n"
            f"Forge-State-ID: {state_id}\n"
            f"AI-Generated-By: forge-codegen"
        )

        result = self._run(["commit", "-m", msg], check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # "nothing to commit" is not an error in the traditional sense
            if "nothing to commit" in stderr.lower():
                # Grab HEAD to return a hash anyway
                head = self._run(["rev-parse", "HEAD"], check=False)
                return CommitResult(
                    success=True,
                    commit_hash=head.stdout.strip(),
                    error="nothing to commit (files already match)",
                )
            return CommitResult(success=False, error=f"git commit failed: {stderr}")

        # Get the new commit hash
        head = self._run(["rev-parse", "HEAD"], check=False)
        commit_hash = head.stdout.strip()
        logger.info(f"[VersionManager] Created commit {commit_hash[:8]}: {change_req_short}")
        return CommitResult(success=True, commit_hash=commit_hash)

    # ─── List versions ────────────────────────────────────────────────────────

    def list_versions(self) -> list[VersionEntry]:
        """
        Return all AI-generated commits, newest first.

        Filters by the AI-Generated-By: forge-codegen trailer.
        """
        if not self.is_git_repo():
            return []

        fmt = "%H|%s|%aI"
        result = self._run(
            ["log", "--all",
             "--grep=AI-Generated-By: forge-codegen",
             f"--format={fmt}"],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        entries: list[VersionEntry] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commit_hash, message, timestamp = parts[0], parts[1], parts[2]
            state_id = self._get_trailer(commit_hash, "Forge-State-ID")
            changed = self._changed_files(commit_hash)
            entries.append(VersionEntry(
                commit_hash=commit_hash,
                short_hash=commit_hash[:8],
                message=message,
                timestamp=timestamp,
                state_id=state_id,
                changed_files=changed,
            ))

        return entries

    # ─── Download ─────────────────────────────────────────────────────────────

    def download_version(self, commit_hash: str) -> bytes:
        """
        Return a zip archive of the repo at a given commit.

        Args:
            commit_hash: Full or abbreviated commit SHA.

        Returns:
            Raw zip bytes.

        Raises:
            ValueError on invalid hash.
            RuntimeError if git archive fails.
        """
        self._validate_hash(commit_hash)
        result = self._run(
            ["archive", "--format=zip", commit_hash],
            check=False,
            capture_bytes=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git archive failed: {result.stderr.strip()}")
        return result.stdout  # bytes when capture_bytes=True

    # ─── Revert ───────────────────────────────────────────────────────────────

    def revert_version(self, commit_hash: str) -> RevertResult:
        """
        Create a revert commit for the given hash.

        Uses `git revert --no-edit` so no interactive editor is spawned.
        On conflict: runs `git revert --abort` and returns the error.
        """
        self._validate_hash(commit_hash)

        result = self._run(
            ["revert", "--no-edit", commit_hash],
            check=False,
        )
        if result.returncode != 0:
            # Cleanup any partial revert state
            self._run(["revert", "--abort"], check=False)
            return RevertResult(
                success=False,
                error="git revert failed",
                conflict_details=result.stderr.strip() or result.stdout.strip(),
            )

        # Get the new revert commit hash
        head = self._run(["rev-parse", "HEAD"], check=False)
        revert_hash = head.stdout.strip()
        logger.info(f"[VersionManager] Reverted {commit_hash[:8]} → new commit {revert_hash[:8]}")
        return RevertResult(success=True, revert_commit_hash=revert_hash)

    # ─── Lookup by state ID ───────────────────────────────────────────────────

    def get_commit_for_state(self, state_id: str) -> Optional[str]:
        """Return the commit hash for a given Forge state ID, or None."""
        if not self.is_git_repo():
            return None
        result = self._run(
            ["log", "--all",
             f"--grep=Forge-State-ID: {state_id}",
             "--format=%H", "-1"],
            check=False,
        )
        h = result.stdout.strip()
        return h if h else None

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _changed_files(self, commit_hash: str) -> list[str]:
        """Return list of files changed in a commit."""
        result = self._run(
            ["diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            check=False,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f]

    def _get_trailer(self, commit_hash: str, key: str) -> str:
        """Extract a git trailer value from a commit message."""
        result = self._run(
            ["log", "-1", f"--format=%(trailers:key={key},valueonly)", commit_hash],
            check=False,
        )
        return result.stdout.strip()

    def _validate_hash(self, commit_hash: str) -> None:
        """Raise ValueError if commit_hash is not a valid git SHA."""
        if not _HASH_RE.match(commit_hash):
            raise ValueError(
                f"Invalid commit hash: {commit_hash!r} — "
                "must match [0-9a-f]{{4,40}}"
            )

    def _run(
        self,
        args: list[str],
        check: bool = True,
        capture_bytes: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a git command in services_root via subprocess."""
        git_exe = self._find_git()
        cmd = [git_exe, "-C", str(self._root)] + args
        logger.debug(f"[VersionManager] {' '.join(cmd)}")
        if capture_bytes:
            return subprocess.run(
                cmd, capture_output=True, check=check,
            )
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check,
        )

    @staticmethod
    def _find_git() -> str:
        """Find the git executable, falling back to common install locations."""
        import shutil
        git = shutil.which("git")
        if git:
            return git
        # Common Windows install paths
        candidates = [
            r"C:\Users\lnellutl\AppData\Local\Programs\Git\bin\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
        ]
        for c in candidates:
            if Path(c).exists():
                return c
        return "git"  # last resort — will fail with a clear error
