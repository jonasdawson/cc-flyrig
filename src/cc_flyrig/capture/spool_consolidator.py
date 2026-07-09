"""Consolidate raw spool files into a committed ``captures/`` tree.

The probe writes one envelope file per hook invocation into a spool directory. This step groups those
by event, applies a caller-supplied per-payload processor (``on_process_payload``), dedupes, sorts for
a stable diff, and writes ``captures/cc-<version>/<Event>.jsonl`` (one payload per line) plus a
**capture report** (``input_manifest.json``): provenance + per-event payload counts. The capture pipeline
injects PII scrubbing as that processor (see ``capture.util.payload_scrubber``); by default the
payload is written unchanged.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    cc_version: str
    out_dir: Path
    counts: dict[str, int]
    total: int
    run_ids: tuple[str, ...]


def _identity(payload: object) -> object:
    return payload


def _load_envelopes(spool_dir: Path) -> list[dict]:
    envelopes: list[dict] = []
    for f in sorted(spool_dir.glob("*.json")):
        try:
            envelopes.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue  # skip an unreadable/partial spool file rather than abort the whole run
    return envelopes


def _resolve_cc_version(envelopes: list[dict], cc_version: str | None, spool_dir: Path) -> tuple[str, list[dict]]:
    """Pick the CC version to consolidate and return it with the in-scope envelopes.

    With ``cc_version`` given, filter the spool to it; otherwise the spool must hold exactly one
    version. Raises if nothing is in scope or the version is ambiguous.
    """
    if cc_version is not None:
        envelopes = [e for e in envelopes if e.get("cc_version") == cc_version]
    if not envelopes:
        raise ValueError(f"no envelopes to consolidate in {spool_dir}")
    if cc_version is None:
        versions = {e.get("cc_version", "unknown") for e in envelopes}
        if len(versions) != 1:
            raise ValueError(f"spool mixes CC versions {sorted(versions)}; pass cc_version explicitly")
        cc_version = next(iter(versions))
    return cc_version, envelopes


def _group_by_event(
    envelopes: list[dict],
    on_process_payload: Callable[[object], object],
    events: frozenset[str] | None = None,
) -> tuple[dict[str, set[str]], set[str], list[str]]:
    """Group processed, deduped payload lines by event; collect run ids and timestamps for provenance.

    ``events``, when given, restricts grouping to that event family's roster -- envelopes for any
    other event are skipped. ``None`` groups every event present in ``envelopes`` (today's behavior).
    """
    by_event: dict[str, set[str]] = {}
    run_ids: set[str] = set()
    timestamps: list[str] = []
    for env in envelopes:
        event = env.get("event") or "Unknown"
        if events is not None and event not in events:
            continue
        payload = env.get("payload", {})
        processed = on_process_payload(payload)
        line = json.dumps(processed, ensure_ascii=False, sort_keys=True)
        by_event.setdefault(event, set()).add(line)
        if env.get("run_id"):
            run_ids.add(env["run_id"])
        if env.get("timestamp"):
            timestamps.append(env["timestamp"])
    return by_event, run_ids, timestamps


def _write_event_files(out_dir: Path, by_event: dict[str, set[str]]) -> dict[str, int]:
    """Write one sorted, deduped ``<Event>.jsonl`` per event; return per-event payload counts."""
    counts: dict[str, int] = {}
    for event, lines in by_event.items():
        ordered = sorted(lines)
        (out_dir / f"{event}.jsonl").write_text("\n".join(ordered) + "\n", encoding="utf-8")
        counts[event] = len(ordered)
    return counts


def _build_capture_report(
    cc_version: str,
    counts: dict[str, int],
    run_ids: set[str],
    timestamps: list[str],
    extra: dict | None,
) -> dict:
    """Assemble the capture report (persisted as ``input_manifest.json``): provenance + per-event counts."""
    report = {
        "cc_version": cc_version,
        "events": dict(sorted(counts.items())),
        "total_payloads": sum(counts.values()),
        "run_ids": sorted(run_ids),
        "captured_at": max(timestamps) if timestamps else None,
    }
    if extra:
        report.update(extra)
    return report


def consolidate(
    spool_dir: str | Path,
    captures_root: str | Path,
    cc_version: str | None = None,
    on_process_payload: Callable[[object], object] = _identity,
    extra_capture_report: dict | None = None,
    subdir: str | None = None,
    events: Iterable[str] | None = None,
) -> ConsolidationResult:
    """Merge the spool into ``captures_root/cc-<version>/`` and return a summary.

    ``cc_version`` defaults to the version stamped in the envelopes (which must then agree); pass it
    explicitly to filter a mixed spool (e.g. after a mid-run CC upgrade). ``on_process_payload`` is
    applied to each payload before it is serialized -- the capture pipeline injects PII scrubbing
    here; the default leaves the payload unchanged. ``extra_capture_report`` is merged into the
    capture report (e.g. batch id, scenario ids). ``subdir`` nests the output under
    ``cc-<version>/<subdir>/`` instead of directly under ``cc-<version>/`` — used to keep a second
    event family (e.g. statusline) in its own subtree beside the hooks captures.
    ``events``, when given, restricts consolidation to this event family's roster (e.g. the
    statusline family's ``("StatusLine", "SubagentStatusLine")``); envelopes for events outside the
    roster are skipped. ``None`` (the default) consolidates every event present in the spool --
    this is the back-compat path for the hooks-only pipeline.
    """
    spool_dir = Path(spool_dir)
    captures_root = Path(captures_root)

    envelopes = _load_envelopes(spool_dir)
    cc_version, envelopes = _resolve_cc_version(envelopes, cc_version, spool_dir)
    events_filter = frozenset(events) if events is not None else None
    by_event, run_ids, timestamps = _group_by_event(envelopes, on_process_payload, events_filter)

    out_dir = captures_root / f"cc-{cc_version}"
    if subdir:
        out_dir = out_dir / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = _write_event_files(out_dir, by_event)
    report = _build_capture_report(cc_version, counts, run_ids, timestamps, extra_capture_report)
    (out_dir / "input_manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return ConsolidationResult(
        cc_version=cc_version,
        out_dir=out_dir,
        counts=dict(sorted(counts.items())),
        total=sum(counts.values()),
        run_ids=tuple(sorted(run_ids)),
    )
