"""Detect drift between committed captures and the canonical IR — the per-PR CI drift gate.

Two independent checks per captured payload:

1. **Schema validation** against the matching ``<Event>Input`` definition (Draft 2020-12). Catches
   type/required-field regressions.
2. **Unknown-key drift.** The IR sets no ``additionalProperties: false``, so validation passes on
   *new* fields. To catch additive CC drift we compare the payload's top-level keys against the known
   property set computed by :mod:`walker`. A new top-level key is reported as drift.

This module reads only committed artifacts (the IR + the ``captures/`` tree); it needs no model auth,
so it runs in ordinary CI.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .keys import input_def_name, output_def_name
from .roster import EVENTS
from .walker import walk_props


@dataclass(frozen=True, slots=True)
class Finding:
    file: Path
    event: str
    index: int  # line number within the .jsonl (0-based)
    # "validation" | "drift" | "unknown-event" | "parse" | "roster" | "cc-hooks-skill-drift" |
    # "cc-hooks-skill-advisory"
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.index} [{self.event}/{self.kind}] {self.detail}"


def find_capture_dirs(captures_root: str | Path, *, cc_version: str | None = None) -> list[Path]:
    """Return the per-CC-version capture directories under ``captures_root`` (``cc-*``).

    ``cc_version`` narrows this to the single ``cc-<version>`` dir (or ``[]`` if it doesn't exist)
    instead of every committed version — pass it whenever a caller has one particular version in
    hand (e.g. the CLI's ``--cc-version``) so a diff run never reads another version's artifacts.
    The default (``None``) preserves the historical "every version" behavior.
    """
    root = Path(captures_root)
    if not root.exists():
        return []
    if cc_version:
        target = root / f"cc-{cc_version}"
        return [target] if target.is_dir() else []
    return sorted(p for p in root.glob("cc-*") if p.is_dir())


def count_payloads(captures_root: str | Path, *, subdir: str | None = None, cc_version: str | None = None) -> int:
    """Total committed payload lines across every version dir (drives the CI skip decision).

    ``subdir`` counts a nested surface tree (e.g. ``cc-<version>/statusline/``) instead of the
    files directly under ``cc-<version>/``; the default preserves the hooks-path behavior exactly.
    ``cc_version`` scopes the count to that one version dir (see :func:`find_capture_dirs`).
    """
    total = 0
    for cdir in find_capture_dirs(captures_root, cc_version=cc_version):
        base = cdir / subdir if subdir else cdir
        if not base.exists():
            continue
        for f in base.glob("*.jsonl"):
            total += sum(1 for line in f.read_text().splitlines() if line.strip())
    return total


def _event_validator(schema: dict, event: str) -> Draft202012Validator:
    sub = dict(schema)
    sub.update({"$ref": f"#/$defs/{input_def_name(event)}"})
    return Draft202012Validator(sub)


def check_payload(schema: dict, event: str, payload: dict, *, file: Path, index: int) -> list[Finding]:
    """Validate one payload and check it for unknown-key drift."""
    def_name = input_def_name(event)
    if def_name not in schema.get("$defs", {}):
        return [Finding(file, event, index, "unknown-event", f"no $defs/{def_name} for captured event")]

    findings: list[Finding] = []
    for err in _event_validator(schema, event).iter_errors(payload):
        location = "/".join(str(p) for p in err.absolute_path) or "<root>"
        findings.append(Finding(file, event, index, "validation", f"at {location}: {err.message}"))

    extra = set(payload) - walk_props(schema, def_name)
    if extra:
        findings.append(Finding(file, event, index, "drift", f"unknown top-level key(s): {sorted(extra)}"))
    return findings


def _check_dir(schema: dict, dir_path: Path) -> list[Finding]:
    """Validate + drift-check every ``<artifact>.jsonl`` directly under ``dir_path`` against ``schema``.

    The shared inner loop for :func:`check_captures` — factored out so a second surface (e.g.
    statusline, keyed by its own ``{artifact -> schema}`` registry entry) can reuse it against a
    nested directory without duplicating the parse/validate/drift logic.
    """
    findings: list[Finding] = []
    for f in sorted(dir_path.glob("*.jsonl")):
        event = f.stem
        for index, line in enumerate(f.read_text().splitlines()):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                findings.append(Finding(f, event, index, "parse", str(exc)))
                continue
            findings.extend(check_payload(schema, event, payload, file=f, index=index))
    return findings


def check_captures(
    schema: dict, captures_root: str | Path, *, subdir: str | None = None, cc_version: str | None = None
) -> list[Finding]:
    """Run validation + drift over every committed payload and return all findings.

    ``subdir`` validates a nested surface tree (e.g. ``cc-<version>/statusline/``, widening this to
    an ``{artifact -> schema}`` registry one caller at a time) instead of the files directly under
    ``cc-<version>/``; the default preserves the hooks-path behavior exactly. ``cc_version`` scopes
    the scan to that one version dir (see :func:`find_capture_dirs`).
    """
    findings: list[Finding] = []
    for cdir in find_capture_dirs(captures_root, cc_version=cc_version):
        base = cdir / subdir if subdir else cdir
        if not base.exists():
            continue
        findings.extend(_check_dir(schema, base))
    return findings


def check_documented_events(menu_events: Iterable[str], *, source: Path) -> list[Finding]:
    """Compare the ``/hooks`` menu's event set against the IR roster (``roster.EVENTS``).

    Returns blocking ``cc-hooks-skill-drift`` findings for events documented by the binary but absent
    from the IR, and vice versa. Pure over the event-name list, so it serves both the capture-time
    warn/prompt (``_cmd_run``) and the CI gate (``_cmd_diff``). It draws no conclusion about *why* the
    sets differ (no rename/removal inference).
    """
    menu = set(menu_events)
    ir = set(EVENTS)
    findings = [
        Finding(source, e, 0, "cc-hooks-skill-drift", "documented by /hooks, absent from IR") for e in sorted(menu - ir)
    ]
    findings += [
        Finding(source, e, 0, "cc-hooks-skill-drift", "in IR, not documented by /hooks") for e in sorted(ir - menu)
    ]
    return findings


def _props_or_empty(schema: dict, def_name: str) -> set[str]:
    """Top-level props for ``def_name``, or an empty set when the def is absent (e.g. a new event)."""
    if def_name not in schema.get("$defs", {}):
        return set()
    return walk_props(schema, def_name)


def check_documented_fields(schema: dict, events: list[dict], *, source: Path) -> list[Finding]:
    """Cross-check the field names the ``/hooks`` menu documents against the IR (advisory only).

    For each entry, report a menu-named field that is **absent** from the IR's ``<Event>Input`` /
    ``<Event>Output`` props — additive drift the binary documents but the IR lacks. Directional by
    design (feature D6): the reverse is *not* reported, since the IR legitimately carries far more
    (the whole ``CommonInput`` envelope, plus everything the menu states only as prose). Emits
    non-blocking ``cc-hooks-skill-advisory`` findings.
    """
    findings: list[Finding] = []
    for entry in events:
        event = entry.get("event", "")
        ir_in = _props_or_empty(schema, input_def_name(event))
        for field in entry.get("input_fields", []):
            if field not in ir_in:
                findings.append(
                    Finding(
                        source,
                        event,
                        0,
                        "cc-hooks-skill-advisory",
                        f"input field {field!r} documented by /hooks, absent from IR",
                    )
                )
        ir_out = _props_or_empty(schema, output_def_name(event))
        for field in entry.get("output_fields", []):
            if field not in ir_out:
                findings.append(
                    Finding(
                        source,
                        event,
                        0,
                        "cc-hooks-skill-advisory",
                        f"output field {field!r} documented by /hooks, absent from IR",
                    )
                )
    return findings


def check_documented_hooks(schema: dict, captures_root: str | Path, *, cc_version: str | None = None) -> list[Finding]:
    """Run the menu-vs-IR checks over every committed ``cc-*/hooks_menu.json``.

    Combines the blocking event-set check (``cc-hooks-skill-drift``) with the advisory field
    cross-check (``cc-hooks-skill-advisory``). Returns no findings when no menu artifact is committed.
    ``cc_version`` scopes the scan to that one version dir (see :func:`find_capture_dirs`) — a diff
    run for one version must not read another version's menu artifact.
    """
    findings: list[Finding] = []
    for cdir in find_capture_dirs(captures_root, cc_version=cc_version):
        path = cdir / "hooks_menu.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        events = data.get("events", [])
        findings += check_documented_events([e["event"] for e in events], source=path)
        findings += check_documented_fields(schema, events, source=path)
    return findings


def roster_agreement(events: tuple[str, ...], defs: Iterable[str]) -> list[Finding]:
    """Compare the IR roster (``roster.EVENTS``) against a schema's own ``<Event>Input`` def set.

    Pure: takes the schema's ``$defs`` keys (not the schema itself), so it needs no file access.
    Any def without a matching roster entry, or any roster entry without a matching def, is one
    blocking ``Finding(kind="roster")`` — closing the gap the menu-vs-roster check never covered
    (roster vs. the schema itself).
    """
    def_events = {d.removesuffix("Input") for d in defs if d.endswith("Input") and d != "CommonInput"}
    roster = set(events)
    findings = [
        Finding(Path("<roster>"), e, 0, "roster", f"$defs/{e}Input present, absent from roster.EVENTS")
        for e in sorted(def_events - roster)
    ]
    findings += [
        Finding(Path("<roster>"), e, 0, "roster", f"in roster.EVENTS, no $defs/{e}Input")
        for e in sorted(roster - def_events)
    ]
    return findings


def has_documented_hooks(captures_root: str | Path, *, cc_version: str | None = None) -> bool:
    """True when at least one committed ``cc-*/hooks_menu.json`` exists (drives the diff skip).

    ``cc_version`` scopes the check to that one version dir (see :func:`find_capture_dirs`).
    """
    return any((cdir / "hooks_menu.json").exists() for cdir in find_capture_dirs(captures_root, cc_version=cc_version))
