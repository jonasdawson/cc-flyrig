"""Integration test: delta() against the real committed cc-2.1.185 -> cc-2.1.198 schema pair.

This is the documented real history (ADR 0011): ``prompt_id`` was hand-authored into
cc-2.1.198/cc-2.1.200's ``CommonInput``. Reads the committed schemas read-only.
"""

import json
from pathlib import Path

from cc_flyrig.schema.delta import delta

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_DIR = REPO_ROOT / "schemas"


def _load(cc_version: str) -> dict:
    return json.loads((SCHEMAS_DIR / cc_version / "hooks.schema.json").read_text())


def test_prompt_id_added_under_common_input():
    schema_a = _load("cc-2.1.185")
    schema_b = _load("cc-2.1.198")

    report = delta(schema_a, schema_b)

    common_changes = [c for c in report.def_changes if c.def_name == "CommonInput"]
    assert len(common_changes) == 1
    change = common_changes[0]
    assert "prompt_id" in change.properties_added
    assert change.properties_removed == ()
