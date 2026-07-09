"""CLI for the capture harness: ``python -m cc_flyrig.capture <command>``.

Commands
--------
(no subcommand)  Default action: drives both scenario batteries (maintainer-run; needs claude +
                 tmux + auth) — the input battery (captures live stdin payloads) then the output
                 battery (validates output fields) — writing coverage reports for both. Exits
                 non-zero if the /hooks-menu pre-flight aborts (the output battery is then
                 skipped) or if any output assertion row fails.
inputs           Drive only the input scenario battery (today's former default).
outputs          Drive only the output validation battery and write output_manifest.json +
                 OUTPUT_COVERAGE.md.
refresh          Merge any spooled envelopes into captures/ (family-scoped, skip-with-note) and
                 (re)render all four derived reports for one version. Offline; never drives claude.
version          Print the installed Claude Code version.

``--scenario ID`` on the default run filters across both batteries (composition-root
partitioning: a battery with no matches is skipped with a note; an ID matching neither battery is
an error). There is no ``validate-outputs`` alias — it was removed in favor of the symmetric
``inputs``/``outputs`` verbs; argparse rejects it (exit 2).

This is the composition root: it calls ``environment_plugins.build_registry`` to assemble the
plugin registry and injects it into the parser and the engine, neither of which knows any specific
plugin.
"""

import argparse
import copy
import dataclasses
import json
import sys
import tempfile
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from ..schema import drift_detector
from . import coverage_report
from .environment_plugins import build_registry
from .event_families import EVENT_FAMILIES, HOOKS_FAMILY, STATUSLINE_FAMILY
from .orchestrator.menu_scanner import scan_hooks_menu
from .orchestrator.scenario_runner import (
    CaptureError,
    CapturePaths,
    ClaudeInstall,
    _progress_bar,
    check_assertion,
    run_scenario,
    run_scenarios,
)
from .orchestrator.scenario_settings import HookEntry, write_scenario_settings
from .provisioning import provision
from .scenario_manifest import (
    Drive,
    EnvironmentPlugins,
    Expect,
    Interaction,
    Launch,
    Scenario,
    Setup,
    parse_manifest,
)
from .spool_consolidator import _load_envelopes, consolidate
from .util.cc_version import detect_cc_version
from .util.payload_scrubber import scrub


def _build_env_plugins(s: "OutputScenario", registry: dict) -> EnvironmentPlugins:
    if s.mcp_server and "mcp_server" in registry:
        return EnvironmentPlugins(selected=(("mcp_server", s.mcp_server),))
    return EnvironmentPlugins()


REPO_ROOT = Path(__file__).resolve().parents[3]
CAPTURE_HARNESS_ROOT = REPO_ROOT / "capture_harness"
DEFAULT_MANIFEST = CAPTURE_HARNESS_ROOT / "scenarios.toml"
DEFAULT_PROBE = CAPTURE_HARNESS_ROOT / "hooks" / "probe.py"
DEFAULT_MCP_SERVERS = CAPTURE_HARNESS_ROOT / "servers"
DEFAULT_CAPTURES = REPO_ROOT / "captures"
DEFAULT_SPOOL = REPO_ROOT / "captures" / ".spool"
DEFAULT_SCHEMAS = REPO_ROOT / "schemas"
DEFAULT_SANDBOX = Path(tempfile.gettempdir()) / "flyrig-sandboxes"
DEFAULT_OUTPUT_SCENARIOS = CAPTURE_HARNESS_ROOT / "output_scenarios.toml"
DEFAULT_PROVISION_ROOT = REPO_ROOT / ".cache" / "cc"
COVERAGE_FILENAME = "INPUT_COVERAGE.md"


@dataclasses.dataclass(frozen=True, slots=True)
class Command:
    """A CLI subcommand: its name, the handler that runs it, and an optional
    configurator that registers command-specific arguments on its subparser."""

    name: str
    handler: Callable[[argparse.Namespace], int]
    add_args: Callable[[argparse.ArgumentParser], None] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class OutputScenario:
    id: str
    description: str
    prompt: str
    target_event: str
    fixture_decision: str
    probe_event: str
    assertion_type: str
    fields: list  # list of {"field": str, "variant": str | None}
    permission_mode: str = "bypassPermissions"
    timeout_s: float = 60.0
    canary: str = ""
    followup_prompt: str = ""
    followup_action: str = ""
    watched_path: str = ""
    model: str = ""
    mcp_server: str = ""
    assertion_path: str = ""
    fixture_exit_code: int = 0
    note: str = ""


def _parse_output_scenarios(text: str) -> list[OutputScenario]:
    import tomllib

    data = tomllib.loads(text)
    return [OutputScenario(**s) for s in data.get("scenarios", [])]


def _write_output_manifest(
    results: list[dict],
    cc_version: str,
    run_id: str,
    out_path: Path,
) -> None:
    summary: dict[str, int] = {}
    for r in results:
        summary[r["result"]] = summary.get(r["result"], 0) + 1
    manifest = {
        "cc_version": cc_version,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "summary": summary,
        "results": results,
    }
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _resolve_refresh_version(captures_root: Path, spool_dir: Path, cc_version: str | None) -> str:
    """Resolve the single CC version ``refresh`` operates on.

    In order: (1) an explicit ``cc_version``; (2) exactly one ``captures/cc-*`` dir; (3) the
    spool's envelopes, read leniently, if they carry exactly one ``cc_version`` stamp (salvage of
    a version whose captures dir doesn't exist yet). Otherwise ``SystemExit`` naming both
    ambiguities and asking for ``--cc-version``.
    """
    if cc_version:
        return cc_version
    dirs = sorted(p.name[3:] for p in captures_root.glob("cc-*") if p.is_dir())
    if len(dirs) == 1:
        return dirs[0]
    envelopes = _load_envelopes(spool_dir)
    spool_versions = sorted({e["cc_version"] for e in envelopes if e.get("cc_version")})
    if len(spool_versions) == 1:
        return spool_versions[0]
    raise SystemExit(
        f"cannot resolve --cc-version: capture dirs {dirs}, spool versions {spool_versions} "
        "— pass --cc-version explicitly"
    )


def _bucket_spool_events(envelopes: Iterable[Mapping], cc_version: str) -> dict[str, int]:
    """Pure: count spool envelopes (filtered to ``cc_version``) per event family.

    An envelope whose event is in neither family's roster counts toward neither — matching the
    battery's ``events=`` filter behavior.
    """
    counts = {family.name: 0 for family in EVENT_FAMILIES}
    for env in envelopes:
        if env.get("cc_version") != cc_version:
            continue
        event = env.get("event")
        for family in EVENT_FAMILIES:
            if event in family.events:
                counts[family.name] += 1
    return counts


def _add_scenario_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scenario",
        action="append",
        metavar="ID",
        default=[],
        help="run only this scenario ID (repeatable); omit to run all",
    )


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    _add_scenario_arg(parser)
    parser.add_argument(
        "--allow-menu-change",
        action="store_true",
        help="proceed past a /hooks menu change without prompting (scripted re-baseline)",
    )


def _add_provision_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("version", help="exact CC version to provision (e.g. 2.1.183)")
    parser.add_argument(
        "--method",
        default="npm",
        choices=["npm", "native"],
        help="installation method (default: npm)",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_PROVISION_ROOT),
        help="root directory for versioned installs (default: .cache/cc under repo root)",
    )


def _cmd_provision(args) -> int:
    install = provision(args.version, root=Path(args.root), method=args.method)
    print(install.bin)
    return 0


def _write_menu_artifacts(events: list[dict], raw: str, cov_dir: Path, cc_version: str) -> None:
    """Write the scrubbed raw scrape and the parsed menu JSON under ``captures/cc-<version>/``."""
    cov_dir.mkdir(parents=True, exist_ok=True)
    (cov_dir / "hooks_menu.txt").write_text(str(scrub(raw)), encoding="utf-8")
    payload = {"cc_version": cc_version, "events": events}
    (cov_dir / "hooks_menu.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _confirm_menu_change(findings: list, args) -> bool:
    """Warn about a /hooks-vs-IR difference and decide whether the run continues.

    ``--allow-menu-change`` proceeds without prompting; a non-interactive run aborts by default; an
    interactive run prompts. Keeps a stale scenario set from silently producing a capture.
    """
    print("\n⚠  /hooks menu differs from the IR roster:", file=sys.stderr)
    for f in findings:
        print(f"  {f}", file=sys.stderr)
    print(
        "New or renamed events need scenarios authored in scenarios.toml before a capture run can cover them.",
        file=sys.stderr,
    )
    if args.allow_menu_change:
        print("proceeding (--allow-menu-change).", file=sys.stderr)
        return True
    if not sys.stdin.isatty():
        return False
    return input("continue anyway? [y/N] ").strip().lower() in ("y", "yes")


def _resolve_install(args) -> ClaudeInstall:
    """Resolve the Claude install shared by every drive path (``inputs``/``outputs``/default).

    Provision inline when --cc-version is set and --claude-bin is still the default ("claude"),
    meaning the caller did not provide an explicit binary. An explicit --claude-bin always wins so
    existing invocations are unaffected (back-compat).
    """
    if args.cc_version and args.claude_bin == "claude":
        return provision(args.cc_version, root=DEFAULT_PROVISION_ROOT, method="npm")
    return ClaudeInstall(bin=args.claude_bin)


def _run_inputs(args, install: ClaudeInstall) -> int:
    cc_version = detect_cc_version(install.bin)
    events, raw = scan_hooks_menu(claude_bin=install.bin, sandbox_root=Path(args.sandbox))
    cov_dir = Path(args.captures) / f"cc-{cc_version}"
    _write_menu_artifacts(events, raw, cov_dir, cc_version)
    print(f"scanned /hooks: {len(events)} events; wrote {cov_dir / 'hooks_menu.json'}")
    findings = drift_detector.check_documented_events([e["event"] for e in events], source=cov_dir / "hooks_menu.json")
    if findings and not _confirm_menu_change(findings, args):
        print("aborted: /hooks menu differs from the IR; reconcile scenarios before capturing", file=sys.stderr)
        return 1

    registry = build_registry(DEFAULT_MCP_SERVERS)
    manifest = parse_manifest(Path(args.manifest).read_text(), registry)
    try:
        results = run_scenarios(
            manifest,
            registry,
            CapturePaths(
                probe=Path(args.probe),
                captures=Path(args.captures),
                spool=Path(args.spool),
                sandbox=Path(args.sandbox),
            ),
            scenarios=args.scenario or None,
            claude=install,
        )
    except CaptureError as e:
        raise SystemExit(str(e)) from e
    ran_ids = {r.scenario_id for r in results}
    observed = {e for r in results for e in r.observed}
    expected = {e for s in manifest.scenarios if s.id in ran_ids for e in s.expect.events}
    missing = sorted(expected - observed)
    hooks_events = set(HOOKS_FAMILY.events)
    statusline_events = set(STATUSLINE_FAMILY.events)
    print(
        f"ran {len(results)} scenarios; "
        f"hooks observed: {', '.join(sorted(observed & hooks_events)) or 'none'}; "
        f"statusline observed: {', '.join(sorted(observed & statusline_events)) or 'none'}"
    )
    if missing:
        print(f"expected-but-missing ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
    for family in ("hooks", "statusline"):
        if not (DEFAULT_SCHEMAS / f"cc-{cc_version}" / f"{family}.schema.json").exists():
            print(
                f"new version {cc_version} has no {family} schema — run: python -m cc_flyrig.schema seed {cc_version}",
                file=sys.stderr,
            )
    _render_hooks_menu(cov_dir, cc_version)
    return 0


def _cmd_inputs(args) -> int:
    return _run_inputs(args, _resolve_install(args))


def _render_hooks_menu(cov_dir: Path, cc_version: str) -> None:
    """Render HOOKS_MENU.md from the scanned menu + the IR schema (best-effort; needs the schema)."""
    schema_path = DEFAULT_SCHEMAS / f"cc-{cc_version}" / "hooks.schema.json"
    menu_json = cov_dir / "hooks_menu.json"
    if not (schema_path.exists() and menu_json.exists()):
        return
    report = coverage_report.build_documented_hooks_report(menu_json, json.loads(schema_path.read_text()))
    (cov_dir / "HOOKS_MENU.md").write_text(coverage_report.render_documented_hooks(report), encoding="utf-8")
    print(f"wrote {cov_dir / 'HOOKS_MENU.md'}")


def _cmd_refresh(args) -> int:
    """Bring one version's committed captures tree and every derivable report up to date.

    Conditional, family-scoped spool merge (skip-with-note per zero-count family; never clobbers
    a family's capture report by consolidating it with zero matching envelopes) followed by a
    render of all four derived reports (skip-with-note per absent source). Offline: no ``claude``,
    no network, no tmux.
    """
    captures_root = Path(args.captures)
    spool_dir = Path(args.spool)
    cc_version = _resolve_refresh_version(captures_root, spool_dir, args.cc_version)

    envelopes = _load_envelopes(spool_dir)
    version_envelopes = [e for e in envelopes if e.get("cc_version") == cc_version]
    if not version_envelopes:
        print("skipped merge (spool empty)")
    else:
        counts = _bucket_spool_events(envelopes, cc_version)

        if counts["hooks"] >= 1:
            result = consolidate(
                spool_dir,
                captures_root,
                cc_version=cc_version,
                on_process_payload=scrub,
                events=HOOKS_FAMILY.events,
            )
            print(f"consolidated {result.total} hooks payloads into {result.out_dir}")
        else:
            print("skipped hooks merge (no spooled envelopes)")

        if counts["statusline"] >= 1:
            result = consolidate(
                spool_dir,
                captures_root,
                cc_version=cc_version,
                on_process_payload=scrub,
                subdir=STATUSLINE_FAMILY.captures_subdir,
                extra_capture_report={"surface": "statusline"},
                events=STATUSLINE_FAMILY.events,
            )
            print(f"consolidated {result.total} statusline payloads into {result.out_dir}")
        else:
            print("skipped statusline merge (no spooled envelopes)")

    cov_dir = captures_root / f"cc-{cc_version}"
    if not cov_dir.exists():
        raise SystemExit(f"no captures for cc-{cc_version} — nothing to refresh")

    manifest = parse_manifest(Path(args.manifest).read_text(), build_registry(DEFAULT_MCP_SERVERS))

    input_report_path = cov_dir / COVERAGE_FILENAME
    input_report_path.write_text(
        coverage_report.render_input_coverage(coverage_report.build_input_report(manifest, cov_dir, cc_version)),
        encoding="utf-8",
    )
    print(f"wrote {input_report_path}")

    statusline_dir = cov_dir / STATUSLINE_FAMILY.captures_subdir
    if statusline_dir.exists():
        statusline_report_path = statusline_dir / "STATUSLINE_COVERAGE.md"
        statusline_report_path.write_text(
            coverage_report.render_statusline_coverage(
                coverage_report.build_statusline_report(manifest, statusline_dir, cc_version)
            ),
            encoding="utf-8",
        )
        print(f"wrote {statusline_report_path}")
    else:
        print("skipped STATUSLINE_COVERAGE.md (no statusline/ subtree)")

    output_manifest_path = cov_dir / "output_manifest.json"
    if output_manifest_path.exists():
        output_report_path = cov_dir / "OUTPUT_COVERAGE.md"
        output_report_path.write_text(
            coverage_report.render_output_coverage(coverage_report.build_output_report(output_manifest_path)),
            encoding="utf-8",
        )
        print(f"wrote {output_report_path}")
    else:
        print("skipped OUTPUT_COVERAGE.md (no output_manifest.json)")

    schema_path = DEFAULT_SCHEMAS / f"cc-{cc_version}" / "hooks.schema.json"
    menu_json = cov_dir / "hooks_menu.json"
    if schema_path.exists() and menu_json.exists():
        _render_hooks_menu(cov_dir, cc_version)
    else:
        print("skipped HOOKS_MENU.md (no hooks_menu.json/schema)")

    return 0


def _run_outputs(args, install: ClaudeInstall) -> int:
    from ..cli.tmux import Tmux

    output_scenarios_path = Path(args.output_scenarios or DEFAULT_OUTPUT_SCENARIOS)
    scenarios = _parse_output_scenarios(output_scenarios_path.read_text())
    if args.scenario:
        ids = set(args.scenario)
        scenarios = [s for s in scenarios if s.id in ids]
        if not scenarios:
            raise SystemExit(f"no scenarios match {sorted(ids)!r}")

    try:
        cc_version = detect_cc_version(install.bin)
    except Exception as e:
        raise SystemExit(f"could not detect CC version: {e}") from e

    batch_id = str(uuid.uuid4())[:8]
    spool_dir = Path(args.spool) / f"validate-{batch_id}"
    spool_dir.mkdir(parents=True, exist_ok=True)

    probe = Path(args.probe)
    fixture = CAPTURE_HARNESS_ROOT / "fixtures" / "decision_fixture.py"
    python = sys.executable
    tmux = Tmux()
    registry = build_registry(DEFAULT_MCP_SERVERS)

    results: list[dict] = []
    total = len(scenarios)
    for i, s in enumerate(scenarios):
        print(_progress_bar(i, total), "—", s.id, flush=True)
        run_id = f"{batch_id}:{s.id}"
        settings_path = Path(args.sandbox) / batch_id / s.id / "settings.json"
        write_scenario_settings(
            settings_path,
            [
                HookEntry(event=s.probe_event, command=f"{python} {probe}"),
                HookEntry(event=s.target_event, command=f"{python} {fixture}"),
            ],
        )
        interactions: list[Interaction] = []
        complete_on = None
        if s.followup_prompt:
            # Send follow-up after first Stop; second Interaction waits for second Stop.
            interactions = [
                Interaction(wait_for="Stop", send_keys=(s.followup_prompt, "Enter")),
                Interaction(wait_for="Stop", send_keys=()),
            ]
        if s.followup_action == "write-watched-path" and s.watched_path:
            # After Stop, write to the watched path to trigger FileChanged.
            # Path(sandbox) / absolute_path resolves to the absolute path in Python.
            interactions = [
                Interaction(
                    wait_for="Stop",
                    send_keys=(),
                    write_sandbox_file=s.watched_path,
                    content="flyrig-watch-trigger\n",
                ),
            ]
            complete_on = "FileChanged"
        fixture_env: list[tuple[str, str]] = [("FLYRIG_FIXTURE_DECISION", s.fixture_decision)]
        if s.fixture_exit_code:
            fixture_env.append(("FLYRIG_FIXTURE_EXIT_CODE", str(s.fixture_exit_code)))
        synthetic = Scenario(
            id=s.id,
            prompt=s.prompt,
            expect=Expect(events=(s.probe_event,), method="promptable"),
            launch=Launch(permission_mode=s.permission_mode, model=s.model or None),
            setup=Setup(env=tuple(fixture_env)),
            drive=Drive(interactions=tuple(interactions), timeout_s=int(s.timeout_s), complete_on=complete_on),
            environment_plugins=_build_env_plugins(s, registry),
        )
        run_scenario(
            synthetic,
            environment_plugins=registry,
            claude_bin=install.bin,
            settings_path=settings_path,
            spool_dir=spool_dir,
            sandbox_root=Path(args.sandbox),
            cc_version=cc_version,
            batch_id=batch_id,
            tmux=tmux,
        )
        pane_path = Path(args.sandbox) / batch_id / s.id / "pane.txt"
        if s.assertion_type == "pane-contains":
            assertion_path = pane_path
        elif s.assertion_type == "filesystem" and s.assertion_path:
            assertion_path = Path(s.assertion_path)
        else:
            assertion_path = None
        assertion_result = check_assertion(
            s.assertion_type,
            s.probe_event,
            spool_dir,
            run_id,
            path=assertion_path,
            canary=s.canary or None,
        )
        for field_entry in s.fields:
            row: dict = {
                "event": s.target_event,
                "field": field_entry["field"],
                "variant": field_entry.get("variant"),
                "assertion": s.assertion_type,
                "result": assertion_result,
            }
            if s.note and assertion_result == "unobservable":
                row["note"] = s.note
            results.append(row)

    print(_progress_bar(total, total), "— done", flush=True)

    cov_dir = Path(args.captures) / f"cc-{cc_version}"
    cov_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cov_dir / "output_manifest.json"
    _write_output_manifest(results, cc_version, batch_id, manifest_path)
    print(f"wrote {manifest_path}")

    report = coverage_report.build_output_report(manifest_path)
    out_cov = cov_dir / "OUTPUT_COVERAGE.md"
    out_cov.write_text(coverage_report.render_output_coverage(report), encoding="utf-8")
    print(f"wrote {out_cov}")

    failed = [r for r in results if r["result"] == "fail"]
    if failed:
        print(f"\nFAIL: {len(failed)} row(s):", file=sys.stderr)
        for r in failed:
            print(f"  {r['event']} / {r['field']} / {r['variant']}", file=sys.stderr)
        return 1
    return 0


def _cmd_outputs(args) -> int:
    return _run_outputs(args, _resolve_install(args))


def partition_scenarios(
    requested: list[str],
    input_ids: Collection[str],
    output_ids: Collection[str],
) -> tuple[list[str], list[str], list[str]]:
    """Partition requested ``--scenario`` IDs across the input/output batteries.

    Pure: no filesystem, printing, clock, or env access — the composition root does all I/O.

    No requested IDs -> both match lists come back empty; the caller (``_cmd_all``) treats "no
    filter" (``requested`` empty) as "run each battery in full" rather than "matched nothing" —
    that distinction lives in the caller, not here. An ID present in both ID sets is returned in
    both match lists (the two batteries' ID sets are disjoint today, but this must not assume it).
    An ID matching neither set is reported in ``unknown`` — never silently dropped.
    """
    if not requested:
        return [], [], []
    input_matches = [rid for rid in requested if rid in input_ids]
    output_matches = [rid for rid in requested if rid in output_ids]
    unknown = [rid for rid in requested if rid not in input_ids and rid not in output_ids]
    return input_matches, output_matches, unknown


def _read_scenario_ids(manifest_path: Path, output_scenarios_path: Path) -> tuple[set[str], set[str]]:
    """Cheaply read the two batteries' scenario ID sets straight from their TOMLs (no registry)."""
    import tomllib

    input_data = tomllib.loads(manifest_path.read_text())
    input_ids = {s["id"] for s in input_data.get("scenario", [])}
    output_data = tomllib.loads(output_scenarios_path.read_text())
    output_ids = {s["id"] for s in output_data.get("scenarios", [])}
    return input_ids, output_ids


def _cmd_all(args) -> int:
    install = _resolve_install(args)

    requested = list(args.scenario or [])
    output_scenarios_path = Path(args.output_scenarios or DEFAULT_OUTPUT_SCENARIOS)
    input_ids, output_ids = _read_scenario_ids(Path(args.manifest), output_scenarios_path)
    input_matches, output_matches, unknown = partition_scenarios(requested, input_ids, output_ids)

    if unknown:
        raise SystemExit(f"--scenario matched neither battery: {sorted(unknown)!r}")

    run_inputs = not requested or bool(input_matches)
    run_outputs = not requested or bool(output_matches)

    if requested and not input_matches:
        print("--scenario matched no input scenarios — skipping the input battery", file=sys.stderr)
    if requested and not output_matches:
        print("--scenario matched no output scenarios — skipping the output battery", file=sys.stderr)

    rc_in = 0
    if run_inputs:
        input_args = copy.copy(args)
        if requested:
            input_args.scenario = input_matches
        rc_in = _run_inputs(input_args, install)
        if rc_in:
            return rc_in

    rc_out = 0
    if run_outputs:
        output_args = copy.copy(args)
        if requested:
            output_args.scenario = output_matches
        rc_out = _run_outputs(output_args, install)

    return rc_in or rc_out


def _cmd_version(args) -> int:
    print(detect_cc_version(args.claude_bin))
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    common.add_argument("--probe", default=str(DEFAULT_PROBE))
    common.add_argument("--captures", default=str(DEFAULT_CAPTURES))
    common.add_argument("--spool", default=str(DEFAULT_SPOOL))
    common.add_argument("--sandbox", default=str(DEFAULT_SANDBOX))
    common.add_argument("--cc-version", default=None)
    common.add_argument("--claude-bin", default="claude")
    common.add_argument(
        "--output-scenarios",
        default=None,
        help="path to output_scenarios.toml (default: capture_harness/output_scenarios.toml)",
    )

    parser = argparse.ArgumentParser(
        prog="python -m cc_flyrig.capture",
        parents=[common],
        description="With no subcommand, drives both scenario batteries (the default action).",
    )
    # The combined drive is the default: its flags live on the top-level parser and it runs when no
    # subcommand is given. Subcommands are optional siblings for subsetting or the other operations.
    _add_run_args(parser)
    parser.set_defaults(func=_cmd_all)

    sub = parser.add_subparsers(dest="command")
    commands = (
        Command("provision", _cmd_provision, _add_provision_args),
        Command("refresh", _cmd_refresh),
        Command("inputs", _cmd_inputs, _add_run_args),
        Command("outputs", _cmd_outputs, _add_scenario_arg),
        Command("version", _cmd_version),
    )
    for cmd in commands:
        p = sub.add_parser(cmd.name, parents=[common])
        p.set_defaults(func=cmd.handler)
        if cmd.add_args:
            cmd.add_args(p)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
