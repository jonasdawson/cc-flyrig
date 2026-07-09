"""Unit tests for the schema drift detector (schema.drift_detector).

Synthetic validation and drift-logic tests that run regardless of committed captures.
See tests/schema/integration/test_drift_detector.py for the CI gate against real captures.
"""

import json
from pathlib import Path

from cc_flyrig.schema import drift_detector
from cc_flyrig.schema.roster import EVENTS

_VALID_PRE_TOOL_USE = {
    "session_id": "abc123",
    "transcript_path": "/x.jsonl",
    "cwd": "/proj",
    "hook_event_name": "PreToolUse",
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/x.txt"},
    "tool_use_id": "toolu_01",
}


def _write_capture(tmp_path: Path, event: str, payloads: list[dict]) -> Path:
    cdir = tmp_path / "cc-test"
    cdir.mkdir(exist_ok=True)
    (cdir / f"{event}.jsonl").write_text("\n".join(json.dumps(p) for p in payloads) + "\n")
    return tmp_path


class TestCheckPayload:
    def test_check_payload__clean_payload__no_findings(self, schema):
        findings = drift_detector.check_payload(schema, "PreToolUse", _VALID_PRE_TOOL_USE, file=Path("x"), index=0)
        assert findings == []

    def test_check_payload__missing_required_field__validation_finding(self, schema):
        bad = {k: v for k, v in _VALID_PRE_TOOL_USE.items() if k != "tool_name"}
        findings = drift_detector.check_payload(schema, "PreToolUse", bad, file=Path("x"), index=0)
        assert any(f.kind == "validation" for f in findings)

    def test_check_payload__unknown_top_level_key__drift_finding(self, schema):
        drifted = {**_VALID_PRE_TOOL_USE, "brand_new_field": 1}
        findings = drift_detector.check_payload(schema, "PreToolUse", drifted, file=Path("x"), index=0)
        drift = [f for f in findings if f.kind == "drift"]
        assert drift and "brand_new_field" in drift[0].detail

    def test_check_payload__open_object_nested_key__not_drift(self, schema):
        # A novel key *inside* tool_input is fine — OpenObject is intentionally open.
        ok = {**_VALID_PRE_TOOL_USE, "tool_input": {"anything_here": True}}
        findings = drift_detector.check_payload(schema, "PreToolUse", ok, file=Path("x"), index=0)
        assert findings == []


class TestCheckCaptures:
    def test_check_captures__clean_tree__no_findings(self, schema, tmp_path):
        root = _write_capture(tmp_path, "PreToolUse", [_VALID_PRE_TOOL_USE])
        assert drift_detector.check_captures(schema, root) == []

    def test_check_captures__drifted_payload__reports_finding(self, schema, tmp_path):
        root = _write_capture(tmp_path, "PreToolUse", [{**_VALID_PRE_TOOL_USE, "extra": 1}])
        findings = drift_detector.check_captures(schema, root)
        assert any(f.kind == "drift" for f in findings)

    def test_check_captures__unknown_event_file__unknown_event_finding(self, schema, tmp_path):
        root = _write_capture(tmp_path, "NotARealEvent", [{"x": 1}])
        findings = drift_detector.check_captures(schema, root)
        assert any(f.kind == "unknown-event" for f in findings)

    def test_count_payloads__multi_line_capture__counts_nonblank_lines(self, schema, tmp_path):
        root = _write_capture(tmp_path, "Stop", [{"a": 1}, {"b": 2}])
        assert drift_detector.count_payloads(root) == 2


class TestCcVersionScoping:
    """A diff run for one version must not read another version's committed artifacts — the bug
    behind #diff --cc-version <version-with-no-hooks-schema> failing due to an unrelated version's
    hooks_menu.json triggering the hooks branch."""

    def _write_menu_for(self, tmp_path, version, events):
        cdir = tmp_path / f"cc-{version}"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "hooks_menu.json").write_text(json.dumps({"cc_version": version, "events": events}))
        return tmp_path

    def test_find_capture_dirs__cc_version_given__returns_only_that_version(self, tmp_path):
        (tmp_path / "cc-1.0.0").mkdir()
        (tmp_path / "cc-2.0.0").mkdir()
        assert drift_detector.find_capture_dirs(tmp_path, cc_version="1.0.0") == [tmp_path / "cc-1.0.0"]

    def test_find_capture_dirs__cc_version_not_committed__returns_empty(self, tmp_path):
        (tmp_path / "cc-1.0.0").mkdir()
        assert drift_detector.find_capture_dirs(tmp_path, cc_version="9.9.9") == []

    def test_count_payloads__cc_version_given__ignores_other_versions(self, tmp_path):
        (tmp_path / "cc-1.0.0").mkdir()
        (tmp_path / "cc-1.0.0" / "Stop.jsonl").write_text('{"a": 1}\n')
        (tmp_path / "cc-2.0.0").mkdir()
        (tmp_path / "cc-2.0.0" / "Stop.jsonl").write_text('{"a": 1}\n{"b": 1}\n')

        assert drift_detector.count_payloads(tmp_path, cc_version="1.0.0") == 1
        assert drift_detector.count_payloads(tmp_path, cc_version="2.0.0") == 2

    def test_has_documented_hooks__cc_version_given__ignores_other_versions_menu(self, tmp_path):
        root = self._write_menu_for(tmp_path, "1.0.0", [{"event": "PreToolUse"}])
        assert drift_detector.has_documented_hooks(root, cc_version="1.0.0") is True
        assert drift_detector.has_documented_hooks(root, cc_version="9.9.9") is False

    def test_check_documented_hooks__cc_version_given__does_not_report_other_versions_drift(self, schema, tmp_path):
        # cc-1.0.0 has a clean roster; cc-2.0.0's menu is drifted. Diffing 1.0.0 must not see 2.0.0's findings.
        clean_events = [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS]
        root = self._write_menu_for(tmp_path, "1.0.0", clean_events)
        self._write_menu_for(
            root, "2.0.0", [{"event": e, "input_fields": [], "output_fields": []} for e in [*EVENTS, "Bogus"]]
        )

        assert drift_detector.check_documented_hooks(schema, root, cc_version="1.0.0") == []
        findings = drift_detector.check_documented_hooks(schema, root, cc_version="2.0.0")
        assert any(f.kind == "cc-hooks-skill-drift" for f in findings)


class TestSurfaceSubdirRegistry:
    """A second surface (e.g. statusline) lives in cc-<version>/<subdir>/ beside the hooks-style
    top-level files; the ``subdir`` kwarg widens count_payloads/check_captures to reach it without
    touching the default (hooks) path, per U5's {artifact -> schema} registry."""

    def test_count_payloads__subdir_given__counts_only_nested_tree(self, tmp_path):
        cdir = tmp_path / "cc-test"
        cdir.mkdir()
        (cdir / "PreToolUse.jsonl").write_text('{"a": 1}\n')
        sub = cdir / "statusline"
        sub.mkdir()
        (sub / "StatusLine.jsonl").write_text('{"b": 1}\n{"c": 1}\n')

        assert drift_detector.count_payloads(tmp_path) == 1
        assert drift_detector.count_payloads(tmp_path, subdir="statusline") == 2

    def test_count_payloads__subdir_absent__returns_zero(self, tmp_path):
        cdir = tmp_path / "cc-test"
        cdir.mkdir()
        assert drift_detector.count_payloads(tmp_path, subdir="statusline") == 0

    def test_check_captures__subdir_given__validates_against_given_schema_not_hooks(
        self, schema, statusline_schema, tmp_path
    ):
        cdir = tmp_path / "cc-test"
        sub = cdir / "statusline"
        sub.mkdir(parents=True)
        good = {
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "/tmp",
            "prompt_id": "p",
            "columns": 80,
            "tasks": [],
        }
        (sub / "SubagentStatusLine.jsonl").write_text(json.dumps(good) + "\n")

        assert drift_detector.check_captures(statusline_schema, tmp_path, subdir="statusline") == []
        # top-level (hooks) scan is unaffected — no files sit directly under cc-test/
        assert drift_detector.check_captures(schema, tmp_path) == []

    def test_check_captures__subdir_absent__returns_no_findings(self, statusline_schema, tmp_path):
        (tmp_path / "cc-test").mkdir()
        assert drift_detector.check_captures(statusline_schema, tmp_path, subdir="statusline") == []


class TestCheckDocumentedEvents:
    def test_check_documented_events__matches_ir__no_findings(self):
        assert drift_detector.check_documented_events(EVENTS, source=Path("hooks_menu.json")) == []

    def test_check_documented_events__menu_only_event__skill_drift_finding(self):
        findings = drift_detector.check_documented_events([*EVENTS, "BrandNewHook"], source=Path("hooks_menu.json"))
        assert [f.kind for f in findings] == ["cc-hooks-skill-drift"]
        assert findings[0].event == "BrandNewHook"
        assert "absent from IR" in findings[0].detail

    def test_check_documented_events__missing_event__skill_drift_finding(self):
        partial = [e for e in EVENTS if e != "PreToolUse"]
        findings = drift_detector.check_documented_events(partial, source=Path("hooks_menu.json"))
        assert [f.kind for f in findings] == ["cc-hooks-skill-drift"]
        assert findings[0].event == "PreToolUse"
        assert "not documented by /hooks" in findings[0].detail


class TestCheckDocumentedFields:
    def test_check_documented_fields__field_in_ir__no_findings(self, schema):
        entry = {"event": "PreToolUse", "input_fields": ["tool_name"], "output_fields": ["hookSpecificOutput"]}
        assert drift_detector.check_documented_fields(schema, [entry], source=Path("hooks_menu.json")) == []

    def test_check_documented_fields__input_field_absent_from_ir__advisory_finding(self, schema):
        entry = {"event": "PreToolUse", "input_fields": ["totally_new_field"], "output_fields": []}
        findings = drift_detector.check_documented_fields(schema, [entry], source=Path("hooks_menu.json"))
        assert [f.kind for f in findings] == ["cc-hooks-skill-advisory"]
        assert "totally_new_field" in findings[0].detail

    def test_check_documented_fields__no_parsed_fields__no_findings(self, schema):
        entry = {"event": "PreToolUse", "input_fields": [], "output_fields": []}
        assert drift_detector.check_documented_fields(schema, [entry], source=Path("hooks_menu.json")) == []


def _write_menu(tmp_path: Path, events: list[dict]) -> Path:
    cdir = tmp_path / "cc-test"
    cdir.mkdir(exist_ok=True)
    (cdir / "hooks_menu.json").write_text(json.dumps({"cc_version": "test", "events": events}))
    return tmp_path


class TestCheckDocumentedHooks:
    def test_check_documented_hooks__full_roster_no_fields__no_findings(self, schema, tmp_path):
        root = _write_menu(tmp_path, [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS])
        assert drift_detector.check_documented_hooks(schema, root) == []

    def test_check_documented_hooks__extra_event__skill_drift(self, schema, tmp_path):
        events = [{"event": e, "input_fields": [], "output_fields": []} for e in [*EVENTS, "Bogus"]]
        root = _write_menu(tmp_path, events)
        findings = drift_detector.check_documented_hooks(schema, root)
        assert any(f.kind == "cc-hooks-skill-drift" and f.event == "Bogus" for f in findings)

    def test_check_documented_hooks__no_menu_committed__no_findings(self, schema, tmp_path):
        assert drift_detector.check_documented_hooks(schema, tmp_path) == []

    def test_has_documented_hooks__no_menu_committed__returns_false(self, tmp_path):
        assert drift_detector.has_documented_hooks(tmp_path) is False

    def test_has_documented_hooks__menu_committed__returns_true(self, tmp_path):
        _write_menu(tmp_path, [{"event": "PreToolUse", "input_fields": [], "output_fields": []}])
        assert drift_detector.has_documented_hooks(tmp_path) is True
