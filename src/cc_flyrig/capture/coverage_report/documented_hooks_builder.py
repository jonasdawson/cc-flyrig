"""Build the documented-hooks report model from a committed ``hooks_menu.json``.

Reads the menu artifact as plain JSON (the artifact is the interface — never imports the scanner) and
combines it with the IR schema to produce ``HOOKS_MENU.md``: the roster-status line vs the IR, the
per-entry docs scraped from ``/hooks``, and the advisory field cross-check. See the hooks-menu-source
evolution; MENU is roster-authoritative, cross-check-advisory, doc-informal.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ...schema import drift_detector
from ...schema.roster import EVENTS


@dataclass(frozen=True, slots=True)
class DocumentedHooksReport:
    cc_version: str
    total: int  # events documented by /hooks
    ir_total: int  # events in the IR roster
    menu_only: list[str]  # documented by /hooks, absent from the IR roster
    ir_only: list[str]  # in the IR roster, not documented by /hooks
    entries: list[dict]  # the parsed menu entries, in menu order
    advisory: list[dict]  # [{event, detail}] from the field cross-check

    @property
    def matches_ir(self) -> bool:
        return not self.menu_only and not self.ir_only


def build_documented_hooks_report(menu_json_path: str | Path, schema: dict) -> DocumentedHooksReport:
    """Load ``hooks_menu.json`` and assemble the report model against the IR ``schema``."""
    path = Path(menu_json_path)
    data = json.loads(path.read_text())
    entries = data.get("events", [])
    names = {e["event"] for e in entries}
    ir = set(EVENTS)
    advisory = [
        {"event": f.event, "detail": f.detail}
        for f in drift_detector.check_documented_fields(schema, entries, source=path)
    ]
    return DocumentedHooksReport(
        cc_version=data.get("cc_version", ""),
        total=len(entries),
        ir_total=len(EVENTS),
        menu_only=sorted(names - ir),
        ir_only=sorted(ir - names),
        entries=entries,
        advisory=advisory,
    )
