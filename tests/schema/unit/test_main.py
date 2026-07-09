"""Tests for the schema CLI (__main__) — the `check` command (formerly `capture diff`)."""

import json

import pytest

from cc_flyrig.capture.__main__ import main as capture_main
from cc_flyrig.schema.__main__ import main


class TestCmdCheck:
    def test_cmd_check__no_committed_captures__exits_zero(self, tmp_path):
        """check command with no committed captures reports clean and exits 0."""
        rc = main(
            [
                "check",
                "--cc-version",
                "2.1.168",
                "--captures",
                str(tmp_path),
            ]
        )

        assert rc == 0

    def _write_menu(self, tmp_path, events):
        cdir = tmp_path / "cc-2.1.168"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "hooks_menu.json").write_text(json.dumps({"cc_version": "2.1.168", "events": events}))
        return tmp_path

    def test_cmd_check__menu_matches_ir__exits_zero(self, tmp_path):
        from cc_flyrig.schema.roster import EVENTS

        captures = self._write_menu(tmp_path, [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS])
        assert main(["check", "--cc-version", "2.1.168", "--captures", str(captures)]) == 0

    def test_cmd_check__menu_extra_event__exits_one(self, tmp_path):
        from cc_flyrig.schema.roster import EVENTS

        events = [{"event": e, "input_fields": [], "output_fields": []} for e in [*EVENTS, "Bogus"]]
        captures = self._write_menu(tmp_path, events)
        assert main(["check", "--cc-version", "2.1.168", "--captures", str(captures)]) == 1

    def test_cmd_check__advisory_field_only__exits_zero(self, tmp_path, capsys):
        from cc_flyrig.schema.roster import EVENTS

        events = [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS]
        events[0] = {"event": EVENTS[0], "input_fields": ["totally_new_field"], "output_fields": []}
        captures = self._write_menu(tmp_path, events)
        assert main(["check", "--cc-version", "2.1.168", "--captures", str(captures)]) == 0
        assert "advisory" in capsys.readouterr().out

    def _write_statusline_capture(self, tmp_path, payload, version="2.1.198"):
        cdir = tmp_path / f"cc-{version}" / "statusline"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "SubagentStatusLine.jsonl").write_text(json.dumps(payload) + "\n")
        return tmp_path

    def test_cmd_check__committed_statusline_capture__validates_against_statusline_schema(self, tmp_path):
        # Mandatory once a capture exists (no --schemas-dir override needed: DEFAULT_SCHEMAS is the
        # real repo tree, which ships exactly one statusline.schema.json, cc-2.1.198).
        good = {
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "/tmp",
            "prompt_id": "p",
            "columns": 80,
            "tasks": [],
        }
        captures = self._write_statusline_capture(tmp_path, good)
        assert main(["check", "--cc-version", "2.1.198", "--captures", str(captures)]) == 0

    def test_cmd_check__committed_statusline_capture__drifted_payload_fails_gate(self, tmp_path):
        bad = {
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "/tmp",
            "prompt_id": "p",
            "columns": 80,
            "tasks": [],
            "brand_new_field": True,
        }
        captures = self._write_statusline_capture(tmp_path, bad)
        assert main(["check", "--cc-version", "2.1.198", "--captures", str(captures)]) == 1

    def test_cmd_check__statusline_capture_no_matching_schema__mandatory_not_skipped(self, tmp_path):
        # The statusline surface is mandatory once captured — an unresolvable schema fails the gate
        # the same way a missing hooks schema would.
        empty_schemas = tmp_path / "empty-schemas"
        empty_schemas.mkdir()
        captures = self._write_statusline_capture(tmp_path / "captures", {"tasks": []})
        with pytest.raises(SystemExit):
            main(
                [
                    "check",
                    "--cc-version",
                    "2.1.198",
                    "--captures",
                    str(captures),
                    "--schemas-dir",
                    str(empty_schemas),
                ]
            )

    def test_cmd_check__statusline_only_version_alongside_unrelated_hooks_menu__exits_zero(self, tmp_path):
        # cc-9.9.8 carries an unrelated hooks_menu.json (as cc-2.1.185 does in the real repo).
        hooks_dir = tmp_path / "cc-9.9.8"
        hooks_dir.mkdir()
        (hooks_dir / "hooks_menu.json").write_text(json.dumps({"cc_version": "9.9.8", "events": []}))

        good = {
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "/tmp",
            "prompt_id": "p",
            "columns": 80,
            "tasks": [],
        }
        sl_dir = tmp_path / "cc-2.1.198" / "statusline"
        sl_dir.mkdir(parents=True)
        (sl_dir / "SubagentStatusLine.jsonl").write_text(json.dumps(good) + "\n")

        assert main(["check", "--cc-version", "2.1.198", "--captures", str(tmp_path)]) == 0

    def test_cmd_check__no_cc_version__checks_every_committed_version(self, tmp_path):
        """All-versions default: with no --cc-version, every schemas/cc-* version is checked."""
        from cc_flyrig.schema.roster import EVENTS

        schemas_dir = tmp_path / "schemas"
        captures = tmp_path / "captures"

        # cc-1.0.0: clean menu, matches roster.
        v1 = schemas_dir / "cc-1.0.0"
        v1.mkdir(parents=True)
        (v1 / "hooks.schema.json").write_text(
            json.dumps(
                {
                    "$id": "schemas/cc-1.0.0/hooks.schema.json",
                    "description": "test",
                    "x-cc-version": "1.0.0",
                    "x-schema-date": "2026-01-01",
                    "$defs": {f"{e}Input": {"type": "object"} for e in EVENTS},
                }
            )
        )
        cdir_a = captures / "cc-1.0.0"
        cdir_a.mkdir(parents=True)
        menu_events_a = [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS]
        (cdir_a / "hooks_menu.json").write_text(json.dumps({"cc_version": "1.0.0", "events": menu_events_a}))

        # cc-2.0.0: menu has a bogus extra event -> blocking finding.
        v2 = schemas_dir / "cc-2.0.0"
        v2.mkdir(parents=True)
        (v2 / "hooks.schema.json").write_text(
            json.dumps(
                {
                    "$id": "schemas/cc-2.0.0/hooks.schema.json",
                    "description": "test",
                    "x-cc-version": "2.0.0",
                    "x-schema-date": "2026-01-01",
                    "$defs": {f"{e}Input": {"type": "object"} for e in EVENTS},
                }
            )
        )
        cdir_b = captures / "cc-2.0.0"
        cdir_b.mkdir(parents=True)
        (cdir_b / "hooks_menu.json").write_text(
            json.dumps(
                {
                    "cc_version": "2.0.0",
                    "events": [{"event": e, "input_fields": [], "output_fields": []} for e in [*EVENTS, "Bogus"]],
                }
            )
        )

        rc = main(["check", "--captures", str(captures), "--schemas-dir", str(schemas_dir)])
        assert rc == 1

    def test_cmd_check__roster_mismatch__blocks_the_gate(self, tmp_path):
        """A hooks.schema.json whose $defs disagree with roster.EVENTS is a blocking finding."""
        from cc_flyrig.schema.keys import input_def_name
        from cc_flyrig.schema.roster import EVENTS

        schemas_dir = tmp_path / "schemas"
        version_dir = schemas_dir / "cc-9.9.9"
        version_dir.mkdir(parents=True)
        defs = {input_def_name(e): {"type": "object"} for e in EVENTS if e != EVENTS[0]}
        defs[input_def_name("TotallyNewEvent")] = {"type": "object"}
        schema = {
            "$id": "schemas/cc-9.9.9/hooks.schema.json",
            "description": "test",
            "x-cc-version": "9.9.9",
            "x-schema-date": "2026-01-01",
            "$defs": defs,
        }
        (version_dir / "hooks.schema.json").write_text(json.dumps(schema))

        captures = tmp_path / "captures"
        cdir = captures / "cc-9.9.9"
        cdir.mkdir(parents=True)
        menu_events = [{"event": e, "input_fields": [], "output_fields": []} for e in EVENTS]
        (cdir / "hooks_menu.json").write_text(json.dumps({"cc_version": "9.9.9", "events": menu_events}))

        rc = main(["check", "--cc-version", "9.9.9", "--captures", str(captures), "--schemas-dir", str(schemas_dir)])
        assert rc == 1


class TestCaptureDiffRemoved:
    def test_capture_diff__no_such_command__exits_two(self):
        """`capture diff` is removed, not deprecated: argparse rejects the subcommand outright."""
        with pytest.raises(SystemExit) as exc_info:
            capture_main(["diff", "--cc-version", "2.1.168"])
        assert exc_info.value.code == 2
