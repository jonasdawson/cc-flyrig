"""Tests for spool consolidation (capture.spool_consolidator)."""

import json
from pathlib import Path

import pytest

from cc_flyrig.capture import spool_consolidator as c


def _write_envelope(spool: Path, name: str, *, event: str, payload: dict, version="2.1.168", run_id="run-1"):
    spool.mkdir(parents=True, exist_ok=True)
    envelope = {
        "cc_version": version,
        "event": event,
        "tool_name": payload.get("tool_name"),
        "timestamp": "2026-06-06T00:00:00+00:00",
        "run_id": run_id,
        "payload": payload,
    }
    (spool / name).write_text(json.dumps(envelope))


class TestSpoolConsolidator:
    def test_consolidate__spool_with_payloads__writes_per_event_jsonl_and_manifest(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="PreToolUse", payload={"tool_name": "Read"})
        _write_envelope(spool, "b.json", event="Stop", payload={"stop_hook_active": False})
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures)

        assert result.cc_version == "2.1.168"
        out = captures / "cc-2.1.168"
        assert (out / "PreToolUse.jsonl").exists()
        assert (out / "Stop.jsonl").exists()
        manifest = json.loads((out / "input_manifest.json").read_text())
        assert manifest["cc_version"] == "2.1.168"
        assert manifest["total_payloads"] == 2

    def test_consolidate__on_process_payload__applied_before_write(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="PreToolUse", payload={"tool_name": "Read", "secret": "raw"})
        captures = tmp_path / "captures"

        c.consolidate(spool, captures, on_process_payload=lambda p: {**p, "secret": "<REDACTED>"})

        line = (captures / "cc-2.1.168" / "PreToolUse.jsonl").read_text().strip()
        assert json.loads(line)["secret"] == "<REDACTED>"

    def test_consolidate__duplicate_payloads__deduped(self, tmp_path):
        spool = tmp_path / "spool"
        payload = {"tool_name": "Read", "x": 1}
        _write_envelope(spool, "a.json", event="PreToolUse", payload=payload)
        _write_envelope(spool, "b.json", event="PreToolUse", payload=payload)
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures)

        assert result.counts["PreToolUse"] == 1

    def test_consolidate__empty_spool__raises(self, tmp_path):
        with pytest.raises(ValueError):
            c.consolidate(tmp_path / "spool", tmp_path / "captures")

    def test_consolidate__mixed_versions_without_explicit_version__raises(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="Stop", payload={}, version="2.1.168")
        _write_envelope(spool, "b.json", event="Stop", payload={}, version="2.1.169")
        with pytest.raises(ValueError):
            c.consolidate(spool, tmp_path / "captures")

    def test_consolidate__mixed_versions_with_explicit_version__filters(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="Stop", payload={"a": 1}, version="2.1.168")
        _write_envelope(spool, "b.json", event="Stop", payload={"b": 2}, version="2.1.169")
        result = c.consolidate(spool, tmp_path / "captures", cc_version="2.1.168")
        assert result.total == 1
        assert result.cc_version == "2.1.168"

    def test_consolidate__subdir_given__nests_output_under_cc_version(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="StatusLine", payload={"cwd": "/tmp"})
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures, subdir="statusline")

        out = captures / "cc-2.1.168" / "statusline"
        assert result.out_dir == out
        assert (out / "StatusLine.jsonl").exists()
        assert (out / "input_manifest.json").exists()
        # the sibling hooks-style path (no subdir) is untouched by this call
        assert not (captures / "cc-2.1.168" / "StatusLine.jsonl").exists()

    def test_consolidate__no_subdir__writes_directly_under_cc_version_unchanged(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "a.json", event="PreToolUse", payload={"tool_name": "Read"})
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures)

        assert result.out_dir == captures / "cc-2.1.168"

    def _write_mixed_family_spool(self, spool: Path) -> None:
        _write_envelope(spool, "a.json", event="PreToolUse", payload={"tool_name": "Read"})
        _write_envelope(spool, "b.json", event="Stop", payload={"stop_hook_active": False})
        _write_envelope(spool, "c.json", event="StatusLine", payload={"cwd": "/tmp"})
        _write_envelope(spool, "d.json", event="SubagentStatusLine", payload={"agent": "worker"})

    def test_consolidate__events_given_for_statusline_family__writes_only_that_familys_jsonl(self, tmp_path):
        spool = tmp_path / "spool"
        self._write_mixed_family_spool(spool)
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures, events=("StatusLine", "SubagentStatusLine"), subdir="statusline")

        out = captures / "cc-2.1.168" / "statusline"
        assert result.out_dir == out
        assert (out / "StatusLine.jsonl").exists()
        assert (out / "SubagentStatusLine.jsonl").exists()
        assert not (out / "PreToolUse.jsonl").exists()
        assert not (out / "Stop.jsonl").exists()
        assert result.total == 2
        assert set(result.counts) == {"StatusLine", "SubagentStatusLine"}

    def test_consolidate__events_given_for_hooks_family__writes_no_statusline_jsonl_at_root(self, tmp_path):
        spool = tmp_path / "spool"
        self._write_mixed_family_spool(spool)
        captures = tmp_path / "captures"

        result = c.consolidate(spool, captures, events=("PreToolUse", "Stop"))

        out = captures / "cc-2.1.168"
        assert (out / "PreToolUse.jsonl").exists()
        assert (out / "Stop.jsonl").exists()
        assert not (out / "StatusLine.jsonl").exists()
        assert not (out / "SubagentStatusLine.jsonl").exists()
        assert set(result.counts) == {"PreToolUse", "Stop"}

    def test_consolidate__events_none__preserves_all_events_behavior(self, tmp_path):
        spool = tmp_path / "spool"
        self._write_mixed_family_spool(spool)

        captures_default = tmp_path / "captures_default"
        result_default = c.consolidate(spool, captures_default)

        captures_explicit_none = tmp_path / "captures_explicit_none"
        result_explicit_none = c.consolidate(spool, captures_explicit_none, events=None)

        assert set(result_default.counts) == {"PreToolUse", "Stop", "StatusLine", "SubagentStatusLine"}
        assert result_default.counts == result_explicit_none.counts
        assert result_default.total == result_explicit_none.total == 4

        out_default = captures_default / "cc-2.1.168"
        out_explicit_none = captures_explicit_none / "cc-2.1.168"
        for name in ("PreToolUse.jsonl", "Stop.jsonl", "StatusLine.jsonl", "SubagentStatusLine.jsonl"):
            assert (out_default / name).read_bytes() == (out_explicit_none / name).read_bytes()
