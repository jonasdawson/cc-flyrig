"""Load and validate the declarative scenario battery (``capture_harness/scenarios.toml``).

A scenario describes one ``claude`` run the orchestrator drives to make hook events fire. Its
fields are grouped by concern into nested tables that mirror the orchestrator's phases: ``expect``
(coverage expectations), ``launch`` (how ``claude`` is invoked), ``setup`` (generic sandbox
preparation), and ``drive`` (TUI interaction + teardown). Opt-in *environment plugins* — fixture
servers, MCP servers, git sandboxes — live under ``environment_plugins`` and are validated generically
against the registry in :mod:`cc_flyrig.capture.environment_plugins`, so plugin-specifics never
leak into this schema. The ``expect.method`` taxonomy lets the coverage report classify events the
battery cannot trigger (headless/interactive limits) as *expected-missing* rather than failures.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields

from ..schema.roster import EVENTS
from .environment_plugins.base import EnvironmentPlugin

# How a scenario is expected to surface its events. Anything other than promptable/interactive is a
# known capture blind spot the reference fills.
CAPTURE_METHODS: frozenset[str] = frozenset(
    {
        "promptable",  # a plain prompt makes the event fire
        "interactive",  # needs TUI interaction (e.g. answering a permission/notification dialog)
        "launch-flag",  # needs a CLI flag, not a prompt (e.g. Setup via --init-only)
        "side-effect",  # needs a filesystem/config side effect during the run
        "failure-induced",  # needs a tool/API failure to be induced
        "unobservable",  # cannot be triggered by the harness; reference-authored only
    }
)

# Valid --effort flag values confirmed via `claude --help` (cc-2.1.168) (P6).
EFFORT_LEVELS: frozenset[str] = frozenset({"low", "medium", "high", "xhigh", "max"})

_DEFAULT_TIMEOUT_S = 180


class ManifestError(ValueError):
    """Raised when the scenario manifest is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class SandboxFile:
    path: str
    content: str = ""


@dataclass(frozen=True, slots=True)
class Interaction:
    """One step of a multi-turn interaction: wait for a signal, then send keystrokes."""

    wait_for: str  # an event name to wait for in the spool, or a substring to match in the pane
    send_keys: tuple[str, ...]
    # P3: optional mid-session file write applied in-place (inotify MODIFY) before send_keys.
    write_sandbox_file: str | None = None  # path relative to the sandbox
    content: str = ""


@dataclass(frozen=True, slots=True)
class Expect:
    """What the scenario should surface — drives the coverage matrix and retry-on-miss."""

    events: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    method: str = "promptable"  # one of CAPTURE_METHODS


@dataclass(frozen=True, slots=True)
class Launch:
    """How the ``claude`` process is invoked."""

    # P6: model alias/ID for --model; overrides the battery default_model.
    model: str | None = None
    permission_mode: str | None = None  # --permission-mode (default/bypassPermissions/auto/...)
    flags: tuple[str, ...] = ()  # extra CLI flags appended to argv (e.g. --init-only, --worktree)


@dataclass(frozen=True, slots=True)
class Setup:
    """Generic sandbox preparation applied before the run starts."""

    sandbox_files: tuple[SandboxFile, ...] = ()
    # P2: extra env vars merged into the child process env (FLYRIG_* vars take precedence).
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Drive:
    """How the TUI is driven and when the run completes and tears down."""

    interactions: tuple[Interaction, ...] = ()
    # Event to wait for before teardown (default "Stop"). Set to a later event (e.g. "PostCompact")
    # for scenarios whose interesting event fires after the first turn's Stop.
    complete_on: str | None = None
    timeout_s: int = _DEFAULT_TIMEOUT_S  # bounds the interaction and completion waits


@dataclass(frozen=True, slots=True)
class EnvironmentPlugins:
    """Opt-in environment plugins a scenario requested, as validated (name -> value) pairs.

    Generic on purpose: the set of valid names is the registry in ``environment_plugins``, not a
    fixed field list here, so a new plugin never changes this type. The orchestrator reads a
    requested plugin with :meth:`get` (e.g. ``environment_plugins.get("git_repo", False)``).
    """

    selected: tuple[tuple[str, object], ...] = ()

    def get(self, name: str, default: object = None) -> object:
        for k, v in self.selected:
            if k == name:
                return v
        return default

    def __contains__(self, name: object) -> bool:
        return any(k == name for k, _ in self.selected)


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    prompt: str = ""
    expect: Expect = field(default_factory=Expect)
    launch: Launch = field(default_factory=Launch)
    setup: Setup = field(default_factory=Setup)
    drive: Drive = field(default_factory=Drive)
    environment_plugins: EnvironmentPlugins = field(default_factory=EnvironmentPlugins)


@dataclass(frozen=True, slots=True)
class Meta:
    """Battery-wide settings from the manifest's ``[meta]`` table."""

    description: str = ""
    # P6: battery-wide model/effort defaults; a scenario's launch.model overrides default_model.
    default_model: str | None = None
    default_effort: str | None = None


@dataclass(frozen=True, slots=True)
class HookConfig:
    """One variant of the ``--settings`` file written for each scenario run."""

    default_script: str
    exclude_events: frozenset[str] = field(default_factory=frozenset)
    script_overrides: tuple[tuple[str, str], ...] = ()  # (event, script filename) pairs
    matchers: tuple[tuple[str, str], ...] = ()  # (event, matcher value) pairs


@dataclass(frozen=True, slots=True)
class RunSettings:
    standard: HookConfig
    native: HookConfig


@dataclass(frozen=True, slots=True)
class RunConfig:
    settings: RunSettings


@dataclass(frozen=True, slots=True)
class Manifest:
    meta: Meta
    scenarios: tuple[Scenario, ...]
    run: RunConfig | None = None


def _require_str_list(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ManifestError(f"{where} must be a list of strings")
    return tuple(value)


def _require_table(value: object, sid: str, where: str) -> dict:
    if not isinstance(value, dict):
        raise ManifestError(f"scenario {sid!r}: [{where}] must be a table")
    return value


def _reject_unknown(raw: dict, cls: type, sid: str, where: str | None = None) -> None:
    """Reject TOML keys that do not map to a field of ``cls`` (keys mirror field names)."""
    unknown = set(raw) - {f.name for f in fields(cls)}
    if unknown:
        loc = f" in [{where}]" if where else ""
        raise ManifestError(f"scenario {sid!r}: unknown key(s){loc}: {', '.join(sorted(unknown))}")


def _build_sandbox_files(value: object, sid: str) -> tuple[SandboxFile, ...]:
    if not isinstance(value, list):
        raise ManifestError(f"scenario {sid!r}: sandbox_files must be a list of tables")
    out: list[SandboxFile] = []
    for entry in value:
        if not isinstance(entry, dict) or "path" not in entry:
            raise ManifestError(f"scenario {sid!r}: each sandbox_files entry needs a 'path'")
        out.append(SandboxFile(path=str(entry["path"]), content=str(entry.get("content", ""))))
    return tuple(out)


def _build_interactions(value: object, sid: str) -> tuple[Interaction, ...]:
    if not isinstance(value, list):
        raise ManifestError(f"scenario {sid!r}: interactions must be a list of tables")
    out: list[Interaction] = []
    for entry in value:
        if not isinstance(entry, dict) or "wait_for" not in entry or "send_keys" not in entry:
            raise ManifestError(f"scenario {sid!r}: each interaction needs 'wait_for' and 'send_keys'")
        wsf = entry.get("write_sandbox_file")
        if wsf is not None and not isinstance(wsf, str):
            raise ManifestError(f"scenario {sid!r}: interaction.write_sandbox_file must be a string")
        out.append(
            Interaction(
                wait_for=str(entry["wait_for"]),
                send_keys=_require_str_list(entry["send_keys"], f"scenario {sid!r}: interaction.send_keys"),
                write_sandbox_file=wsf,
                content=str(entry.get("content", "")),
            )
        )
    return tuple(out)


def _build_env(value: object, sid: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise ManifestError(f"scenario {sid!r}: env must be a table")
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ManifestError(f"scenario {sid!r}: env keys and values must be strings")
    return tuple(sorted(value.items()))


def _build_expect(raw: dict, sid: str) -> Expect:
    _reject_unknown(raw, Expect, sid, "expect")
    events = _require_str_list(raw.get("events", []), f"scenario {sid!r}: expect.events")
    bad_events = [e for e in events if e not in EVENTS]
    if bad_events:
        raise ManifestError(f"scenario {sid!r}: unknown event name(s): {', '.join(bad_events)}")
    method = str(raw.get("method", "promptable"))
    if method not in CAPTURE_METHODS:
        raise ManifestError(f"scenario {sid!r}: expect.method {method!r} not in {sorted(CAPTURE_METHODS)}")
    tools = _require_str_list(raw.get("tools", []), f"scenario {sid!r}: expect.tools")
    return Expect(events=events, tools=tools, method=method)


def _build_launch(raw: dict, sid: str) -> Launch:
    _reject_unknown(raw, Launch, sid, "launch")
    model = raw.get("model")
    if model is not None and not isinstance(model, str):
        raise ManifestError(f"scenario {sid!r}: launch.model must be a string")
    permission_mode = raw.get("permission_mode")
    if permission_mode is not None and not isinstance(permission_mode, str):
        raise ManifestError(f"scenario {sid!r}: launch.permission_mode must be a string")
    flags = _require_str_list(raw.get("flags", []), f"scenario {sid!r}: launch.flags")
    return Launch(model=model, permission_mode=permission_mode, flags=flags)


def _build_setup(raw: dict, sid: str) -> Setup:
    _reject_unknown(raw, Setup, sid, "setup")
    return Setup(
        sandbox_files=_build_sandbox_files(raw.get("sandbox_files", []), sid),
        env=_build_env(raw.get("env", {}), sid),
    )


def _build_drive(raw: dict, sid: str) -> Drive:
    _reject_unknown(raw, Drive, sid, "drive")
    complete_on = raw.get("complete_on")
    if complete_on is not None and complete_on not in EVENTS:
        raise ManifestError(f"scenario {sid!r}: drive.complete_on {complete_on!r} is not a known event")
    timeout_s = raw.get("timeout_s", _DEFAULT_TIMEOUT_S)
    if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise ManifestError(f"scenario {sid!r}: drive.timeout_s must be a positive integer")
    return Drive(
        interactions=_build_interactions(raw.get("interactions", []), sid),
        complete_on=complete_on,
        timeout_s=timeout_s,
    )


def _build_environment_plugins(raw: dict, sid: str, registry: Mapping[str, EnvironmentPlugin]) -> EnvironmentPlugins:
    unknown = set(raw) - set(registry)
    if unknown:
        known = ", ".join(sorted(registry)) or "(none registered)"
        raise ManifestError(
            f"scenario {sid!r}: unknown environment_plugin(s): {', '.join(sorted(unknown))} (known: {known})"
        )
    selected: list[tuple[str, object]] = []
    for name in sorted(raw):
        try:
            value = registry[name].validate(raw[name])
        except ValueError as exc:
            raise ManifestError(f"scenario {sid!r}: environment_plugins.{name}: {exc}") from exc
        selected.append((name, value))
    return EnvironmentPlugins(tuple(selected))


def _validate_scenario(raw: dict, seen_ids: set[str]) -> str:
    """Validate a raw scenario's identity and top-level shape; return its unique id.

    Per-table field validation lives in the ``_build_*`` helpers; this consolidates the
    cross-cutting checks that belong to no single sub-table (identity, uniqueness, unknown
    top-level keys, and the prompt-or-launch.flags requirement).
    """
    if "id" not in raw or not isinstance(raw["id"], str) or not raw["id"].strip():
        raise ManifestError("every scenario needs a non-empty string 'id'")
    sid = raw["id"]
    if sid in seen_ids:
        raise ManifestError(f"duplicate scenario id: {sid!r}")
    seen_ids.add(sid)

    _reject_unknown(raw, Scenario, sid)

    launch = _require_table(raw.get("launch", {}), sid, "launch")
    if not str(raw.get("prompt", "")).strip() and not launch.get("flags"):
        raise ManifestError(f"scenario {sid!r}: needs a 'prompt' or launch.flags")
    return sid


def _build_scenario(raw: dict, seen_ids: set[str], registry: Mapping[str, EnvironmentPlugin]) -> Scenario:
    sid = _validate_scenario(raw, seen_ids)
    return Scenario(
        id=sid,
        prompt=str(raw.get("prompt", "")),
        expect=_build_expect(_require_table(raw.get("expect", {}), sid, "expect"), sid),
        launch=_build_launch(_require_table(raw.get("launch", {}), sid, "launch"), sid),
        setup=_build_setup(_require_table(raw.get("setup", {}), sid, "setup"), sid),
        drive=_build_drive(_require_table(raw.get("drive", {}), sid, "drive"), sid),
        environment_plugins=_build_environment_plugins(
            _require_table(raw.get("environment_plugins", {}), sid, "environment_plugins"), sid, registry
        ),
    )


def _validate_meta(meta: dict) -> None:
    """Validate the ``[meta]`` table's value domains (model/effort defaults)."""
    default_effort = meta.get("default_effort")
    if default_effort is not None and (not isinstance(default_effort, str) or default_effort not in EFFORT_LEVELS):
        raise ManifestError(f"meta.default_effort {default_effort!r} not in {sorted(EFFORT_LEVELS)}")
    default_model = meta.get("default_model")
    if default_model is not None and not isinstance(default_model, str):
        raise ManifestError("meta.default_model must be a string")


def _build_meta(data: dict) -> Meta:
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        raise ManifestError("[meta] must be a table")
    _validate_meta(meta)
    return Meta(
        description=str(meta.get("description", "")),
        default_model=meta.get("default_model"),
        default_effort=meta.get("default_effort"),
    )


def _build_hook_config(raw: dict, where: str) -> HookConfig:
    default_script = raw.get("default_script")
    if not isinstance(default_script, str) or not default_script:
        raise ManifestError(f"[{where}]: default_script must be a non-empty string")

    exclude_raw = raw.get("exclude_events", [])
    if not isinstance(exclude_raw, list) or not all(isinstance(e, str) for e in exclude_raw):
        raise ManifestError(f"[{where}]: exclude_events must be a list of strings")
    bad = [e for e in exclude_raw if e not in EVENTS]
    if bad:
        raise ManifestError(f"[{where}]: exclude_events: unknown event(s): {', '.join(sorted(bad))}")

    overrides_raw = raw.get("script_overrides", {})
    if not isinstance(overrides_raw, dict):
        raise ManifestError(f"[{where}.script_overrides] must be a table")
    bad_keys = [k for k in overrides_raw if k not in EVENTS]
    if bad_keys:
        raise ManifestError(f"[{where}.script_overrides]: unknown event(s): {', '.join(sorted(bad_keys))}")
    if not all(isinstance(v, str) for v in overrides_raw.values()):
        raise ManifestError(f"[{where}.script_overrides]: values must be strings")

    matchers_raw = raw.get("matchers", {})
    if not isinstance(matchers_raw, dict):
        raise ManifestError(f"[{where}.matchers] must be a table")
    bad_keys = [k for k in matchers_raw if k not in EVENTS]
    if bad_keys:
        raise ManifestError(f"[{where}.matchers]: unknown event(s): {', '.join(sorted(bad_keys))}")
    if not all(isinstance(v, str) for v in matchers_raw.values()):
        raise ManifestError(f"[{where}.matchers]: values must be strings")

    return HookConfig(
        default_script=default_script,
        exclude_events=frozenset(exclude_raw),
        script_overrides=tuple(sorted(overrides_raw.items())),
        matchers=tuple(sorted(matchers_raw.items())),
    )


def _build_run(data: dict) -> RunConfig | None:
    run_raw = data.get("run")
    if run_raw is None:
        return None
    if not isinstance(run_raw, dict):
        raise ManifestError("[run] must be a table")
    settings_raw = run_raw.get("settings")
    if not isinstance(settings_raw, dict):
        raise ManifestError("[run.settings] must be a table")
    standard_raw = settings_raw.get("standard")
    if not isinstance(standard_raw, dict):
        raise ManifestError("[run.settings.standard] must be a table")
    native_raw = settings_raw.get("native")
    if not isinstance(native_raw, dict):
        raise ManifestError("[run.settings.native] must be a table")
    return RunConfig(
        settings=RunSettings(
            standard=_build_hook_config(standard_raw, "run.settings.standard"),
            native=_build_hook_config(native_raw, "run.settings.native"),
        )
    )


def parse_manifest(text: str, environment_plugins: Mapping[str, EnvironmentPlugin] | None = None) -> Manifest:
    """Parse and validate a manifest from TOML text.

    ``environment_plugins`` is the registry that ``[scenario.environment_plugins]`` entries are
    validated against, injected by the composition root (``__main__``). It defaults to empty, so a
    caller that passes no registry rejects any plugin a scenario requests.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"invalid TOML: {exc}") from exc

    raw_scenarios = data.get("scenario", [])
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ManifestError("manifest must define at least one [[scenario]]")

    registry = environment_plugins or {}
    seen_ids: set[str] = set()
    scenarios = tuple(_build_scenario(s, seen_ids, registry) for s in raw_scenarios)
    return Manifest(meta=_build_meta(data), scenarios=scenarios, run=_build_run(data))
