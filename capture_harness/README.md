# Capture harness (runbook)

This directory is the input and output **battery definitions** plus the in-session assets they
drive with (probe scripts, the MCP probe server, the decision fixture, a smoke-test `.claude/`) —
the engine and CLI that consume them live in `src/cc_flyrig/capture/`. Contributing a new
*runtime* never touches this directory (see CONTRIBUTING "Adding a runtime"); contributing coverage
for a new *CC event* starts here, in `scenarios.toml`.

This harness keeps the hand-authored schemas (`schemas/cc-<version>/hooks.schema.json` and its sibling
`statusline.schema.json`) honest against what Claude Code actually emits. It drives real `claude`
sessions to capture live stdin payloads, validates that authored output decisions take effect, and
flags drift when a new CC version ships.

Running a live capture needs `claude` + auth + budget + tmux, all present in the devcontainer —
**anyone with those** can run it, not only the project maintainer; see
[CONTRIBUTING.md](../CONTRIBUTING.md#contributing-a-captureschema-update-for-a-new-cc-version) for
the contributor-facing path. A maintainer's role is reviewing and merging the resulting PR. Per-PR CI
only runs `python -m cc_flyrig.schema check` against the committed `captures/` tree; it never
launches `claude`.

Everything runs as `python -m cc_flyrig.capture [<command>]` from the repo root, in the
devcontainer. With no `<command>`, it runs the default action — both the input and output scenario
batteries, in that order, sharing one resolved Claude install.

## Quick start

```sh
# Drive both the input and output scenario batteries for the installed CC version (via tmux).
python -m cc_flyrig.capture

# Check the fresh captures against the committed schema — the same gate CI runs.
python -m cc_flyrig.schema check
```

Iterating on one battery is cheaper: `capture inputs` drives only the input battery (live stdin
payloads); `capture outputs` drives only the output battery (validates output decisions take
effect). Both take `--scenario ID` to subset further.

The default run writes everything under `captures/cc-<version>/`. Inspect the results:

```sh
cat captures/cc-<version>/INPUT_COVERAGE.md               # which events fired, which payloads landed
cat captures/cc-<version>/HOOKS_MENU.md                   # the /hooks roster + per-entry docs + advisory cross-check
cat captures/cc-<version>/OUTPUT_COVERAGE.md              # output-decision validation results (from the outputs battery)
cat captures/cc-<version>/statusline/STATUSLINE_COVERAGE.md   # statusline event family coverage, under its own subtree
```

## Commands

| Command | What it does |
| --- | --- |
| *(no subcommand)* | **Default action.** Resolves the Claude install once, then drives **both** batteries in order: scans the `/hooks` menu, drives the input battery (`scenarios.toml`) via tmux, capturing both the hooks and statusline event families in one pass, consolidates + scrubs the spool per event family and writes `INPUT_COVERAGE.md` + `STATUSLINE_COVERAGE.md` + `HOOKS_MENU.md`; then drives the output battery (`output_scenarios.toml`) and writes `output_manifest.json` + `OUTPUT_COVERAGE.md`. Never writes to `schemas/`; if a new version has no committed schema yet, it prints a non-fatal hint to run `schema seed <v>`. Exits non-zero if the `/hooks`-menu pre-flight aborts (the output battery is then skipped — a stale scenario set poisons both batteries) or if any output assertion row fails; expected-but-missing input events stay report-only. |
| `inputs` | Drives only the input battery (today's former default) — the cheap iteration path when you don't need the output battery. |
| `outputs` | Drives only the output battery, each scenario returning a decision from `fixtures/decision_fixture.py` and asserting its effect (tool blocked, canary surfaced, …). Writes `output_manifest.json` + `OUTPUT_COVERAGE.md`. |
| `refresh` | Bring one version's derived state current, offline (never drives `claude`). If the spool holds envelopes for that version, family-scoped merges them into `captures/` (skip-with-note per family with nothing spooled, so an empty family never clobbers its committed report); then (re)renders all four derived reports — `INPUT_COVERAGE.md`, `STATUSLINE_COVERAGE.md`, `OUTPUT_COVERAGE.md`, `HOOKS_MENU.md` — each skip-with-note if its source is absent. |
| `provision <version>` | Install an isolated, version-pinned `claude` and print its binary path. |
| `version` | Print the installed CC version. |

`capture` only observes — it never writes to or gates against `schemas/`. The contract lifecycle
(seeding, checking, reconciling, and diffing schemas) lives in a separate module, run as
`python -m cc_flyrig.schema <command>`:

| Command | What it does |
| --- | --- |
| `check [--cc-version V]` | The CI gate. Validates committed captures against the committed schema for every committed version (or just `V`); exits non-zero on drift. Also fails if the event roster disagrees with the schema's `<Event>Input` def set. Prints `advisory` findings without failing. |
| `seed <version>` | Forward-copies the latest schema of each family (hooks + statusline) into a new version's schema dir; per-file idempotent, also copies `lang/` runtime profiles when present. |
| `reconcile [--cc-version V] [--dry-run]` | Reads committed captures, infers observed field types, and writes additive property proposals into the committed schema (or just prints them with `--dry-run`). Never edits `CommonInput` directly. |
| `diff --from cc-A --to cc-B [--family hooks\|statusline\|all]` | Informational cross-version delta between two committed schema versions (defs/properties/types/required-ness added or removed). |

Common flags (all commands): `--captures`, `--spool`, `--sandbox`, `--cc-version`, `--claude-bin`,
`--manifest`, `--probe`, `--output-scenarios` (path to `output_scenarios.toml`, like `--manifest` for
the output battery — accepted-and-ignored by commands that don't drive a battery). The default run,
`inputs`, and `outputs` also take `--scenario ID` (repeatable — run a subset); on the default run,
`--scenario` partitions the requested IDs across **both** batteries (composition-root
partitioning): a battery with no matching ID is skipped with a stderr note, and an ID matching
neither battery is a hard error rather than a silent drop. The default run and `inputs` also take
`--allow-menu-change`; `provision` takes `--method npm|native` and `--root`.

Sandboxes default to a temp dir **outside the repo** (`$TMPDIR/flyrig-sandboxes`) so driven sessions
never load the project's own `CLAUDE.md`/settings. Override with `--sandbox`.

## Workflows

### Re-baseline on a new CC release

```sh
python -m cc_flyrig.capture                                    # drives both batteries; produces captures/cc-<new>/ (no schema yet)
python -m cc_flyrig.schema seed <new>                           # forward-copy the latest schema into cc-<new>/
python -m cc_flyrig.schema check --cc-version <new>             # flags drift against the seeded schema
python -m cc_flyrig.schema reconcile --cc-version <new>         # proposes additive schema properties from observed captures
# review the proposed changes by hand:
git diff schemas/
python -m cc_flyrig.schema check                                # full re-verify across all committed versions
```

Review `INPUT_COVERAGE.md`, `OUTPUT_COVERAGE.md`, and `HOOKS_MENU.md`; review `git diff schemas/` by
hand for anything `reconcile` proposed (it never edits `CommonInput` directly — cross-event candidates
get an advisory note for a human to manually promote); then commit the new schema + `captures/cc-<new>/`.
Push, then tag `cc-<new>` and push the tag — CI generates all runtimes and attaches the Release assets.

If the default run reports that the `/hooks` menu differs from the IR roster, it warns and prompts before the
expensive drive (a non-interactive run aborts). Resolve the delta first — a menu-only event needs a
schema def + a scenario in `scenarios.toml` before capture can cover it; an IR-only event was removed
or renamed and should be retired. Use `--allow-menu-change` to proceed for a scripted re-baseline.

### Re-capture a version no longer installed

```sh
BIN=$(python -m cc_flyrig.capture provision <version>)
python -m cc_flyrig.capture --claude-bin "$BIN" --cc-version <version>
python -m cc_flyrig.schema check --cc-version <version>
```

Passing `--cc-version <version>` to the default run provisions inline when `--claude-bin` is left at its default, so the
explicit `provision` step is only needed when you want the binary path yourself. Set
`CLAUDE_CONFIG_DIR` (isolate config) and `DISABLE_AUTOUPDATER=1` (pin the version) before provisioning
if the shared devcontainer config would otherwise interfere.

### Smoke-test the probe by hand

Open `claude` from this directory — `.claude/settings.json` wires the passive probe locally, isolated
from the project's own `.claude`, so you can watch payloads land in the spool without driving the full
battery. Afterwards, fold the smoke session's spool into the tree with
`python -m cc_flyrig.capture refresh`.

## What's here

| Path | Purpose |
| --- | --- |
| `scenarios.toml` | Input battery. Each `[[scenario]]` is one driven `claude` run; `expect.events` drives coverage. `[meta]` sets battery defaults; `[run.settings.*]` picks the probe script + matchers per run mode; `[scenario.environment_plugins]` opts a scenario into a capture mechanism (below). |
| `output_scenarios.toml` | Output battery, driven by `capture outputs` (and by the default run). Each `[[scenarios]]` returns a decision and asserts its effect. The header comment documents every field. |
| `hooks/probe.py` | Passive, stdlib-only probe. Records each invocation's stdin to the spool; always exits 0 with empty stdout, never gates a tool call. |
| `hooks/worktree_probe.py` | Worktree capture shim wired on `WorktreeCreate` (whose command hook must print a directory path to stdout, which the passive probe can't). Creates the dir, prints the path, then best-effort spools. |
| `statusline/probe.py`, `statusline/subagent_probe.py` | Passive probes for the statusline family, wired via the `statusLine` / `subagentStatusLine` settings keys. |
| `servers/mcp_elicit_server.py` | Stdlib MCP stdio server exposing `probe_elicit`; calls `elicitation/create` mid-tool-call so CC fires `Elicitation` / `ElicitationResult`. Selected per-scenario via the `mcp_server` plugin. |
| `fixtures/decision_fixture.py` | Parameterized decision hook used by the output battery. Reads the desired output JSON from `FLYRIG_FIXTURE_DECISION` and writes it to stdout so CC acts on it. |
| `.claude/settings.json` | Harness-local probe wiring for the manual smoke test above. |

**Environment plugins** — opt-in capture mechanisms a scenario requests under
`[scenario.environment_plugins]`:

- `fixture_server = "ratelimit-429"` — localhost always-429 server (auto-injects `ANTHROPIC_BASE_URL`) to force the `StopFailure` rate-limit path reproducibly.
- `mcp_server = "elicit-probe"` — writes a per-scenario `--mcp-config` wiring `mcp_elicit_server.py` so elicitation events fire.
- `git_repo = true` — seeds the sandbox as a real git repo so CC's native worktree machinery can run.
- `worktree = true` — navigates the keep/remove worktree dialog on exit (used by the `worktree-remove` scenario).
