"""Tests for capture utility modules (capture.util.payload_scrubber, user_settings_guard, schema.keys)."""

from pathlib import Path

import pytest

from cc_flyrig.capture.util.payload_scrubber import scrub
from cc_flyrig.capture.util.user_settings_guard import preserve_user_settings, user_settings_path
from cc_flyrig.schema.keys import input_def_name


class TestPayloadScrubber:
    def test_scrub__home_path_in_string__replaced_with_placeholder(self):
        out = scrub({"cwd": "/home/alice/project"}, home="/home/alice")
        assert out == {"cwd": "<HOME>/project"}

    def test_scrub__sensitive_keys__redacted(self):
        out = scrub(
            {"session_id": "abc", "transcript_path": "/home/alice/.claude/t.jsonl", "keep": "v"},
            home="/home/alice",
        )
        assert out["session_id"] == "<SESSION_ID>"
        assert out["transcript_path"] == "<TRANSCRIPT_PATH>"
        assert out["keep"] == "v"

    def test_scrub__nested_structures__scrubbed_recursively(self):
        out = scrub({"a": [{"session_id": "x"}], "b": {"cwd": "/home/alice/p"}}, home="/home/alice")
        assert out["a"][0]["session_id"] == "<SESSION_ID>"
        assert out["b"]["cwd"] == "<HOME>/p"

    def test_scrub__scratchpad_dir__redacted(self):
        # cc-2.1.332: a per-session /tmp path embedding the session UUID, outside $HOME.
        out = scrub(
            {"scratchpad_dir": "/tmp/claude-1000/-tmp-x/0b5c8e2a-1111-2222-3333-444455556666/scratchpad"},
            home="/home/alice",
        )
        assert out == {"scratchpad_dir": "<SCRATCHPAD_DIR>"}


class TestPreserveUserSettings:
    def test_preserve_user_settings__file_modified_inside__restored_byte_for_byte_and_notice_printed(
        self, tmp_path, capsys
    ):
        target = tmp_path / "settings.json"
        original = b'{\n  "theme": "dark"\n}\n'
        target.write_bytes(original)
        with preserve_user_settings(target):
            target.write_text('{"theme": "dark", "model": "haiku"}')
        assert target.read_bytes() == original
        assert f"restored {target}" in capsys.readouterr().err

    def test_preserve_user_settings__file_unchanged__untouched_and_no_notice(self, tmp_path, capsys):
        target = tmp_path / "settings.json"
        target.write_bytes(b"{}\n")
        mtime = target.stat().st_mtime_ns
        with preserve_user_settings(target):
            pass
        assert target.read_bytes() == b"{}\n"
        assert target.stat().st_mtime_ns == mtime  # not rewritten
        assert capsys.readouterr().err == ""

    def test_preserve_user_settings__file_created_inside_when_absent__removed(self, tmp_path, capsys):
        target = tmp_path / "settings.json"
        with preserve_user_settings(target):
            target.write_text('{"model": "haiku"}')
        assert not target.exists()
        assert "restored" in capsys.readouterr().err

    def test_preserve_user_settings__body_raises__still_restored(self, tmp_path):
        target = tmp_path / "settings.json"
        target.write_bytes(b'{"a": 1}')
        with pytest.raises(KeyboardInterrupt), preserve_user_settings(target):
            target.write_bytes(b'{"a": 2}')
            raise KeyboardInterrupt
        assert target.read_bytes() == b'{"a": 1}'

    def test_user_settings_path__claude_config_dir_set__uses_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        assert user_settings_path() == tmp_path / "settings.json"

    def test_user_settings_path__unset__falls_back_to_home_dot_claude(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert user_settings_path() == Path(tmp_path) / ".claude" / "settings.json"


class TestSchemaKeys:
    def test_input_def_name__event__appends_input_suffix(self):
        assert input_def_name("Stop") == "StopInput"
