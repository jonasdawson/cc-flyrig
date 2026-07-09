"""CI gate: output_manifest.json must have no undocumented 'fail' rows.

A 'fail' row is allowed through only if it carries a 'note' explaining the
observed behavior (e.g. a captured regression in the product under test) --
an unexplained fail still blocks the commit.
"""

import json
from pathlib import Path

import pytest

CAPTURES_ROOT = Path(__file__).parent.parent.parent.parent / "captures"


def _find_output_manifests():
    return sorted(CAPTURES_ROOT.glob("cc-*/output_manifest.json"))


@pytest.mark.skipif(not _find_output_manifests(), reason="no output_manifest.json committed")
def test_output_manifest__committed_results__no_fail_rows():
    for manifest_path in _find_output_manifests():
        data = json.loads(manifest_path.read_text())
        fails = [r for r in data.get("results", []) if r.get("result") == "fail" and not r.get("note")]
        assert not fails, f"{manifest_path.relative_to(CAPTURES_ROOT)}: {len(fails)} undocumented fail row(s): {fails}"
