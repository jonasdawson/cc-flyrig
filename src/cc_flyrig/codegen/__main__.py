"""Composition root for the codegen factory.

Owns no codegen logic: it parses and validates the CLI, resolves the event family and
CC version for the requested work, reads each resolved runtime profile
(``lang/<runtime>.json`` -> a concrete ``profile.RuntimeProfile``, via ``toolchain.py``), wires the
object graph, and delegates to ``Generator``. Keeping logic out of here is what makes the pipeline
testable without argv.

The event family is an internal selector, not a CLI flag: the root derives it from ``--event``, or
generates every family when ``--event`` is omitted. Families version independently, so different
families may resolve to different CC versions (and thus different ``scaffolds/<runtime>/cc-<version>``
output directories) in the same run.

    python -m cc_flyrig.codegen generate --event PreToolUse [--cc-version 2.1.177]
    python -m cc_flyrig.codegen generate [--cc-version 2.1.177]  # all events, all families
    python -m cc_flyrig.codegen generate --event StatusLine     # family derived from event
"""

import argparse
import json
import sys
from pathlib import Path

from . import toolchain
from .generate import Generator
from .load import IntermediateRepresentationLoader
from .profile import RuntimeProfile
from .render import EntrypointRenderer, template_dir, template_runtimes
from .settings import FAMILY_SCHEMA_FILENAMES, Settings


def _latest_cc_version(schemas_dir: Path, family: str) -> str | None:
    # Only consider versions that ship this family's IR -- families version
    # independently, so a version dir carrying only the sibling namespace's schema is not a
    # candidate (e.g. a statusline-only cc-<version> dir is not "latest" for family hooks).
    schema_filename = FAMILY_SCHEMA_FILENAMES[family]
    versions = [
        p.name.removeprefix("cc-") for p in schemas_dir.glob("cc-*") if p.is_dir() and (p / schema_filename).is_file()
    ]
    if not versions:
        return None
    return max(versions, key=lambda v: tuple(int(part) for part in v.split(".")))


def _all_events(schemas_dir: Path, cc_version: str, family: str) -> list[str]:
    schema_filename = FAMILY_SCHEMA_FILENAMES[family]
    schema = json.loads((schemas_dir / f"cc-{cc_version}" / schema_filename).read_text())
    return sorted(
        name.removesuffix("Input") for name in schema["$defs"] if name.endswith("Input") and name != "CommonInput"
    )


def _bump_copier_default(out_dir: Path, new_version: str) -> None:
    """Write new_version to the language VERSION file when it is newer than the current one.

    No-ops silently when the VERSION file is absent or already at a higher version.
    """
    version_file = out_dir.parent / "VERSION"
    if not version_file.exists():
        return
    current = version_file.read_text().strip()
    if tuple(int(x) for x in new_version.split(".")) <= tuple(int(x) for x in current.split(".")):
        return
    version_file.write_text(new_version + "\n")
    print(f"bumped {version_file} to {new_version}", file=sys.stderr)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m cc_flyrig.codegen",
        description="Generate a typed, stdlib-only entrypoint for a Claude Code stdin-JSON event.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser(
        "generate", help="Generate typed entrypoints. Omit --event to generate all events of every family."
    )
    gen.add_argument(
        "--event",
        default=None,
        help="Event to scaffold (e.g. PreToolUse, StatusLine). Omit for all events of every family.",
    )
    gen.add_argument("--cc-version", help="Schema version to read/stamp (default: latest committed, per family).")
    gen.add_argument(
        "--runtime",
        default="python",
        help=(
            "Target runtime: selects the lang/<runtime>.json runtime profile and templates/<runtime>/ "
            "(default: python). Pass 'all' to generate every runtime with a template set in one run."
        ),
    )
    gen.add_argument("--schemas-dir", type=Path, default=Path("schemas"), help="Root of the schemas tree.")
    gen.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Root to write scaffolds under; the <runtime>/cc-<version>/ tree nests inside it, so it "
            "composes with --runtime all (default: scaffolds)."
        ),
    )
    args = parser.parse_args(argv)

    # Runtime-profile-file existence/content is checked later, per resolved (family, version) pair
    # (families may resolve to different versions in one run). The template directory, however, is
    # a pure function of --runtime, so it is validated here at the CLI boundary rather than failing
    # deep inside Jinja with TemplateNotFound. 'all' has no template dir of its own -- it fans out
    # over template_runtimes(), each of which is a real dir by construction.
    if args.runtime != "all":
        runtime_templates = template_dir(args.runtime)
        if not runtime_templates.is_dir():
            parser.error(f"no templates for runtime {args.runtime!r} at {runtime_templates}")

    return args


def _cli_error(message: str) -> int:
    """Report a clean CLI error (post-argparse) and return the conventional argparse exit code."""
    print(f"error: {message}", file=sys.stderr)
    return 2


def _out_dir(args: argparse.Namespace, runtime: str, version: str) -> Path:
    # --out-dir replaces the `scaffolds/` root; the `<runtime>/cc-<version>/` tree always nests
    # inside it, so the layout is identical to the default (and composes with --runtime all, each
    # runtime landing in its own subdir). `--out-dir scaffolds` reproduces the default exactly.
    root = args.out_dir if args.out_dir is not None else Path("scaffolds")
    return root / runtime / f"cc-{version}"


def _resolve_profile_for(
    args: argparse.Namespace, runtime: str, version: str, *, lenient: bool
) -> RuntimeProfile | int:
    """Resolve the runtime profile for (``runtime``, ``version``), including a toolchain probe.

    ``lenient`` (``--runtime all``) turns any reason this runtime cannot be generated -- a missing or
    malformed ``lang/<runtime>.json``, or an absent formatter/checker binary -- into a single
    ``skipping <runtime>`` stderr line and the exit code ``1`` (skip-and-report), rather than the hard
    ``_cli_error`` a concrete ``--runtime <name>`` gets. The toolchain probe only runs under
    ``lenient``; a concrete runtime keeps its existing per-event failure behavior.
    """
    version_dir = args.schemas_dir / f"cc-{version}"
    profile_path = version_dir / "lang" / f"{runtime}.json"
    if not profile_path.is_file():
        if lenient:
            print(f"skipping {runtime}: no runtime profile at {profile_path}", file=sys.stderr)
            return 1
        return _cli_error(f"no runtime profile for runtime {runtime!r} at {profile_path}")
    try:
        profile = toolchain.load_runtime_profile(version_dir, runtime)
    except ValueError as err:
        if lenient:
            print(f"skipping {runtime}: {err}", file=sys.stderr)
            return 1
        return _cli_error(str(err))
    if lenient and (tc_err := _toolchain_error(profile)):
        print(f"skipping {runtime}: {tc_err}", file=sys.stderr)
        return 1
    return profile


def _toolchain_error(profile: RuntimeProfile) -> str | None:
    """Return an error message if the profile's toolchain binaries are absent, else ``None``.

    Probes the already-resolved formatter/checker on empty input -- ``ruff format -`` and
    ``esbuild --loader=ts`` both accept it, and ``Toolchain.identity``/``no_check`` are no-ops -- so
    a missing binary surfaces as ``FileNotFoundError`` once, up front, instead of once per event with
    a half-written output tree. Only a missing binary is caught; any other failure (a real bug) is
    left to propagate.
    """
    try:
        profile.toolchain.format("")
        profile.toolchain.check("")
    except FileNotFoundError as err:
        return str(err)
    return None


def _find_family(args: argparse.Namespace, event: str) -> tuple[str, str] | int:
    """Find which family's schema (at its own resolved version) defines ``<event>Input``.

    Returns ``(family, version)``, or a clean CLI exit code if the event is unknown everywhere, or
    (defensively -- event names are disjoint today) defined in more than one family.
    """
    matches: list[tuple[str, str]] = []
    for family, schema_filename in FAMILY_SCHEMA_FILENAMES.items():
        version = args.cc_version or _latest_cc_version(args.schemas_dir, family)
        if version is None:
            continue
        schema_path = args.schemas_dir / f"cc-{version}" / schema_filename
        if not schema_path.is_file():
            continue
        schema = json.loads(schema_path.read_text())
        if f"{event}Input" in schema["$defs"]:
            matches.append((family, version))

    if not matches:
        return _cli_error(f"unknown event {event!r}: not found in any registered family")
    if len(matches) > 1:
        families = [family for family, _ in matches]
        return _cli_error(f"event {event!r} is defined in more than one family: {families}")
    return matches[0]


def _run_one(event: str, family: str, version: str, out_dir: Path, profile: RuntimeProfile, args) -> int:
    settings = Settings(
        event=event,
        cc_version=version,
        family=family,
        schemas_dir=args.schemas_dir,
        out_dir=out_dir,
    )
    generator = Generator(
        settings=settings,
        profile=profile,
        loader=IntermediateRepresentationLoader(settings),
        renderer=EntrypointRenderer(),
    )
    try:
        out_path = generator.run()
    except (ValueError, FileNotFoundError) as err:  # unknown event / missing checker binary
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


def _resolve_runtimes(args: argparse.Namespace) -> list[str]:
    """The runtimes this invocation targets: every template set for ``all``, else the one named."""
    if args.runtime == "all":
        return template_runtimes()
    return [args.runtime]


def _generate_for_runtime(args: argparse.Namespace, runtime: str, *, lenient: bool) -> int:
    """Generate one runtime's scaffolds (one event, or every event of every family).

    ``lenient`` is set only for ``--runtime all``: it lets a runtime that cannot be generated
    (missing profile / absent toolchain, resolved in ``_resolve_profile_for``) be skipped-and-reported
    rather than aborting the whole run, so the other runtimes still generate.
    """
    if args.event:
        found = _find_family(args, args.event)
        if isinstance(found, int):
            return found
        family, version = found
        out_dir = _out_dir(args, runtime, version)
        profile = _resolve_profile_for(args, runtime, version, lenient=lenient)
        if isinstance(profile, int):
            return profile
        rc = _run_one(args.event, family, version, out_dir, profile, args)
        if rc == 0 and family == "hooks":
            _bump_copier_default(out_dir, version)
        return rc

    # No --event: generate every event of every registered family, each at its own resolved
    # version. An explicit --cc-version that a family has no schema for skips that family with a
    # stderr note; it is only an error if *no* family has a schema at that version.
    rc = 0
    generated_any = False
    for family, schema_filename in FAMILY_SCHEMA_FILENAMES.items():
        version = args.cc_version or _latest_cc_version(args.schemas_dir, family)
        if version is None:
            continue
        schema_path = args.schemas_dir / f"cc-{version}" / schema_filename
        if not schema_path.is_file():
            if args.cc_version is not None:
                print(f"skipping {family}: no schema for cc-{version}", file=sys.stderr)
            continue

        generated_any = True
        out_dir = _out_dir(args, runtime, version)
        profile = _resolve_profile_for(args, runtime, version, lenient=lenient)
        if isinstance(profile, int):
            return profile
        events = _all_events(args.schemas_dir, version, family)
        family_rc = max(_run_one(event, family, version, out_dir, profile, args) for event in events)
        rc = max(rc, family_rc)
        if family_rc == 0 and family == "hooks":
            _bump_copier_default(out_dir, version)

    if not generated_any:
        version_note = args.cc_version or "latest"
        return _cli_error(
            f"no schema versions found under {args.schemas_dir}/cc-* for any registered family "
            f"(cc-version: {version_note})"
        )

    return rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    lenient = args.runtime == "all"
    runtimes = _resolve_runtimes(args)
    if not runtimes:  # only reachable for 'all' with an empty templates/ tree
        return _cli_error("no runtimes with a template set found under templates/")
    return max(_generate_for_runtime(args, runtime, lenient=lenient) for runtime in runtimes)


if __name__ == "__main__":
    sys.exit(main())
