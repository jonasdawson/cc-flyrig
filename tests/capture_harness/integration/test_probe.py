"""Integration tests for the standalone capture probe (capture_harness/hooks/probe.py).

The probe is exercised as a subprocess, the way Claude Code invokes a command hook, so the test also
covers its "never import the package / never touch stdout" contract.
"""

import json
import subprocess
import sys
from pathlib import Path

PROBE = Path(__file__).parent.parent.parent.parent / "capture_harness" / "hooks" / "probe.py"

_PAYLOAD = {
    "session_id": "abc123",
    "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
    "cwd": "/home/user/project",
    "hook_event_name": "PreToolUse",
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/x.txt"},
    "tool_use_id": "toolu_01",
}


def _run(stdin: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": __import__("os").environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(PROBE)],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
    )


def _json_files(d: Path) -> list[Path]:
    return sorted(d.glob("*.json"))


class TestProbe:
    def test_probe__missing_spool_env__exits_zero_empty_stdout(self, tmp_path):
        result = _run(json.dumps(_PAYLOAD))  # no FLYRIG_SPOOL_DIR
        assert result.returncode == 0
        assert result.stdout == ""

    def test_probe__valid_payload__writes_single_envelope_file(self, tmp_path):
        spool = tmp_path / "spool"
        result = _run(
            json.dumps(_PAYLOAD),
            {"FLYRIG_SPOOL_DIR": str(spool), "FLYRIG_CC_VERSION": "2.1.168", "FLYRIG_RUN_ID": "run-1"},
        )
        assert result.returncode == 0
        assert result.stdout == ""

        files = _json_files(spool)
        assert len(files) == 1
        assert not list(spool.glob("*.tmp"))  # no half-written temp left behind

        envelope = json.loads(files[0].read_text())
        assert envelope["cc_version"] == "2.1.168"
        assert envelope["event"] == "PreToolUse"
        assert envelope["tool_name"] == "Read"
        assert envelope["run_id"] == "run-1"
        assert envelope["payload"] == _PAYLOAD
        assert "timestamp" in envelope

    def test_probe__malformed_stdin__exits_zero_and_writes_nothing(self, tmp_path):
        spool = tmp_path / "spool"
        result = _run("this is not json", {"FLYRIG_SPOOL_DIR": str(spool)})
        assert result.returncode == 0
        assert result.stdout == ""
        assert _json_files(spool) == []

    def test_probe__two_invocations__write_distinct_files(self, tmp_path):
        spool = tmp_path / "spool"
        env = {"FLYRIG_SPOOL_DIR": str(spool), "FLYRIG_RUN_ID": "run-1"}
        _run(json.dumps(_PAYLOAD), env)
        _run(json.dumps({**_PAYLOAD, "hook_event_name": "PostToolUse"}), env)
        files = _json_files(spool)
        assert len(files) == 2
        events = {json.loads(f.read_text())["event"] for f in files}
        assert events == {"PreToolUse", "PostToolUse"}
