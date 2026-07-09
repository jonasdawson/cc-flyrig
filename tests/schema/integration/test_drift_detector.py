"""Integration tests for the schema drift detector (schema.drift_detector).

The CI gate: each version's committed captures must validate against *that version's* committed IR
schema. Skips cleanly when no captures have been committed yet (maintainer step per ADR 0007).
See tests/schema/unit/test_drift_detector.py for synthetic validation logic tests.
"""

import json
from pathlib import Path

import pytest

from cc_flyrig.schema import drift_detector

ROOT = Path(__file__).parent.parent.parent.parent
CAPTURES_ROOT = ROOT / "captures"
SCHEMAS_ROOT = ROOT / "schemas"

# Each captured version validates against its own schema, not one hard-coded baseline: fields are
# added across CC versions (e.g. prompt_id landed between cc-2.1.185 and cc-2.1.198), so a single
# shared schema would false-positive on newer captures.
_HOOKS_VERSIONS = sorted(p.parent.name for p in SCHEMAS_ROOT.glob("cc-*/hooks.schema.json"))
_STATUSLINE_VERSIONS = sorted(p.parent.name for p in SCHEMAS_ROOT.glob("cc-*/statusline.schema.json"))


def _load_schema(version_dir_name: str, filename: str) -> dict:
    return json.loads((SCHEMAS_ROOT / version_dir_name / filename).read_text())


class TestCommittedCaptureGate:
    """The actual CI gate: committed captures must validate against the committed IR."""

    @pytest.mark.parametrize("version_dir", _HOOKS_VERSIONS)
    def test_committed_captures__validate_against_ir__no_findings(self, version_dir):
        cc_version = version_dir[len("cc-") :]
        if drift_detector.count_payloads(CAPTURES_ROOT, cc_version=cc_version) == 0:
            pytest.skip(f"no committed hooks captures for {version_dir} — capture is a maintainer step (ADR 0007)")
        schema = _load_schema(version_dir, "hooks.schema.json")
        findings = drift_detector.check_captures(schema, CAPTURES_ROOT, cc_version=cc_version)
        assert findings == [], f"{version_dir} captured payloads drifted from the IR:\n" + "\n".join(
            str(f) for f in findings
        )


class TestCommittedStatuslineCaptureGate:
    """The statusline counterpart of TestCommittedCaptureGate (Group 2, U5): committed
    captures/cc-<version>/statusline/*.jsonl must validate against that version's statusline.schema.json."""

    @pytest.mark.parametrize("version_dir", _STATUSLINE_VERSIONS)
    def test_committed_statusline_captures__validate_against_ir__no_findings(self, version_dir):
        cc_version = version_dir[len("cc-") :]
        if drift_detector.count_payloads(CAPTURES_ROOT, subdir="statusline", cc_version=cc_version) == 0:
            pytest.skip(f"no committed statusline captures for {version_dir} — capture is a maintainer step")
        schema = _load_schema(version_dir, "statusline.schema.json")
        findings = drift_detector.check_captures(schema, CAPTURES_ROOT, subdir="statusline", cc_version=cc_version)
        assert findings == [], f"{version_dir} statusline payloads drifted from the IR:\n" + "\n".join(
            str(f) for f in findings
        )

    @pytest.mark.parametrize("version_dir", _HOOKS_VERSIONS)
    def test_committed_hooks_captures__unaffected_by_statusline_subdir__still_validate(self, version_dir):
        # Regression guard for the subdir widening: the default (hooks) scan must ignore the
        # cc-<version>/statusline/ subtree entirely, since glob("*.jsonl") is non-recursive.
        cc_version = version_dir[len("cc-") :]
        if drift_detector.count_payloads(CAPTURES_ROOT, cc_version=cc_version) == 0:
            pytest.skip(f"no committed hooks captures for {version_dir} — capture is a maintainer step (ADR 0007)")
        schema = _load_schema(version_dir, "hooks.schema.json")
        findings = drift_detector.check_captures(schema, CAPTURES_ROOT, cc_version=cc_version)
        assert findings == []
