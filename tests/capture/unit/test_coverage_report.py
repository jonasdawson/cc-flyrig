"""Tests for the coverage report (capture.coverage_report)."""

import json
from pathlib import Path

import pytest

from cc_flyrig.capture.coverage_report import (
    FAIL,
    MISSING,
    NOT_ATTEMPTED,
    NOT_TESTED,
    OBSERVED,
    PASS,
    UNOBSERVABLE,
    build_documented_hooks_report,
    build_input_report,
    build_output_report,
    build_statusline_report,
    render_documented_hooks,
    render_input_coverage,
    render_output_coverage,
    render_statusline_coverage,
)
from cc_flyrig.capture.scenario_manifest import parse_manifest
from cc_flyrig.schema.roster import EVENTS

_SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "schemas" / "cc-2.1.168" / "hooks.schema.json").read_text())


def _write_menu_json(tmp_path: Path, events: list[dict], cc_version: str = "1.2.3") -> Path:
    path = tmp_path / "hooks_menu.json"
    path.write_text(json.dumps({"cc_version": cc_version, "events": events}))
    return path


_MANIFEST_TEXT = """
[[scenario]]
id = "read"
prompt = "go"
[scenario.expect]
events = ["PreToolUse", "PostToolUse", "Stop"]
tools = ["Read"]
"""

_MINIMAL_INVENTORY = [
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "deny"},
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "allow"},
    {"event": "PostToolUse", "field": "decision", "variant": "block"},
]


def _write_events(captures_dir: Path, **events: list[dict]) -> Path:
    captures_dir.mkdir(parents=True, exist_ok=True)
    for event, payloads in events.items():
        (captures_dir / f"{event}.jsonl").write_text("".join(json.dumps(p) + "\n" for p in payloads))
    return captures_dir


@pytest.fixture
def captures(tmp_path) -> Path:
    d = _write_events(
        tmp_path / "cc-2.1.168",
        PreToolUse=[{"tool_name": "Read"}, {"tool_name": "Bash"}],
        Stop=[{"stop_hook_active": False}],
    )
    (d / "input_manifest.json").write_text(json.dumps({"captured_at": "2026-06-06T00:00:00+00:00"}))
    return d


@pytest.fixture
def manifest():
    return parse_manifest(_MANIFEST_TEXT)


class TestBuildInputReport:
    def test_build_input_report__statuses__assigned_per_event(self, manifest, captures):
        by_event = {r.event: r for r in build_input_report(manifest, captures, "2.1.168").rows}
        assert by_event["PreToolUse"].status == OBSERVED
        assert by_event["Stop"].status == OBSERVED
        assert by_event["PostToolUse"].status == MISSING  # expected, not captured
        assert by_event["CwdChanged"].status == NOT_ATTEMPTED  # no scenario targets it

    def test_build_input_report__expected_event_with_zero_count__is_missing(self, tmp_path):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.expect]\nevents = ["WorktreeRemove"]\n'
        captures = _write_events(tmp_path / "cc-x")  # nothing captured
        by_event = {r.event: r for r in build_input_report(parse_manifest(text), captures, "x").rows}
        assert by_event["WorktreeRemove"].status == MISSING

    def test_build_input_report__count_positive__wins_over_expected(self, tmp_path):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.expect]\nevents = ["Stop"]\n'
        captures = _write_events(tmp_path / "cc-x", Stop=[{"stop_hook_active": False}])
        by_event = {r.event: r for r in build_input_report(parse_manifest(text), captures, "x").rows}
        assert by_event["Stop"].status == OBSERVED

    def test_build_input_report__tool_names__collected_from_payloads(self, manifest, captures):
        tools = dict(build_input_report(manifest, captures, "2.1.168").tools)
        assert tools["PreToolUse"] == ("Bash", "Read")

    def test_build_input_report__post_tool_batch__reads_tool_calls(self, tmp_path):
        captures = _write_events(
            tmp_path / "cc-x",
            PostToolBatch=[{"tool_calls": [{"tool_name": "Read"}, {"tool_name": "Write"}]}],
        )
        tools = dict(build_input_report(parse_manifest(_MANIFEST_TEXT), captures, "x").tools)
        assert tools["PostToolBatch"] == ("Read", "Write")

    def test_build_input_report__tally__counts_statuses(self, manifest, captures):
        report = build_input_report(manifest, captures, "2.1.168")
        assert report.observed == 2  # PreToolUse, Stop
        assert report.missing == 1  # PostToolUse
        assert report.total_events == report.observed + report.missing + report.not_attempted


class TestRenderInputCoverage:
    def test_render_input_coverage__model__contains_sections_and_flags_missing(self, manifest, captures):
        out = render_input_coverage(build_input_report(manifest, captures, "2.1.168"))
        assert "# Capture coverage — cc-2.1.168" in out
        assert "## Events" in out
        assert "## Tools observed" in out
        assert "expected-but-missing" in out  # PostToolUse should flag
        assert out.endswith("\n")


class TestBuildOutputReport:
    def test_build_output_report__manifest_absent__all_rows_not_tested(self, tmp_path):
        report = build_output_report(tmp_path / "nonexistent.json", _MINIMAL_INVENTORY)
        assert all(r.result == NOT_TESTED for r in report.rows)
        assert report.not_tested == len(_MINIMAL_INVENTORY)
        assert report.passed == 0
        assert report.failed == 0
        assert report.unobservable == 0
        assert report.validated_at is None

    def test_build_output_report__manifest_has_pass_row__classifies_pass(self, tmp_path):
        manifest = {
            "cc_version": "2.1.177",
            "validated_at": "2026-06-19T12:00:00+00:00",
            "results": [
                {
                    "event": "PreToolUse",
                    "field": "hookSpecificOutput.permissionDecision",
                    "variant": "deny",
                    "assertion": "PostToolUse absent",
                    "result": PASS,
                }
            ],
        }
        (tmp_path / "output_manifest.json").write_text(json.dumps(manifest))
        report = build_output_report(tmp_path / "output_manifest.json", _MINIMAL_INVENTORY)
        by_key = {(r.event, r.field, r.variant): r for r in report.rows}
        deny_row = by_key[("PreToolUse", "hookSpecificOutput.permissionDecision", "deny")]
        assert deny_row.result == PASS
        assert deny_row.assertion == "PostToolUse absent"

    def test_build_output_report__manifest_missing_row__classifies_not_tested(self, tmp_path):
        manifest = {
            "cc_version": "2.1.177",
            "validated_at": "2026-06-19T12:00:00+00:00",
            "results": [],
        }
        (tmp_path / "output_manifest.json").write_text(json.dumps(manifest))
        report = build_output_report(tmp_path / "output_manifest.json", _MINIMAL_INVENTORY)
        assert all(r.result == NOT_TESTED for r in report.rows)

    def test_build_output_report__tally__counts_each_result(self, tmp_path):
        manifest = {
            "cc_version": "2.1.177",
            "validated_at": "2026-06-19T12:00:00+00:00",
            "results": [
                {
                    "event": "PreToolUse",
                    "field": "hookSpecificOutput.permissionDecision",
                    "variant": "deny",
                    "result": PASS,
                },  # noqa: E501
                {
                    "event": "PreToolUse",
                    "field": "hookSpecificOutput.permissionDecision",
                    "variant": "allow",
                    "result": FAIL,
                },  # noqa: E501
                {"event": "PostToolUse", "field": "decision", "variant": "block", "result": UNOBSERVABLE},
            ],
        }
        (tmp_path / "output_manifest.json").write_text(json.dumps(manifest))
        report = build_output_report(tmp_path / "output_manifest.json", _MINIMAL_INVENTORY)
        assert report.passed == 1
        assert report.failed == 1
        assert report.unobservable == 1
        assert report.not_tested == 0


class TestRenderOutputCoverage:
    def test_render_output_coverage__valid_report__produces_markdown_with_limit_note(self, tmp_path):
        report = build_output_report(tmp_path / "nonexistent.json", _MINIMAL_INVENTORY)
        out = render_output_coverage(report)
        assert "# Output Contract Coverage" in out
        assert "Validation limit" in out
        assert "not yet validated" in out
        assert "not-tested" in out
        assert out.endswith("\n")

    # Verify the unused constants are reachable (they're part of the public API).
    def test_constants__status_markers__have_expected_wire_values(self):
        assert PASS == "pass"
        assert FAIL == "fail"
        assert UNOBSERVABLE == "unobservable"
        assert NOT_TESTED == "not-tested"


class TestBuildDocumentedHooksReport:
    def test_build__full_roster__matches_ir(self, tmp_path):
        events = [
            {"event": e, "description": "", "input_fields": [], "output_fields": [], "exit_codes": ""} for e in EVENTS
        ]
        report = build_documented_hooks_report(_write_menu_json(tmp_path, events), _SCHEMA)
        assert report.matches_ir
        assert report.total == len(EVENTS)
        assert report.advisory == []

    def test_build__extra_event_and_new_field__records_diff_and_advisory(self, tmp_path):
        events = [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS]
        events.append({"event": "Bogus", "input_fields": [], "output_fields": []})
        events[0] = {"event": EVENTS[0], "input_fields": ["totally_new_field"], "output_fields": []}
        report = build_documented_hooks_report(_write_menu_json(tmp_path, events), _SCHEMA)
        assert not report.matches_ir
        assert "Bogus" in report.menu_only
        assert any("totally_new_field" in a["detail"] for a in report.advisory)


class TestRenderDocumentedHooks:
    def test_render__matching_roster__produces_markdown(self, tmp_path):
        events = [
            {
                "event": "PreToolUse",
                "description": "Before tool execution",
                "input_fields": [],
                "output_fields": [],
                "exit_codes": "Exit code 2 - block",
                "input_note": "Input to command is JSON of tool call arguments.",
                "output_note": "",
            }
        ]
        # A single-event menu differs from the full IR roster; render still succeeds.
        report = build_documented_hooks_report(_write_menu_json(tmp_path, events), _SCHEMA)
        out = render_documented_hooks(report)
        assert "# `/hooks` Menu" in out
        assert "roster-authoritative" in out
        assert "PreToolUse" in out
        assert out.endswith("\n")


_SUBAGENT_MANIFEST_TEXT = """
[[scenario]]
id = "read"
prompt = "go"
[scenario.expect]
events = ["PreToolUse", "PostToolUse", "Stop"]
tools = ["Read"]

[[scenario]]
id = "delegate"
prompt = "delegate to a subagent"
[scenario.expect]
events = ["SubagentStart", "SubagentStop"]
"""

_NO_SUBAGENT_MANIFEST_TEXT = """
[[scenario]]
id = "read"
prompt = "go"
[scenario.expect]
events = ["PreToolUse", "PostToolUse", "Stop"]
tools = ["Read"]
"""


@pytest.fixture
def subagent_manifest():
    return parse_manifest(_SUBAGENT_MANIFEST_TEXT)


@pytest.fixture
def no_subagent_manifest():
    return parse_manifest(_NO_SUBAGENT_MANIFEST_TEXT)


class TestBuildStatuslineReport:
    def test_build_statusline_report__subagent_scenario_ran__subagent_statusline_is_missing(
        self, subagent_manifest, tmp_path
    ):
        captures = _write_events(
            tmp_path / "cc-2.1.168" / "statusline",
            StatusLine=[{"model": {"id": "x"}}],
        )
        by_event = {r.event: r for r in build_statusline_report(subagent_manifest, captures, "2.1.168").rows}
        assert by_event["StatusLine"].status == OBSERVED
        assert by_event["SubagentStatusLine"].status == MISSING

    def test_build_statusline_report__no_subagent_scenario__subagent_statusline_is_not_attempted(
        self, no_subagent_manifest, tmp_path
    ):
        captures = _write_events(
            tmp_path / "cc-2.1.168" / "statusline",
            StatusLine=[{"model": {"id": "x"}}],
        )
        by_event = {r.event: r for r in build_statusline_report(no_subagent_manifest, captures, "2.1.168").rows}
        assert by_event["StatusLine"].status == OBSERVED
        assert by_event["SubagentStatusLine"].status == NOT_ATTEMPTED

    def test_build_statusline_report__no_subagent_scenario_but_observed__still_marks_observed(
        self, no_subagent_manifest, tmp_path
    ):
        captures = _write_events(
            tmp_path / "cc-2.1.168" / "statusline",
            StatusLine=[{"model": {"id": "x"}}],
            SubagentStatusLine=[{"model": {"id": "x"}}],
        )
        by_event = {r.event: r for r in build_statusline_report(no_subagent_manifest, captures, "2.1.168").rows}
        assert by_event["SubagentStatusLine"].status == OBSERVED

    def test_build_statusline_report__status_line_never_captured__is_missing_not_not_attempted(
        self, no_subagent_manifest, tmp_path
    ):
        captures = _write_events(tmp_path / "cc-2.1.168" / "statusline")  # nothing captured
        by_event = {r.event: r for r in build_statusline_report(no_subagent_manifest, captures, "2.1.168").rows}
        assert by_event["StatusLine"].status == MISSING

    def test_build_statusline_report__tally__counts_statuses(self, subagent_manifest, tmp_path):
        captures = _write_events(
            tmp_path / "cc-2.1.168" / "statusline",
            StatusLine=[{"model": {"id": "x"}}],
        )
        report = build_statusline_report(subagent_manifest, captures, "2.1.168")
        assert report.observed == 1
        assert report.missing == 1
        assert report.total_events == report.observed + report.missing + report.not_attempted


class TestRenderStatuslineCoverage:
    def test_render_statusline_coverage__model__contains_header_and_event_rows(self, subagent_manifest, tmp_path):
        captures = _write_events(
            tmp_path / "cc-2.1.168" / "statusline",
            StatusLine=[{"model": {"id": "x"}}],
        )
        report = build_statusline_report(subagent_manifest, captures, "2.1.168")
        out = render_statusline_coverage(report)
        assert "# Statusline capture coverage — cc-2.1.168" in out
        assert "StatusLine" in out
        assert "SubagentStatusLine" in out
        assert "expected-but-missing" in out
        assert out.endswith("\n")
