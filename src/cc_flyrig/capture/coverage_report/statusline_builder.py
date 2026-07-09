"""Build the coverage report model for the statusline event family from a committed ``captures/`` tree.

The statusline event family (``StatusLine`` / ``SubagentStatusLine``) is separate from the
hooks family: it has no tool identity, and its expectations are derived differently. ``StatusLine`` is
expected on every battery run — it fires per scenario regardless of what any individual scenario
targets. ``SubagentStatusLine`` is only expected when the manifest actually drove a subagent scenario;
that is inferred from ``scenario.expect.events`` containing a subagent-lifecycle event, since the
manifest has no dedicated field for it. ``rendering`` turns this model into ``STATUSLINE_COVERAGE.md``.
"""

from dataclasses import dataclass
from pathlib import Path

from ..event_families import STATUSLINE_FAMILY
from ..scenario_manifest import Manifest
from .input_builder import MISSING, NOT_ATTEMPTED, OBSERVED, _captured_at, _observed_counts

# Subagent-lifecycle events used as a proxy signal for "this manifest drove a subagent scenario".
_SUBAGENT_LIFECYCLE_EVENTS = frozenset(
    {"SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "TeammateIdle"}
)


@dataclass(frozen=True, slots=True)
class StatuslineEventCoverage:
    event: str
    status: str
    count: int


@dataclass(frozen=True, slots=True)
class StatuslineCoverageReport:
    cc_version: str
    captured_at: str | None
    rows: tuple[StatuslineEventCoverage, ...]
    observed: int
    missing: int
    not_attempted: int
    total_events: int


def _has_subagent_scenario(manifest: Manifest) -> bool:
    """Whether any scenario in ``manifest`` targets a subagent-lifecycle event."""
    return any(
        event in _SUBAGENT_LIFECYCLE_EVENTS for scenario in manifest.scenarios for event in scenario.expect.events
    )


def _classify(manifest: Manifest, counts: dict[str, int]) -> list[StatuslineEventCoverage]:
    """Classify each statusline event-family event against what was captured."""
    subagent_scenario_ran = _has_subagent_scenario(manifest)
    rows: list[StatuslineEventCoverage] = []
    for event in STATUSLINE_FAMILY.events:
        count = counts.get(event, 0)
        if count > 0:
            status = OBSERVED
        elif event == "StatusLine":
            # StatusLine always fires per the battery design (D2) — never "not attempted".
            status = MISSING
        elif subagent_scenario_ran:
            status = MISSING
        else:
            status = NOT_ATTEMPTED
        rows.append(StatuslineEventCoverage(event, status, count))
    return rows


def build_statusline_report(manifest: Manifest, captures_dir: str | Path, cc_version: str) -> StatuslineCoverageReport:
    """Read ``captures_dir`` (the ``statusline/`` subtree) and assemble the coverage report model."""
    captures_dir = Path(captures_dir)
    rows = _classify(manifest, _observed_counts(captures_dir))
    tally = {OBSERVED: 0, MISSING: 0, NOT_ATTEMPTED: 0}
    for row in rows:
        tally[row.status] += 1
    return StatuslineCoverageReport(
        cc_version=cc_version,
        captured_at=_captured_at(captures_dir),
        rows=tuple(rows),
        observed=tally[OBSERVED],
        missing=tally[MISSING],
        not_attempted=tally[NOT_ATTEMPTED],
        total_events=len(STATUSLINE_FAMILY.events),
    )
