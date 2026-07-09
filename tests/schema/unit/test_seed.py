"""Unit tests for schema.seed: the pure reseed() core, and the `seed` CLI's family loop."""

import json
from pathlib import Path

from cc_flyrig.schema.__main__ import main
from cc_flyrig.schema.seed import reseed

TODAY = "2026-06-20"


def _make_schema(schemas_dir: Path, version: str, family: str = "hooks", schema_date: str = "2026-01-01") -> None:
    ver_dir = schemas_dir / f"cc-{version}"
    ver_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "$id": f"schemas/cc-{version}/{family}.schema.json",
        "description": f"Canonical IR. CC version {version}.",
        "x-cc-version": version,
        "x-schema-date": schema_date,
        "$defs": {},
    }
    (ver_dir / f"{family}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    lang_dir = ver_dir / "lang"
    if not lang_dir.exists():
        lang_dir.mkdir()
        (lang_dir / "python.json").write_text('{"language": "python"}\n')


class TestReseed:
    def test_reseed__patches_id(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "Canonical IR. CC version 1.0.0.",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        result = reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert result["$id"] == "schemas/cc-1.0.1/hooks.schema.json"

    def test_reseed__patches_description(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "Canonical IR. CC version 1.0.0.",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        result = reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert "1.0.1" in result["description"]
        assert "1.0.0" not in result["description"]

    def test_reseed__patches_x_cc_version(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "d",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        result = reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert result["x-cc-version"] == "1.0.1"

    def test_reseed__patches_schema_date(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "d",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        result = reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert result["x-schema-date"] == TODAY

    def test_reseed__does_not_mutate_input(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "d",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        original = dict(schema)
        reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert schema == original

    def test_reseed__returns_new_dict(self):
        schema = {
            "$id": "schemas/cc-1.0.0/hooks.schema.json",
            "description": "d",
            "x-cc-version": "1.0.0",
            "x-schema-date": "2025-01-01",
        }
        result = reseed(schema, "1.0.0", "1.0.1", TODAY)
        assert result is not schema


class TestCmdSeed:
    def test_cmd_seed__no_existing_schema__warns_and_does_not_create(self, tmp_path, capsys):
        rc = main(["seed", "9.9.9", "--schemas-dir", str(tmp_path)])
        assert rc == 0
        assert not (tmp_path / "cc-9.9.9").exists()
        assert "warning" in capsys.readouterr().err

    def test_cmd_seed__schema_already_exists__skipped_idempotently(self, tmp_path):
        _make_schema(tmp_path, "1.0.0")
        rc = main(["seed", "1.0.0", "--schemas-dir", str(tmp_path)])
        assert rc == 0
        # unchanged: date not touched to today's
        schema = json.loads((tmp_path / "cc-1.0.0" / "hooks.schema.json").read_text())
        assert schema["x-schema-date"] == "2026-01-01"

    def test_cmd_seed__new_version__seeds_hooks_and_statusline(self, tmp_path):
        _make_schema(tmp_path, "1.0.0", family="hooks")
        _make_schema(tmp_path, "1.0.0", family="statusline")

        rc = main(["seed", "1.0.1", "--schemas-dir", str(tmp_path)])

        assert rc == 0
        assert (tmp_path / "cc-1.0.1" / "hooks.schema.json").exists()
        assert (tmp_path / "cc-1.0.1" / "statusline.schema.json").exists()

    def test_cmd_seed__new_version__patches_metadata(self, tmp_path):
        _make_schema(tmp_path, "1.0.0")
        main(["seed", "1.0.1", "--schemas-dir", str(tmp_path)])
        schema = json.loads((tmp_path / "cc-1.0.1" / "hooks.schema.json").read_text())
        assert schema["x-cc-version"] == "1.0.1"
        assert schema["$id"] == "schemas/cc-1.0.1/hooks.schema.json"

    def test_cmd_seed__new_version__copies_lang_verbatim(self, tmp_path):
        _make_schema(tmp_path, "1.0.0")
        main(["seed", "1.0.1", "--schemas-dir", str(tmp_path)])
        lang_file = tmp_path / "cc-1.0.1" / "lang" / "python.json"
        assert lang_file.exists()
        assert lang_file.read_text() == '{"language": "python"}\n'

    def test_cmd_seed__multiple_existing_versions__copies_from_latest(self, tmp_path):
        _make_schema(tmp_path, "1.0.0")
        _make_schema(tmp_path, "1.0.5")
        _make_schema(tmp_path, "1.0.2")
        main(["seed", "2.0.0", "--schemas-dir", str(tmp_path)])
        schema = json.loads((tmp_path / "cc-2.0.0" / "hooks.schema.json").read_text())
        assert "1.0.5" not in schema["$id"]  # patched away
        assert (tmp_path / "cc-2.0.0" / "hooks.schema.json").exists()

    def test_cmd_seed__per_file_idempotent__hooks_missing_statusline_present__only_seeds_hooks(self, tmp_path):
        # A sibling surface (statusline) may already own the target dir; hooks still gets seeded.
        _make_schema(tmp_path, "1.0.0", family="hooks")
        target = tmp_path / "cc-1.0.1"
        target.mkdir()
        existing = {"$id": "x", "description": "d", "x-cc-version": "1.0.1", "x-schema-date": "d"}
        (target / "statusline.schema.json").write_text(json.dumps(existing))

        rc = main(["seed", "1.0.1", "--schemas-dir", str(tmp_path)])

        assert rc == 0
        assert (target / "hooks.schema.json").exists()

    def test_cmd_seed__no_source_for_one_family__warns_but_seeds_the_other(self, tmp_path, capsys):
        _make_schema(tmp_path, "1.0.0", family="hooks")
        # No statusline source anywhere.
        rc = main(["seed", "1.0.1", "--schemas-dir", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "cc-1.0.1" / "hooks.schema.json").exists()
        assert not (tmp_path / "cc-1.0.1" / "statusline.schema.json").exists()
        assert "warning" in capsys.readouterr().err
