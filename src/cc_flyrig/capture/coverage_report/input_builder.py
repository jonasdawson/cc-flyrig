"""Build the coverage report model from a committed ``captures/`` tree.

Capture is incomplete by construction: headless/interactive limits mean some events can never be
driven by the battery. The model classifies every IR event as observed, expected-but-missing (a
scenario targets it but no payload was captured — investigate), or simply not attempted by any
scenario — so an empty cell never reads as a silent gap. A known anomaly such as WorktreeRemove (a CC
bug) shows as expected-but-missing every run until it is fixed. ``rendering`` turns the model into
Markdown.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ...schema.roster import EVENTS, TOOL_EVENTS
from ..scenario_manifest import Manifest

# Classification of an event for the report.
OBSERVED = "observed"
MISSING = "expected-but-missing"
NOT_ATTEMPTED = "not-attempted"


@dataclass(frozen=True, slots=True)
class EventCoverage:
    event: str
    status: str
    count: int
    capture_methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    cc_version: str
    captured_at: str | None
    rows: tuple[EventCoverage, ...]
    tools: tuple[tuple[str, tuple[str, ...]], ...]  # (event, sorted tool names) per tool-bearing event
    observed: int
    missing: int
    not_attempted: int
    total_events: int


def _observed_counts(captures_dir: Path) -> dict[str, int]:
    """Map event name -> number of captured payload lines in ``captures_dir``."""
    counts: dict[str, int] = {}
    for f in captures_dir.glob("*.jsonl"):
        counts[f.stem] = sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    return counts


def _observed_tools(captures_dir: Path) -> dict[str, set[str]]:
    """Map each tool-bearing event to the set of tool names seen in its captured payloads."""
    out: dict[str, set[str]] = {}
    for event in TOOL_EVENTS:
        f = captures_dir / f"{event}.jsonl"
        if not f.exists():
            continue
        seen: set[str] = set()
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = payload.get("tool_name")
            if isinstance(name, str):
                seen.add(name)
            for call in payload.get("tool_calls", []) or []:  # PostToolBatch
                if isinstance(call, dict) and isinstance(call.get("tool_name"), str):
                    seen.add(call["tool_name"])
        out[event] = seen
    return out


def _classify(manifest: Manifest, counts: dict[str, int]) -> list[EventCoverage]:
    """Classify every IR event against what the battery expects and what was captured."""
    expected: set[str] = set()
    methods: dict[str, set[str]] = {}
    for scenario in manifest.scenarios:
        for event in scenario.expect.events:
            expected.add(event)
            methods.setdefault(event, set()).add(scenario.expect.method)

    rows: list[EventCoverage] = []
    for event in EVENTS:
        count = counts.get(event, 0)
        if count > 0:
            status = OBSERVED
        elif event in expected:
            status = MISSING
        else:
            status = NOT_ATTEMPTED
        rows.append(EventCoverage(event, status, count, tuple(sorted(methods.get(event, ())))))
    return rows


def _captured_at(captures_dir: Path) -> str | None:
    capture_report_file = captures_dir / "input_manifest.json"
    if not capture_report_file.exists():
        return None
    try:
        return json.loads(capture_report_file.read_text(encoding="utf-8")).get("captured_at")
    except (OSError, json.JSONDecodeError):
        return None


def build_input_report(manifest: Manifest, captures_dir: str | Path, cc_version: str) -> CoverageReport:
    """Read ``captures_dir`` and assemble the coverage report model."""
    captures_dir = Path(captures_dir)
    rows = _classify(manifest, _observed_counts(captures_dir))
    seen = _observed_tools(captures_dir)
    tools = tuple((event, tuple(sorted(seen.get(event, ())))) for event in sorted(TOOL_EVENTS))
    tally = {OBSERVED: 0, MISSING: 0, NOT_ATTEMPTED: 0}
    for row in rows:
        tally[row.status] += 1
    return CoverageReport(
        cc_version=cc_version,
        captured_at=_captured_at(captures_dir),
        rows=tuple(rows),
        tools=tools,
        observed=tally[OBSERVED],
        missing=tally[MISSING],
        not_attempted=tally[NOT_ATTEMPTED],
        total_events=len(EVENTS),
    )
