"""Drive the scenario battery against an interactive ``claude`` to capture real hook payloads.

Maintainer-run, in the devcontainer (needs ``claude`` + auth + tmux). Each scenario runs in an
isolated sandbox (``--settings`` injects the probe, ``--setting-sources project`` excludes user/local
config, cwd is outside the repo) so the project's own hooks never pollute capture and the probe never
pollutes the project. Turn completion is detected from the probe's own ``Stop`` capture rather than
fragile sleeps.

The engine is **plugin-agnostic**: it knows nothing about specific capture mechanisms. Each
requested environment plugin contributes to a ``RunPlan`` via ``configure`` (against the injected
registry); ``run_scenario`` only assembles and executes that plan. Concrete plugins are composed in
``__main__`` (the composition root) and injected in.
"""

import json
import sys
import time
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path

from ...cli.tmux import Tmux
from ...schema.roster import EVENTS
from .. import coverage_report
from ..environment_plugins.base import EnvironmentPlugin, RunPlan
from ..event_families import HOOKS_FAMILY, STATUSLINE_FAMILY
from ..scenario_manifest import HookConfig, Manifest, Scenario
from ..spool_consolidator import consolidate
from ..util.cc_version import detect_cc_version
from ..util.payload_scrubber import scrub
from .scenario_settings import HookEntry, StatusLineEntry, write_scenario_settings


@dataclass(frozen=True, slots=True)
class CapturePaths:
    probe: Path
    captures: Path
    spool: Path
    sandbox: Path
    coverage_report_filename: str = "INPUT_COVERAGE.md"
    statusline_coverage_report_filename: str = "STATUSLINE_COVERAGE.md"


@dataclass(frozen=True, slots=True)
class ClaudeInstall:
    bin: str = "claude"
    version: str | None = None


class CaptureError(RuntimeError):
    """Raised when the capture run cannot proceed (e.g. CC version undetectable)."""


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    run_id: str
    observed: frozenset[str]


def _hook_entries(config: HookConfig, probe_dir: Path, python: str) -> list[HookEntry]:
    override_map = dict(config.script_overrides)
    matcher_map = dict(config.matchers)
    entries: list[HookEntry] = []
    for event in EVENTS:
        if event in config.exclude_events:
            continue
        script = override_map.get(event, config.default_script)
        entries.append(HookEntry(event, f"{python} {probe_dir / script}", matcher_map.get(event)))
    return entries


def _progress_bar(done: int, total: int, width: int = 20) -> str:
    filled = round(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = round(100 * done / total) if total else 0
    return f"[{bar}] {done}/{total} ({pct}%)"


_STATUSLINE_DISPLAY_LABELS: Mapping[str, str] = {
    "StatusLine": "statusline",
    "SubagentStatusLine": "subagent-statusline",
}


def summarize_scenario(
    expected: tuple[str, ...],
    observed: frozenset[str],
    statusline_counts: Mapping[str, int],
) -> str:
    """Render a scenario's completion summary across both event families.

    Pure: no I/O, no printing — the caller (``run_scenarios``) prints the returned string. The
    hooks half intersects ``observed`` against ``expected`` only (not any family descriptor), so
    statusline tags observed alongside hooks events never contaminate the hooks ``n/m``.
    """
    n = len(set(expected) & observed)
    m = len(expected)
    mark = "✓" if n == m else "⚠"
    line = f"  {mark} hooks {n}/{m} expected"
    if n != m:
        missing = sorted(set(expected) - observed)
        line += f" (missing: {', '.join(missing)})"
    for event, count in statusline_counts.items():
        label = _STATUSLINE_DISPLAY_LABELS.get(event, event)
        line += f" · {label} ×{count}"
    return line


def _spool_events(spool_dir: Path, run_id: str) -> frozenset[str]:
    events: set[str] = set()
    for f in spool_dir.glob("*.json"):
        try:
            env = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if env.get("run_id") == run_id and env.get("event"):
            events.add(env["event"])
    return frozenset(events)


def _spool_event_count(spool_dir: Path, run_id: str, event: str) -> int:
    """Count spooled envelopes matching event+run_id (the probe writes one file per invocation)."""
    n = 0
    for f in spool_dir.glob("*.json"):
        try:
            env = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if env.get("run_id") == run_id and env.get("event") == event:
            n += 1
    return n


def check_assertion(
    assertion_type: str,
    event: str,
    spool_dir: Path,
    run_id: str,
    *,
    path: Path | None = None,
    canary: str | None = None,
) -> str:
    """Return 'pass', 'fail', or 'unobservable' for one output validation assertion.

    assertion_type values:
      spool-absent       event must NOT appear in spool for run_id
      spool-present      event must appear in spool for run_id
      spool-count-gt:N   event must appear more than N times (e.g. 'spool-count-gt:1')
      spool-count-lte:N  event must appear N or fewer times (e.g. 'spool-count-lte:1')
      filesystem         path must exist (pass path= kwarg)
      pane-contains      canary must appear in captured pane text (pass path= to pane.txt, canary=)
      unobservable       always returns 'unobservable'
    """
    if assertion_type == "unobservable":
        return "unobservable"
    events = _spool_events(spool_dir, run_id)
    if assertion_type == "spool-absent":
        return "pass" if event not in events else "fail"
    if assertion_type == "spool-present":
        return "pass" if event in events else "fail"
    if assertion_type.startswith("spool-count-gt:"):
        threshold = int(assertion_type.split(":")[1])
        return "pass" if _spool_event_count(spool_dir, run_id, event) > threshold else "fail"
    if assertion_type.startswith("spool-count-lte:"):
        threshold = int(assertion_type.split(":")[1])
        return "pass" if _spool_event_count(spool_dir, run_id, event) <= threshold else "fail"
    if assertion_type == "filesystem":
        return "pass" if (path is not None and path.exists()) else "fail"
    if assertion_type == "pane-contains":
        if path is None or canary is None:
            return "unobservable"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return "fail"
        return "pass" if canary in text else "unobservable"
    raise ValueError(f"unknown assertion_type: {assertion_type!r}")


def _wait_for(predicate, timeout_s: float, sleep, clock, *, poll: float = 1.0, required: bool = True) -> bool:
    """Poll ``predicate`` until true or ``timeout_s`` elapses. Raise on timeout only if ``required``."""
    deadline = clock() + timeout_s
    while True:
        if predicate():
            return True
        if clock() >= deadline:
            if required:
                raise TimeoutError("timed out waiting for capture condition")
            return False
        sleep(poll)


def _session_name(batch_id: str, scenario_id: str) -> str:
    raw = f"flyrig_{batch_id}_{scenario_id}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)


# Substrings used to read the interactive TUI state from a captured pane. These track the CC TUI and
# may need updating on a new release (the orchestrator is a maintainer tool, not a shipped artifact).
_READY_MARKER = "for shortcuts"  # the input-box footer; present once the prompt is ready
_INTERACTION_WAIT_S = 45  # cap on waiting for an interaction's trigger (dialog/event) to appear
# The first-launch folder-trust dialog ("Quick safety check: ... one you trust? ... 1. Yes, I trust
# this folder"). Default-highlighted option is "Yes", so Enter accepts.
_TRUST_MARKERS = ("trust this folder", "quick safety check")


def _wait_ready(tmux: Tmux, session: str, timeout_s: float, sleep, clock, *, poll: float) -> bool:
    """Wait until the TUI input box is ready, accepting a one-time folder-trust prompt if it appears."""
    _wait_for(lambda: tmux.has_session(session), 10.0, sleep, clock, poll=poll, required=False)
    deadline = clock() + timeout_s
    trusted = False
    while True:
        pane = tmux.capture_pane(session).lower()
        if not trusted and any(marker in pane for marker in _TRUST_MARKERS):
            tmux.send_key(session, "Enter")  # accept trust (default highlighted option)
            trusted = True
        elif _READY_MARKER in pane:
            return True
        if clock() >= deadline:
            return False
        sleep(poll)


def _seed_sandbox(scenario: Scenario, *, sandbox_root: Path, batch_id: str) -> Path:
    sandbox = sandbox_root / batch_id / scenario.id
    sandbox.mkdir(parents=True, exist_ok=True)
    for sf in scenario.setup.sandbox_files:
        target = sandbox / sf.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sf.content, encoding="utf-8")
    return sandbox


def _setup_claude_command(
    scenario: Scenario,
    *,
    claude_bin: str,
    settings_path: Path,
    model: str | None,
    effort: str | None,
) -> list[str]:
    argv = [claude_bin, "--settings", str(settings_path), "--setting-sources", "project"]
    if scenario.launch.permission_mode:
        argv += ["--permission-mode", scenario.launch.permission_mode]
    argv += list(scenario.launch.flags)
    if model:
        argv += ["--model", model]
    if effort:
        argv += ["--effort", effort]
    return argv


def _build_session_env(scenario: Scenario, *, spool_dir: Path, cc_version: str, run_id: str) -> dict:
    # P2: merge scenario env first; FLYRIG_* vars take precedence so a scenario cannot break the probe.
    return {
        **dict(scenario.setup.env),
        "FLYRIG_SPOOL_DIR": str(spool_dir),
        "FLYRIG_CC_VERSION": cc_version,
        "FLYRIG_RUN_ID": run_id,
    }


def _run_interactions(
    scenario: Scenario,
    *,
    tmux: Tmux,
    session: str,
    sandbox: Path,
    spool_dir: Path,
    run_id: str,
    sleep,
    clock,
    poll: float,
) -> None:
    for step in scenario.drive.interactions:
        # P1: capture a baseline count before waiting so a repeated wait_for only unblocks
        # on a *new* occurrence, not one already seen in a prior step.
        baseline = _spool_event_count(spool_dir, run_id, step.wait_for)
        # A dialog/event we're waiting to react to should appear within seconds; cap the
        # wait so a no-show (e.g. an auto-allowed command that never prompts) doesn't burn
        # the full timeout.
        _wait_for(
            lambda step=step, baseline=baseline: (
                _spool_event_count(spool_dir, run_id, step.wait_for) > baseline
                or step.wait_for in tmux.capture_pane(session)
            ),
            min(scenario.drive.timeout_s, _INTERACTION_WAIT_S),
            sleep,
            clock,
            poll=poll,
            required=False,
        )
        # P3: apply mid-session file write in-place (inotify MODIFY) before send_keys.
        if step.write_sandbox_file:
            target = sandbox / step.write_sandbox_file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step.content, encoding="utf-8")
        tmux.send_tokens(session, list(step.send_keys))


@dataclass(frozen=True, slots=True)
class _RunContext:
    """Concrete :class:`~cc_flyrig.capture.environment_plugins.base.RunContext` — the run
    state and engine helpers an environment plugin may touch from ``configure`` and its callbacks."""

    sandbox: Path
    native_settings_path: Path | None
    _tmux: Tmux
    _session: str
    _spool_dir: Path
    _run_id: str
    _sleep: Callable[[float], None]
    _clock: Callable[[], float]
    _poll: float

    def sleep(self, seconds: float) -> None:
        self._sleep(seconds)

    def send_text(self, text: str) -> None:
        self._tmux.send_text(self._session, text)

    def send_key(self, key: str) -> None:
        self._tmux.send_key(self._session, key)

    def wait_for_event(self, event: str, timeout_s: float) -> bool:
        return _wait_for(
            lambda: event in _spool_events(self._spool_dir, self._run_id),
            timeout_s,
            self._sleep,
            self._clock,
            poll=self._poll,
            required=False,
        )


def _teardown_session(
    tmux: Tmux,
    session: str,
    *,
    spool_dir: Path,
    run_id: str,
    sleep,
    clock,
    poll: float,
    teardown: list,
) -> None:
    tmux.send_text(session, "/exit")
    tmux.send_key(session, "Enter")
    for callback in teardown:  # environment plugin teardown (e.g. worktree-remove dialog navigation)
        callback()
    _wait_for(
        lambda: "SessionEnd" in _spool_events(spool_dir, run_id),
        10.0,
        sleep,
        clock,
        poll=poll,
        required=False,
    )
    tmux.kill_session(session)


def _drive_session(
    scenario: Scenario,
    *,
    tmux: Tmux,
    session: str,
    sandbox: Path,
    argv: list[str],
    env: dict,
    spool_dir: Path,
    run_id: str,
    ready_timeout_s: float,
    sleep,
    clock,
    poll: float,
    teardown: list,
) -> None:
    tmux.new_session(session, cwd=str(sandbox), command=argv, env=env)
    try:
        _wait_ready(tmux, session, ready_timeout_s, sleep, clock, poll=poll)
        if scenario.prompt:
            tmux.send_text(session, scenario.prompt)
            tmux.send_key(session, "Enter")
        _run_interactions(
            scenario,
            tmux=tmux,
            session=session,
            sandbox=sandbox,
            spool_dir=spool_dir,
            run_id=run_id,
            sleep=sleep,
            clock=clock,
            poll=poll,
        )
        if scenario.prompt:
            # Wait for the scenario's terminal event before teardown. Defaults to the turn's
            # Stop; set complete_on for events that fire after the first Stop (e.g. PostCompact
            # after /compact).
            terminal = scenario.drive.complete_on or "Stop"
            _wait_for(
                lambda: terminal in _spool_events(spool_dir, run_id),
                scenario.drive.timeout_s,
                sleep,
                clock,
                poll=poll,
                required=False,
            )
        (sandbox / "pane.txt").write_text(tmux.capture_pane(session), encoding="utf-8")
    finally:
        _teardown_session(
            tmux,
            session,
            spool_dir=spool_dir,
            run_id=run_id,
            sleep=sleep,
            clock=clock,
            poll=poll,
            teardown=teardown,
        )


def run_scenario(
    scenario: Scenario,
    *,
    environment_plugins: Mapping[str, EnvironmentPlugin],
    claude_bin: str,
    settings_path: Path,
    spool_dir: Path,
    sandbox_root: Path,
    cc_version: str,
    batch_id: str,
    tmux: Tmux,
    sleep=time.sleep,
    clock=time.monotonic,
    ready_timeout_s: float = 30.0,
    poll: float = 1.0,
    default_model: str | None = None,
    default_effort: str | None = None,
    native_settings_path: Path | None = None,
) -> ScenarioResult:
    """Drive one scenario through an interactive ``claude`` session and return the events it observed.

    Plugin-agnostic: each requested environment plugin contributes to a ``RunPlan`` via
    ``configure``; this function assembles and executes the plan (prefix/append argv, merge env,
    enter run contexts, run teardown callbacks).
    """
    run_id = f"{batch_id}:{scenario.id}"
    sandbox = _seed_sandbox(scenario, sandbox_root=sandbox_root, batch_id=batch_id)
    session = _session_name(batch_id, scenario.id)

    ctx = _RunContext(
        sandbox=sandbox,
        native_settings_path=native_settings_path,
        _tmux=tmux,
        _session=session,
        _spool_dir=spool_dir,
        _run_id=run_id,
        _sleep=sleep,
        _clock=clock,
        _poll=poll,
    )
    plan = RunPlan(settings_path=settings_path)
    for name, value in scenario.environment_plugins.selected:
        environment_plugins[name].configure(value, ctx, plan)

    # P6: model resolves here (scenario.launch.model overrides the battery default); effort is
    # battery-wide. Environment plugins have already set plan.settings_path / extra_argv / argv_prefix.
    model = scenario.launch.model or default_model
    base_argv = _setup_claude_command(
        scenario, claude_bin=claude_bin, settings_path=plan.settings_path, model=model, effort=default_effort
    )
    argv = plan.argv_prefix + base_argv + plan.extra_argv
    env = {**_build_session_env(scenario, spool_dir=spool_dir, cc_version=cc_version, run_id=run_id), **plan.env}

    with ExitStack() as stack:
        for run_context in plan.run_contexts:  # e.g. the fixture server; may yield env additions
            extra_env = stack.enter_context(run_context)
            if extra_env:
                env.update(extra_env)
        _drive_session(
            scenario,
            tmux=tmux,
            session=session,
            sandbox=sandbox,
            argv=argv,
            env=env,
            spool_dir=spool_dir,
            run_id=run_id,
            ready_timeout_s=ready_timeout_s,
            sleep=sleep,
            clock=clock,
            poll=poll,
            teardown=plan.teardown,
        )

    return ScenarioResult(scenario.id, run_id, _spool_events(spool_dir, run_id))


def run_scenarios(
    manifest: Manifest,
    environment_plugins: Mapping[str, EnvironmentPlugin],
    paths: CapturePaths,
    *,
    scenarios: list[str] | None = None,
    claude: ClaudeInstall = ClaudeInstall(),
) -> list[ScenarioResult]:
    """Run scenarios from the manifest, consolidate the spool, and write the coverage report.

    ``scenarios`` is a list of scenario IDs to run; ``None`` runs all. Raises
    :class:`CaptureError` if ``scenarios`` is given but no IDs match the manifest, or if the
    manifest has no ``[run.settings]`` block.
    """
    if manifest.run is None:
        raise CaptureError("[run.settings] is required in the manifest to run scenarios")

    if scenarios is not None:
        ids = set(scenarios)
        filtered = tuple(s for s in manifest.scenarios if s.id in ids)
        if not filtered:
            raise CaptureError(f"no scenarios match {sorted(ids)!r}")
        manifest = replace(manifest, scenarios=filtered)

    tmux = Tmux()
    cc_version = claude.version or detect_cc_version(claude.bin)
    batch_id = time.strftime("%Y%m%dT%H%M%S")
    paths.spool.mkdir(parents=True, exist_ok=True)
    paths.sandbox.mkdir(parents=True, exist_ok=True)

    probe_dir = paths.probe.parent
    python = sys.executable
    run_cfg = manifest.run.settings
    statusline_probe_dir = paths.probe.parent.parent / STATUSLINE_FAMILY.captures_subdir
    statusline_entries = [
        StatusLineEntry(
            settings_key=key,
            command=f"{python} {statusline_probe_dir / STATUSLINE_FAMILY.probe_names[key]}",
        )
        for key in STATUSLINE_FAMILY.settings_keys
    ]
    settings_path = write_scenario_settings(
        paths.sandbox / "probe-settings.json",
        _hook_entries(run_cfg.standard, probe_dir, python),
        statusline_entries,
    )
    native_settings_path = write_scenario_settings(
        paths.sandbox / "probe-settings-native.json",
        _hook_entries(run_cfg.native, probe_dir, python),
        statusline_entries,
    )

    results: list[ScenarioResult] = []
    total = len(manifest.scenarios)
    for scenario in manifest.scenarios:
        print(_progress_bar(len(results), total), "—", scenario.id, flush=True)
        result = run_scenario(
            scenario,
            environment_plugins=environment_plugins,
            claude_bin=claude.bin,
            settings_path=settings_path,
            spool_dir=paths.spool,
            sandbox_root=paths.sandbox,
            cc_version=cc_version,
            batch_id=batch_id,
            tmux=tmux,
            default_model=manifest.meta.default_model,
            default_effort=manifest.meta.default_effort,
            native_settings_path=native_settings_path,
        )
        results.append(result)
        statusline_counts = {ev: _spool_event_count(paths.spool, result.run_id, ev) for ev in STATUSLINE_FAMILY.events}
        print(summarize_scenario(scenario.expect.events, result.observed, statusline_counts), flush=True)
    print(_progress_bar(total, total), "— done", flush=True)

    scenario_ids = [s.id for s in manifest.scenarios]
    consolidate(
        paths.spool,
        paths.captures,
        cc_version=cc_version,
        on_process_payload=scrub,
        extra_capture_report={"batch_id": batch_id, "scenario_ids": scenario_ids},
        events=HOOKS_FAMILY.events,
    )
    consolidate(
        paths.spool,
        paths.captures,
        cc_version=cc_version,
        on_process_payload=scrub,
        extra_capture_report={"batch_id": batch_id, "scenario_ids": scenario_ids, "surface": "statusline"},
        subdir=STATUSLINE_FAMILY.captures_subdir,
        events=STATUSLINE_FAMILY.events,
    )

    cov_dir = paths.captures / f"cc-{cc_version}"
    (cov_dir / paths.coverage_report_filename).write_text(
        coverage_report.render_input_coverage(coverage_report.build_input_report(manifest, cov_dir, cc_version)),
        encoding="utf-8",
    )
    statusline_cov_dir = cov_dir / STATUSLINE_FAMILY.captures_subdir
    (statusline_cov_dir / paths.statusline_coverage_report_filename).write_text(
        coverage_report.render_statusline_coverage(
            coverage_report.build_statusline_report(manifest, statusline_cov_dir, cc_version)
        ),
        encoding="utf-8",
    )
    return results
