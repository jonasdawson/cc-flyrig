"""CLI for the contract lifecycle: ``python -m cc_flyrig.schema <command>``.

Commands
--------
check      Validate committed captures against the committed schema, per family, per version (the
           CI gate, formerly ``capture diff``); exits non-zero on drift.
seed       Forward-copy the latest schema of each family into a new version's schema dir.
reconcile  Merge observed capture fields into the committed schema as additive proposals. (Group 3.)
diff       Cross-version delta between two named committed schema versions. (Group 3.)

This is the composition root: all I/O (argparse, globbing, file reads/writes, printing, exit
codes) lives here. Pure contract logic lives in ``locate.py``, ``seed.py``, ``drift_detector.py``,
``walker.py``, ``roster.py``.
"""

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from . import delta, drift_detector, locate
from .keys import input_def_name
from .reconcile import observe, propose
from .roster import EVENTS
from .seed import reseed

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURES = REPO_ROOT / "captures"
DEFAULT_SCHEMAS = REPO_ROOT / "schemas"

FAMILIES = ("hooks", "statusline")


def _schema_versions(schemas_dir: Path) -> list[str]:
    return sorted(p.name[3:] for p in schemas_dir.glob("cc-*") if p.is_dir())


def _check_one_version(cc_version: str | None, *, captures: Path, schemas_dir: Path) -> tuple[list, bool]:
    """Run the full check for a single version (or, when ``cc_version`` is None, whatever the
    hooks/statusline resolvers can uniquely find). Returns ``(findings, had_any_captures)``."""
    has_payloads = drift_detector.count_payloads(captures, cc_version=cc_version) > 0
    has_menu = drift_detector.has_documented_hooks(captures, cc_version=cc_version)
    has_statusline_payloads = drift_detector.count_payloads(captures, subdir="statusline", cc_version=cc_version) > 0

    if not has_payloads and not has_menu and not has_statusline_payloads:
        return [], False

    findings: list = []
    if has_payloads or has_menu:
        schema = json.loads(locate.find("hooks", cc_version, schemas_dir).read_text())
        findings += drift_detector.check_captures(schema, captures, cc_version=cc_version) if has_payloads else []
        findings += drift_detector.check_documented_hooks(schema, captures, cc_version=cc_version)
        findings += drift_detector.roster_agreement(EVENTS, schema.get("$defs", {}))
    if has_statusline_payloads:
        statusline_schema = json.loads(locate.find("statusline", cc_version, schemas_dir).read_text())
        findings += drift_detector.check_captures(
            statusline_schema, captures, subdir="statusline", cc_version=cc_version
        )
    return findings, True


def _cmd_check(args) -> int:
    captures = Path(args.captures)
    schemas_dir = Path(args.schemas_dir)

    if args.cc_version:
        versions = [args.cc_version]
    else:
        versions = _schema_versions(schemas_dir)

    if not versions:
        # No schema versions to check against at all: nothing committed yet.
        print("no committed captures to check (live capture is a maintainer step)")
        return 0

    all_findings: list = []
    any_captures = False
    for v in versions:
        findings, had_captures = _check_one_version(v, captures=captures, schemas_dir=schemas_dir)
        any_captures = any_captures or had_captures
        all_findings += findings

    if not any_captures:
        print("no committed captures to check (live capture is a maintainer step)")
        return 0

    advisory = [f for f in all_findings if f.kind == "cc-hooks-skill-advisory"]
    blocking = [f for f in all_findings if f.kind != "cc-hooks-skill-advisory"]

    for f in advisory:  # reported, never fails the gate (feature D6)
        print(f"  advisory: {f}")
    if blocking:
        print(f"DRIFT: {len(blocking)} finding(s):", file=sys.stderr)
        for f in blocking:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("captures validate against the IR")
    return 0


def _seed_family(family: str, new_version: str, schemas_dir: Path, today: str) -> None:
    filename = f"{family}.schema.json"
    target = schemas_dir / f"cc-{new_version}"
    if (target / filename).exists():
        # Per-file idempotency: a sibling family may already own the target dir.
        return
    existing = [p for p in schemas_dir.glob("cc-*") if p.is_dir() and (p / filename).exists()]
    if not existing:
        print(f"warning: no existing {filename} to seed from; add {target}/{filename} manually", file=sys.stderr)
        return
    source = max(existing, key=lambda p: tuple(int(x) for x in p.name[3:].split(".")))
    source_version = source.name[3:]
    target.mkdir(parents=True, exist_ok=True)
    schema = json.loads((source / filename).read_text())
    patched = reseed(schema, source_version, new_version, today)
    target.mkdir(parents=True, exist_ok=True)
    (target / filename).write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    if (source / "lang").is_dir() and not (target / "lang").is_dir():
        shutil.copytree(source / "lang", target / "lang")
    print(f"seeded schemas/cc-{new_version}/{filename} from cc-{source_version} — run check before generating")


def _cmd_seed(args) -> int:
    schemas_dir = Path(args.schemas_dir)
    today = date.today().isoformat()
    for family in FAMILIES:
        _seed_family(family, args.version, schemas_dir, today)
    return 0


def _load_capture_samples(dir_path: Path) -> dict[str, list[dict]]:
    """Parse every ``*.jsonl`` file directly under ``dir_path`` into ``{event: [payload, ...]}``.

    Mirrors ``drift_detector._check_dir``'s parse loop (event name = file stem, blank lines
    skipped) but returns parsed payloads instead of findings.
    """
    samples: dict[str, list[dict]] = {}
    if not dir_path.exists():
        return samples
    for f in sorted(dir_path.glob("*.jsonl")):
        event = f.stem
        rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        samples[event] = rows
    return samples


def _format_type(type_value) -> str:
    if isinstance(type_value, str):
        return type_value
    return " | ".join(type_value)


def _reconcile_family(cc_version: str, family: str, capture_dir: Path, schemas_dir: Path, *, dry_run: bool) -> None:
    samples = _load_capture_samples(capture_dir)
    if not samples:
        return

    try:
        schema_path = locate.find(family, cc_version, schemas_dir)
    except SystemExit:
        print(f"cc-{cc_version} [{family}]: no schema to reconcile against, skipping", file=sys.stderr)
        return

    schema = json.loads(schema_path.read_text())
    proposal = propose(schema, observe(samples))

    if not proposal.additions and not proposal.notes and not proposal.warnings:
        return

    print(f"cc-{cc_version} [{family}]")
    for addition in proposal.additions:
        suffix = f"{addition.seen}/{addition.total} samples"
        if addition.required:
            suffix += " → required"
        print(f"  + {input_def_name(addition.event)}.{addition.key}: {_format_type(addition.type)} ({suffix})")
    for note in proposal.notes:
        print(f"  note: {note}")
    for warning in proposal.warnings:
        print(f"  warning: {warning}")

    if dry_run or not proposal.additions:
        return
    schema_path.write_text(json.dumps(proposal.schema, indent=2) + "\n", encoding="utf-8")


def _cmd_reconcile(args) -> int:
    captures = Path(args.captures)
    schemas_dir = Path(args.schemas_dir)

    if args.cc_version:
        versions = [args.cc_version]
    else:
        versions = sorted(p.name[3:] for p in captures.glob("cc-*") if p.is_dir())

    for v in versions:
        _reconcile_family(v, "hooks", captures / f"cc-{v}", schemas_dir, dry_run=args.dry_run)
        _reconcile_family(v, "statusline", captures / f"cc-{v}" / "statusline", schemas_dir, dry_run=args.dry_run)

    return 0


def _render_def_change(change) -> str:
    parts = []
    if change.properties_added:
        parts.append("+" + ",+".join(change.properties_added))
    if change.properties_removed:
        parts.append("-" + ",-".join(change.properties_removed))
    for tc in change.type_changes:
        parts.append(f"{tc.property}: {tc.old_type} -> {tc.new_type}")
    if change.required_added:
        parts.append("required: +" + ",+".join(change.required_added))
    if change.required_removed:
        parts.append("required: -" + ",-".join(change.required_removed))
    return f"  ~ {change.def_name}: {', '.join(parts)}"


def _diff_family(family: str, from_dir: Path, to_dir: Path, from_version: str, to_version: str) -> None:
    filename = f"{family}.schema.json"
    from_path = from_dir / filename
    to_path = to_dir / filename
    if not from_path.exists() or not to_path.exists():
        print(f"family {family} absent from {from_version} or {to_version}, skipping")
        return

    schema_a = json.loads(from_path.read_text())
    schema_b = json.loads(to_path.read_text())
    report = delta.delta(schema_a, schema_b)

    print(f"[{family}] {from_version} -> {to_version}")
    if not report.defs_added and not report.defs_removed and not report.def_changes:
        print("  no differences")
        return
    if report.defs_added:
        print("  defs added: " + ", ".join(report.defs_added))
    if report.defs_removed:
        print("  defs removed: " + ", ".join(report.defs_removed))
    for change in report.def_changes:
        print(_render_def_change(change))


def _cmd_diff(args) -> int:
    schemas_dir = Path(args.schemas_dir)
    from_dir = schemas_dir / args.from_version
    to_dir = schemas_dir / args.to_version

    families = FAMILIES if args.family == "all" else (args.family,)
    for family in families:
        _diff_family(family, from_dir, to_dir, args.from_version, args.to_version)
    return 0


def _add_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cc-version", default=None, help="check only this version (default: every committed version)")
    parser.add_argument("--captures", default=str(DEFAULT_CAPTURES))
    parser.add_argument("--schemas-dir", default=str(DEFAULT_SCHEMAS))


def _add_seed_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("version", help="new CC version to seed a schema dir for (e.g. 2.1.201)")
    parser.add_argument("--schemas-dir", default=str(DEFAULT_SCHEMAS))


def _add_reconcile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cc-version", default=None)
    parser.add_argument("--captures", default=str(DEFAULT_CAPTURES))
    parser.add_argument("--schemas-dir", default=str(DEFAULT_SCHEMAS))
    parser.add_argument("--dry-run", action="store_true")


def _add_diff_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="from_version", required=True, help="cc-<version> dir name, e.g. cc-2.1.185")
    parser.add_argument("--to", dest="to_version", required=True, help="cc-<version> dir name, e.g. cc-2.1.198")
    parser.add_argument("--family", default="all", choices=["hooks", "statusline", "all"])
    parser.add_argument("--schemas-dir", default=str(DEFAULT_SCHEMAS))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cc_flyrig.schema",
        description="Owns the contract lifecycle: schemas/cc-<version>/ and everything that reads or writes it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="validate committed captures against the committed schema")
    _add_check_args(p_check)
    p_check.set_defaults(func=_cmd_check)

    p_seed = sub.add_parser("seed", help="forward-copy the latest schema of each family into a new version")
    _add_seed_args(p_seed)
    p_seed.set_defaults(func=_cmd_seed)

    p_reconcile = sub.add_parser("reconcile", help="merge observed capture fields into the committed schema")
    _add_reconcile_args(p_reconcile)
    p_reconcile.set_defaults(func=_cmd_reconcile)

    p_diff = sub.add_parser("diff", help="cross-version delta between two named committed schemas")
    _add_diff_args(p_diff)
    p_diff.set_defaults(func=_cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
