"""Integration tests for the worktree capture shim (capture_harness/hooks/worktree_probe.py).

Exercised as a subprocess (same pattern as test_probe.py) to cover the
"standalone / never import the package" contract, plus the stdout-path requirement.
"""

import json
import subprocess
import sys
from pathlib import Path

WORKTREE_PROBE = Path(__file__).parent.parent.parent.parent / "capture_harness" / "hooks" / "worktree_probe.py"

_PAYLOAD = {
    "hook_event_name": "WorktreeCreate",
    "name": "test-worktree",
    "session_id": "abc123",
}


def _run(stdin: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": __import__("os").environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(WORKTREE_PROBE)],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
    )


class TestWorktreeProbe:
    def test_worktree_probe__valid_payload__prints_abspath_and_spools(self, tmp_path):
        """P7: stdout is one absolute existing dir path; an envelope is spooled with event = 'WorktreeCreate'."""
        spool = tmp_path / "spool"
        result = _run(
            json.dumps(_PAYLOAD),
            env_extra={"FLYRIG_SPOOL_DIR": str(spool), "FLYRIG_RUN_ID": "b1:wt", "FLYRIG_CC_VERSION": "2.1.168"},
        )

        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1, f"expected exactly one stdout line, got: {result.stdout!r}"
        worktree_path = Path(lines[0])
        assert worktree_path.is_absolute()
        assert worktree_path.is_dir()

        envelopes = list(spool.glob("*.json"))
        assert len(envelopes) == 1
        env_data = json.loads(envelopes[0].read_text())
        assert env_data["event"] == "WorktreeCreate"
        assert env_data["run_id"] == "b1:wt"

    def test_worktree_probe__no_spool_env__still_prints_a_path(self):
        """P7: without FLYRIG_SPOOL_DIR the shim still prints a valid abs path (contract never broken)."""
        result = _run(json.dumps(_PAYLOAD))

        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert Path(lines[0]).is_absolute()

    def test_worktree_probe__unwritable_root__still_prints_a_path(self, tmp_path):
        """P7: if the preferred worktree root is unwritable, falls back to mkdtemp and still prints."""
        bad_spool = "/proc/no-such/path/spool"
        result = _run(
            json.dumps(_PAYLOAD),
            env_extra={"FLYRIG_SPOOL_DIR": bad_spool, "FLYRIG_RUN_ID": "b1:wt"},
        )

        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert Path(lines[0]).is_absolute()

    def test_worktree_probe__empty_stdin__still_prints_a_path(self, tmp_path):
        """P7: empty stdin (malformed / missing payload) never breaks the path contract."""
        spool = tmp_path / "spool"
        result = _run("", env_extra={"FLYRIG_SPOOL_DIR": str(spool)})

        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert Path(lines[0]).is_absolute()
