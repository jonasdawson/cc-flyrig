"""Tests for the Copier delivery template (generated/python/).

Verifies that ``uvx copier copy generated/python ./dest --data event=<snake> --force`` produces a
hook file byte-for-byte identical to the committed golden fixture.  The tests cover a representative
slice of the 30 events — one per structurally distinct x-decision-pattern — and a negative case for
an unknown cc_version.

``uvx copier`` is used via subprocess (copier is not a Python-importable dev dependency; it is
available in any environment that has uv installed).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("uvx"), reason="uvx not installed (copier is run via uvx)")

COPIER_TEMPLATE = Path(__file__).parent.parent.parent.parent / "scaffolds"
GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _copier_copy(
    event_snake: str, dst: Path, cc_version: str = "2.1.177", language: str = "python"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "uvx",
            "copier",
            "copy",
            "--force",
            "--data",
            f"language={language}",
            "--data",
            f"event={event_snake}",
            "--data",
            f"cc_version={cc_version}",
            str(COPIER_TEMPLATE),
            str(dst),
        ],
        capture_output=True,
        text=True,
    )


_PACKAGE_FILES = {"_harness.py", "__main__.py"}


def _assert_package_matches_golden(tmp_path: Path, event_snake: str) -> None:
    # Copier copies the template subdirectory's files flat into the destination.
    assert {f.name for f in tmp_path.iterdir()} == _PACKAGE_FILES
    golden = GOLDEN_DIR / event_snake
    for fname in _PACKAGE_FILES:
        assert (tmp_path / fname).read_text() == (golden / fname).read_text()


class TestCopierDelivery:
    def test_copy__pre_tool_use__produces_golden_identical_package(self, tmp_path):
        result = _copier_copy("pre_tool_use", tmp_path)
        assert result.returncode == 0
        _assert_package_matches_golden(tmp_path, "pre_tool_use")

    def test_copy__none_pattern_event__produces_golden_identical_package(self, tmp_path):
        # CwdChanged uses the "none" x-decision-pattern (side-effect only, no JSON output).
        result = _copier_copy("cwd_changed", tmp_path)
        assert result.returncode == 0
        _assert_package_matches_golden(tmp_path, "cwd_changed")

    def test_copy__worktree_path_return_event__produces_golden_identical_package(self, tmp_path):
        # WorktreeCreate uses the "worktree-path-return" pattern (bare path to stdout, not JSON).
        result = _copier_copy("worktree_create", tmp_path)
        assert result.returncode == 0
        _assert_package_matches_golden(tmp_path, "worktree_create")

    def test_copy__top_level_decision_event__produces_golden_identical_package(self, tmp_path):
        # PostToolUse uses the "top-level-decision" pattern (decision + reason at root level).
        result = _copier_copy("post_tool_use", tmp_path)
        assert result.returncode == 0
        _assert_package_matches_golden(tmp_path, "post_tool_use")

    def test_copy__worktree_remove_event__produces_golden_identical_package(self, tmp_path):
        # WorktreeRemove has no captured payload but its scaffold should still be deliverable.
        result = _copier_copy("worktree_remove", tmp_path)
        assert result.returncode == 0
        _assert_package_matches_golden(tmp_path, "worktree_remove")

    def test_copy__unknown_cc_version__fails_gracefully(self, tmp_path):
        # If cc_version has no corresponding pre-generated directory, copier should fail cleanly.
        result = _copier_copy("pre_tool_use", tmp_path, cc_version="0.0.0")
        assert result.returncode != 0


# The TypeScript scaffolds tree is its own committed reference (no separate golden dir): copier just
# copies it, so delivery is verified against scaffolds/typescript/cc-<version>/<event>/.
TS_VERSION = "2.1.185"
SCAFFOLDS_TS = COPIER_TEMPLATE / "typescript" / f"cc-{TS_VERSION}"
_TS_PACKAGE_FILES = {"_harness.ts", "index.ts"}


def _assert_ts_package_matches_scaffold(tmp_path: Path, event_snake: str) -> None:
    assert {f.name for f in tmp_path.iterdir()} == _TS_PACKAGE_FILES
    scaffold = SCAFFOLDS_TS / event_snake
    for fname in _TS_PACKAGE_FILES:
        assert (tmp_path / fname).read_text() == (scaffold / fname).read_text()


class TestCopierDeliveryTypeScript:
    def test_copy__typescript_pre_tool_use__produces_scaffold_identical_package(self, tmp_path):
        result = _copier_copy("pre_tool_use", tmp_path, cc_version=TS_VERSION, language="typescript")
        assert result.returncode == 0
        _assert_ts_package_matches_scaffold(tmp_path, "pre_tool_use")

    def test_copy__typescript_none_pattern_event__produces_scaffold_identical_package(self, tmp_path):
        # SessionEnd uses the "none" x-decision-pattern (side-effect only, handle returns void).
        result = _copier_copy("session_end", tmp_path, cc_version=TS_VERSION, language="typescript")
        assert result.returncode == 0
        _assert_ts_package_matches_scaffold(tmp_path, "session_end")
