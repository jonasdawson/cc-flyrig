"""Integration tests for schema.reconcile against real committed captures/schemas.

Uses tmp_path for anything that copies committed files so the real ``schemas/``/``captures/`` trees
are never written to during a test run.
"""

import copy
import json
from pathlib import Path

from cc_flyrig.schema.reconcile import observe, propose

ROOT = Path(__file__).parent.parent.parent.parent
CAPTURES_ROOT = ROOT / "captures"
SCHEMAS_ROOT = ROOT / "schemas"

CC_VERSION = "2.1.198"


def _load_samples(dir_path: Path) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = {}
    for f in sorted(dir_path.glob("*.jsonl")):
        event = f.stem
        samples[event] = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return samples


class TestPromptIdReplay:
    def test_stripping_prompt_id_from_common_input__reconcile_re_proposes_it(self):
        schema_path = SCHEMAS_ROOT / f"cc-{CC_VERSION}" / "hooks.schema.json"
        schema = json.loads(schema_path.read_text())

        stripped = copy.deepcopy(schema)
        common = stripped["$defs"]["CommonInput"]
        common["properties"].pop("prompt_id", None)
        if "required" in common:
            common["required"] = [k for k in common["required"] if k != "prompt_id"]

        # Sanity: the committed captures actually carry prompt_id somewhere (read-only).
        capture_dir = CAPTURES_ROOT / f"cc-{CC_VERSION}"
        samples = _load_samples(capture_dir)
        events_with_prompt_id = {event for event, rows in samples.items() if any("prompt_id" in row for row in rows)}
        assert events_with_prompt_id, "expected at least one committed cc-2.1.198 event to carry prompt_id"

        proposal = propose(stripped, observe(samples))

        proposed_keys_by_event = {a.event: a.key for a in proposal.additions}
        assert any(
            event in events_with_prompt_id and key == "prompt_id" for event, key in proposed_keys_by_event.items()
        ), f"expected prompt_id to be re-proposed for one of {events_with_prompt_id}, got: {proposal.additions}"


class TestCommittedTreeNoOp:
    def test_reconcile_over_untouched_committed_tree__proposes_nothing(self):
        schema_path = SCHEMAS_ROOT / f"cc-{CC_VERSION}" / "hooks.schema.json"
        schema = json.loads(schema_path.read_text())
        capture_dir = CAPTURES_ROOT / f"cc-{CC_VERSION}"
        samples = _load_samples(capture_dir)

        proposal = propose(schema, observe(samples))

        assert proposal.additions == (), f"committed cc-{CC_VERSION} schema is not caught up: {proposal.additions}"
