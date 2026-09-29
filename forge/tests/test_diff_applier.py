"""
DiffApplier edge case test suite.

Covers every realistic scenario that could come from AI-generated diffs:
  - MODIFY: basic, CRLF files, trailing whitespace, multi-file batch
  - CREATE: new file, proper git headers, fallback _content_to_diff format
  - DELETE: file removal
  - ATOMIC: one bad diff in a batch rolls back everything
  - SECURITY: path traversal attempts
  - EDGE CASES: empty diff, missing file, binary-ish content

Run:
    cd aie-forge-main/forge
    python -m pytest tests/test_diff_applier.py -v
"""

import difflib
import sys
import tempfile
from pathlib import Path

import pytest

# Put src on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from modules.codegen.diff_applier import DiffApplier, DiffApplyError


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_services_dir(tmp_path: Path) -> Path:
    """Create a minimal fake services/ directory."""
    svc = tmp_path / "services"
    svc.mkdir()
    return svc


def make_file(root: Path, rel: str, content: str, crlf: bool = False) -> Path:
    """Write a file under root, optionally with CRLF line endings."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if crlf:
        p.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    else:
        p.write_text(content, encoding="utf-8")
    return p


def make_modify_diff(original: str, patched: str, filepath: str) -> str:
    """Generate a unified diff for a file modification."""
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
    ))


def make_create_diff(filepath: str, content: str) -> str:
    """Generate a proper git-format diff for a new file."""
    lines = content.splitlines()
    parts = [
        f"diff --git a/{filepath} b/{filepath}",
        f"new file mode 100644",
        f"--- /dev/null",
        f"+++ b/{filepath}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    for line in lines:
        parts.append(f"+{line}")
    return "\n".join(parts) + "\n"


def make_delete_diff(filepath: str, original: str) -> str:
    """Generate a proper git-format diff for file deletion."""
    lines = original.splitlines()
    parts = [
        f"diff --git a/{filepath} b/{filepath}",
        f"deleted file mode 100644",
        f"--- a/{filepath}",
        f"+++ /dev/null",
        f"@@ -1,{len(lines)} +0,0 @@",
    ]
    for line in lines:
        parts.append(f"-{line}")
    return "\n".join(parts) + "\n"


class FakeDiff:
    def __init__(self, file: str, diff: str, status: str = "success"):
        self.file = file
        self.diff = diff
        self.status = status


# ─── MODIFY tests ─────────────────────────────────────────────────────────────

class TestModify:

    def test_basic_modify(self, tmp_path):
        """Basic line change in an existing file."""
        svc = make_services_dir(tmp_path)
        original = "line1\nline2\nline3\n"
        patched  = "line1\nLINE2_CHANGED\nline3\n"
        make_file(svc, "svc/file.js", original)

        diff = make_modify_diff(original, patched, "svc/file.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/file.js", diff)])

        assert result.success
        assert (svc / "svc/file.js").read_text(encoding="utf-8") == patched

    def test_modify_crlf_file(self, tmp_path):
        """File with CRLF endings — diff should still apply cleanly."""
        svc = make_services_dir(tmp_path)
        original = "line1\nline2\nline3\n"
        patched  = "line1\nLINE2_CHANGED\nline3\n"
        # Write with CRLF
        make_file(svc, "svc/file.js", original, crlf=True)

        diff = make_modify_diff(original, patched, "svc/file.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/file.js", diff)])

        assert result.success
        written = (svc / "svc/file.js").read_bytes()
        # Content should contain the change (may be LF or CRLF depending on git)
        assert b"LINE2_CHANGED" in written

    def test_modify_trailing_whitespace_in_diff(self, tmp_path):
        """Trailing whitespace in diff lines must not abort the apply."""
        svc = make_services_dir(tmp_path)
        original = "hello\nworld\n"
        patched  = "hello\nworld\nbye\n"
        make_file(svc, "svc/a.js", original)

        # Inject trailing whitespace into a context line
        diff = make_modify_diff(original, patched, "svc/a.js")
        diff = diff.replace(" hello\n", " hello  \n")  # trailing space on context line

        result = DiffApplier(svc).apply([FakeDiff("svc/a.js", diff)])
        assert result.success

    def test_modify_multi_hunk(self, tmp_path):
        """Diff with multiple @@ hunks in one file."""
        svc = make_services_dir(tmp_path)
        lines = [f"line{i}\n" for i in range(1, 51)]
        original = "".join(lines)
        lines[4]  = "CHANGED_LINE5\n"
        lines[44] = "CHANGED_LINE45\n"
        patched  = "".join(lines)
        make_file(svc, "svc/big.js", original)

        diff = make_modify_diff(original, patched, "svc/big.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/big.js", diff)])

        assert result.success
        content = (svc / "svc/big.js").read_text(encoding="utf-8")
        assert "CHANGED_LINE5" in content
        assert "CHANGED_LINE45" in content

    def test_modify_appends_to_end(self, tmp_path):
        """Adding lines at the end of a file (most common AI pattern)."""
        svc = make_services_dir(tmp_path)
        original = "const x = 1;\nmodule.exports = x;\n"
        patched  = original + "\n// Added by Forge AI\n"
        make_file(svc, "svc/index.js", original)

        diff = make_modify_diff(original, patched, "svc/index.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/index.js", diff)])

        assert result.success
        assert "// Added by Forge AI" in (svc / "svc/index.js").read_text()


# ─── CREATE tests ─────────────────────────────────────────────────────────────

class TestCreate:

    def test_create_new_file_proper_headers(self, tmp_path):
        """CREATE diff with full git headers (diff --git + new file mode)."""
        svc = make_services_dir(tmp_path)
        content = "const x = 1;\nmodule.exports = x;\n"
        diff = make_create_diff("svc/utils/logger.js", content)

        result = DiffApplier(svc).apply([FakeDiff("svc/utils/logger.js", diff)])

        assert result.success
        written = (svc / "svc/utils/logger.js").read_text(encoding="utf-8")
        assert "const x = 1;" in written

    def test_create_makes_parent_dirs(self, tmp_path):
        """CREATE diff for a deeply nested new file creates all parent dirs."""
        svc = make_services_dir(tmp_path)
        content = "export default {};\n"
        diff = make_create_diff("svc/a/b/c/deep.js", content)

        result = DiffApplier(svc).apply([FakeDiff("svc/a/b/c/deep.js", diff)])

        assert result.success
        assert (svc / "svc/a/b/c/deep.js").exists()

    def test_create_does_not_fail_if_target_missing(self, tmp_path):
        """CREATE diff target doesn't need to pre-exist."""
        svc = make_services_dir(tmp_path)
        target = svc / "svc/brand_new.js"
        assert not target.exists()

        diff = make_create_diff("svc/brand_new.js", "const y = 2;\n")
        result = DiffApplier(svc).apply([FakeDiff("svc/brand_new.js", diff)])

        assert result.success
        assert target.exists()

    def test_create_and_modify_in_same_batch(self, tmp_path):
        """CREATE a new file and MODIFY an existing file atomically."""
        svc = make_services_dir(tmp_path)
        original = "const express = require('express');\n"
        patched  = "const express = require('express');\nconst logger = require('./logger');\n"
        make_file(svc, "svc/index.js", original)

        create_diff = make_create_diff("svc/logger.js", "module.exports = console;\n")
        modify_diff = make_modify_diff(original, patched, "svc/index.js")

        result = DiffApplier(svc).apply([
            FakeDiff("svc/logger.js", create_diff),
            FakeDiff("svc/index.js", modify_diff),
        ])

        assert result.success
        assert len(result.files_written) == 2
        assert (svc / "svc/logger.js").exists()
        assert "logger" in (svc / "svc/index.js").read_text()


# ─── DELETE tests ─────────────────────────────────────────────────────────────

class TestDelete:

    def test_delete_existing_file(self, tmp_path):
        """DELETE diff removes the file."""
        svc = make_services_dir(tmp_path)
        content = "const old = true;\n"
        make_file(svc, "svc/old.js", content)

        diff = make_delete_diff("svc/old.js", content)
        result = DiffApplier(svc).apply([FakeDiff("svc/old.js", diff)])

        assert result.success
        assert not (svc / "svc/old.js").exists()


# ─── ATOMIC rollback tests ─────────────────────────────────────────────────────

class TestAtomic:

    def test_bad_diff_in_batch_rolls_back_nothing_written(self, tmp_path):
        """If one diff fails in a batch, no files are written to disk."""
        svc = make_services_dir(tmp_path)
        original_a = "fileA content\n"
        original_b = "fileB content\n"
        make_file(svc, "svc/a.js", original_a)
        make_file(svc, "svc/b.js", original_b)

        good_diff = make_modify_diff(original_a, "fileA CHANGED\n", "svc/a.js")
        bad_diff  = "--- a/svc/b.js\n+++ b/svc/b.js\n@@ -999,3 +999,3 @@\n-nonexistent\n+replaced\n"

        result = DiffApplier(svc).apply([
            FakeDiff("svc/a.js", good_diff),
            FakeDiff("svc/b.js", bad_diff),
        ])

        assert not result.success
        # Both files should be unchanged
        assert (svc / "svc/a.js").read_text() == original_a
        assert (svc / "svc/b.js").read_text() == original_b

    def test_failed_diffs_skipped_cleanly(self, tmp_path):
        """Diffs with status != 'success' are ignored, not applied."""
        svc = make_services_dir(tmp_path)
        original = "original\n"
        make_file(svc, "svc/a.js", original)

        # This diff would change the file but its status is 'error'
        diff = make_modify_diff(original, "changed\n", "svc/a.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/a.js", diff, status="error")])

        assert result.success  # vacuous success — nothing to apply
        assert (svc / "svc/a.js").read_text() == original

    def test_empty_diff_string_skipped(self, tmp_path):
        """An empty diff string is silently skipped."""
        svc = make_services_dir(tmp_path)
        make_file(svc, "svc/a.js", "content\n")

        result = DiffApplier(svc).apply([FakeDiff("svc/a.js", "", status="success")])
        assert result.success


# ─── SECURITY tests ───────────────────────────────────────────────────────────

class TestSecurity:

    def test_path_traversal_rejected(self, tmp_path):
        """Diff targeting ../../etc/passwd must be rejected."""
        svc = make_services_dir(tmp_path)
        result = DiffApplier(svc).apply([
            FakeDiff("../../etc/passwd", "--- /dev/null\n+++ b/../../etc/passwd\n@@ -0,0 +1 @@\n+evil\n")
        ])
        assert not result.success
        assert "traversal" in str(result.failure_reasons).lower() or "outside" in str(result.failure_reasons).lower()

    def test_absolute_path_rejected(self, tmp_path):
        """Diff with an absolute file path must be rejected."""
        svc = make_services_dir(tmp_path)
        result = DiffApplier(svc).apply([
            FakeDiff("/etc/passwd", "some diff")
        ])
        assert not result.success

    def test_null_byte_in_path_rejected(self, tmp_path):
        """Null byte in path must be rejected."""
        svc = make_services_dir(tmp_path)
        result = DiffApplier(svc).apply([
            FakeDiff("svc/file\x00.js", "some diff")
        ])
        assert not result.success

    def test_ab_prefix_stripped(self, tmp_path):
        """a/ and b/ prefixes from diff headers are stripped from the file path."""
        svc = make_services_dir(tmp_path)
        original = "hello\n"
        patched  = "hello\nworld\n"
        make_file(svc, "svc/file.js", original)

        diff = make_modify_diff(original, patched, "svc/file.js")
        # Pass the file path with a/ prefix (as it would appear in the diff header)
        result = DiffApplier(svc).apply([FakeDiff("a/svc/file.js", diff)])

        assert result.success


# ─── EDGE CASE tests ──────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_multi_file_batch_all_succeed(self, tmp_path):
        """Multiple files all succeed in one apply() call."""
        svc = make_services_dir(tmp_path)
        files = {}
        diffs = []
        for i in range(5):
            orig = f"file{i} original\n"
            patched = f"file{i} patched\n"
            files[f"svc/file{i}.js"] = orig
            make_file(svc, f"svc/file{i}.js", orig)
            diffs.append(FakeDiff(f"svc/file{i}.js", make_modify_diff(orig, patched, f"svc/file{i}.js")))

        result = DiffApplier(svc).apply(diffs)

        assert result.success
        assert len(result.files_written) == 5
        for i in range(5):
            assert f"file{i} patched" in (svc / f"svc/file{i}.js").read_text()

    def test_modify_file_with_unicode_content(self, tmp_path):
        """File containing unicode (arrows, emoji, etc.) applies cleanly."""
        svc = make_services_dir(tmp_path)
        original = "// → arrow\nconst x = 1; // 🚀\n"
        patched  = "// → arrow\nconst x = 2; // 🚀 updated\n"
        make_file(svc, "svc/unicode.js", original)

        diff = make_modify_diff(original, patched, "svc/unicode.js")
        result = DiffApplier(svc).apply([FakeDiff("svc/unicode.js", diff)])

        assert result.success
        assert "x = 2" in (svc / "svc/unicode.js").read_text(encoding="utf-8")

    def test_no_diffs_returns_success(self, tmp_path):
        """Empty list of diffs is a no-op success."""
        svc = make_services_dir(tmp_path)
        result = DiffApplier(svc).apply([])
        assert result.success
        assert result.files_written == []

    def test_modify_nonexistent_file_fails(self, tmp_path):
        """MODIFY diff targeting a file that doesn't exist should fail."""
        svc = make_services_dir(tmp_path)
        diff = "--- a/svc/ghost.js\n+++ b/svc/ghost.js\n@@ -1,1 +1,1 @@\n-old\n+new\n"
        result = DiffApplier(svc).apply([FakeDiff("svc/ghost.js", diff)])
        assert not result.success

    def test_create_minimal_diff_without_git_headers(self, tmp_path):
        """CREATE diff with just --- /dev/null (no git header) — DiffApplier
        should auto-inject the missing headers and apply it cleanly."""
        svc = make_services_dir(tmp_path)
        # Minimal format without diff --git header — what the AI sometimes returns
        diff = (
            "--- /dev/null\n"
            "+++ b/svc/minimal.js\n"
            "@@ -0,0 +1,2 @@\n"
            "+const x = 1;\n"
            "+module.exports = x;\n"
        )
        result = DiffApplier(svc).apply([FakeDiff("svc/minimal.js", diff)])
        assert result.success, f"Should succeed after header injection: {result.failure_reasons}"
        assert (svc / "svc/minimal.js").exists()
        assert "const x = 1" in (svc / "svc/minimal.js").read_text()

    def test_content_to_diff_format_via_implementation_agent(self, tmp_path):
        """The _content_to_diff fallback in implementation_agent.py must now
        generate diffs with proper git headers that DiffApplier can apply."""
        svc = make_services_dir(tmp_path)
        # Simulate what _content_to_diff now generates
        file_path = "svc/utils/helper.js"
        content = "function helper() { return 42; }\nmodule.exports = helper;\n"
        lines = content.splitlines()
        diff = "\n".join([
            f"diff --git a/{file_path} b/{file_path}",
            "new file mode 100644",
            "--- /dev/null",
            f"+++ b/{file_path}",
            f"@@ -0,0 +1,{len(lines)} @@",
            *[f"+{l}" for l in lines],
        ]) + "\n"

        result = DiffApplier(svc).apply([FakeDiff(file_path, diff)])

        assert result.success
        written = (svc / file_path).read_text(encoding="utf-8")
        assert "function helper" in written
