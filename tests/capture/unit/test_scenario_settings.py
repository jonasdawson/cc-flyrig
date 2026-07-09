"""Tests for the scenario settings writer (capture.orchestrator.scenario_settings)."""

import json
from pathlib import Path


from cc_flyrig.capture.orchestrator.scenario_settings import (
    HookEntry,
    StatusLineEntry,
    _build_scenario_settings,
    write_scenario_settings,
)


class TestBuildScenarioSettings:
    def test_build_scenario_settings__single_entry__produces_hooks_dict(self):
        entries = [HookEntry("Stop", "python probe.py")]
        result = _build_scenario_settings(entries)
        assert result == {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python probe.py"}]}]}}

    def test_build_scenario_settings__with_matcher__includes_matcher_key(self):
        entries = [HookEntry("FileChanged", "python probe.py", matcher="watched.txt")]
        result = _build_scenario_settings(entries)
        assert result == {
            "hooks": {
                "FileChanged": [
                    {"matcher": "watched.txt", "hooks": [{"type": "command", "command": "python probe.py"}]}
                ]
            }
        }

    def test_build_scenario_settings__no_matcher__matcher_key_absent(self):
        entries = [HookEntry("Stop", "python probe.py")]
        result = _build_scenario_settings(entries)
        assert "matcher" not in result["hooks"]["Stop"][0]

    def test_build_scenario_settings__multiple_entries__all_present(self):
        entries = [HookEntry("Stop", "python probe.py"), HookEntry("SessionEnd", "python probe.py")]
        result = _build_scenario_settings(entries)
        assert set(result["hooks"]) == {"Stop", "SessionEnd"}

    def test_build_scenario_settings__empty__empty_hooks(self):
        assert _build_scenario_settings([]) == {"hooks": {}}

    def test_build_scenario_settings__hooks_only__byte_identical_to_pre_statusline_shape(self):
        """D5 back-compat gate: no statusline entries means no statusLine/subagentStatusLine keys."""
        entries = [HookEntry("Stop", "python probe.py"), HookEntry("FileChanged", "python probe.py", matcher="x")]
        result = _build_scenario_settings(entries)
        assert result == {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "python probe.py"}]}],
                "FileChanged": [{"matcher": "x", "hooks": [{"type": "command", "command": "python probe.py"}]}],
            }
        }
        assert set(result) == {"hooks"}

    def test_build_scenario_settings__with_statusline_entries__adds_top_level_keys(self):
        entries = [HookEntry("Stop", "python probe.py")]
        statusline_entries = [
            StatusLineEntry("statusLine", "python3 probe.py"),
            StatusLineEntry("subagentStatusLine", "python3 subagent_probe.py"),
        ]
        result = _build_scenario_settings(entries, statusline_entries)
        assert result["hooks"] == {"Stop": [{"hooks": [{"type": "command", "command": "python probe.py"}]}]}
        assert result["statusLine"] == {"type": "command", "command": "python3 probe.py"}
        assert result["subagentStatusLine"] == {
            "type": "command",
            "command": "python3 subagent_probe.py",
            "refreshInterval": 1,
        }


class TestWriteScenarioSettings:
    def test_write_scenario_settings__single_entry__writes_valid_json(self, tmp_path):
        entries = [HookEntry("Stop", "python probe.py")]
        out = write_scenario_settings(tmp_path / "settings.json", entries)
        data = json.loads(out.read_text())
        assert "hooks" in data
        assert "Stop" in data["hooks"]

    def test_write_scenario_settings__nested_missing_parents__creates_them(self, tmp_path):
        out = write_scenario_settings(tmp_path / "deep" / "dir" / "s.json", [])
        assert out.exists()

    def test_write_scenario_settings__any_entries__returns_resolved_path(self, tmp_path):
        out = write_scenario_settings(tmp_path / "s.json", [])
        assert isinstance(out, Path)
        assert out == tmp_path / "s.json"

    def test_write_scenario_settings__any_entries__ends_with_trailing_newline(self, tmp_path):
        out = write_scenario_settings(tmp_path / "s.json", [])
        assert out.read_text().endswith("\n")
