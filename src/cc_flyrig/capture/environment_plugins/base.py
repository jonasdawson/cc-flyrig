"""Abstractions for opt-in *environment plugins* — the contract between scenarios and the engine.

An environment plugin is a mechanism a scenario opts into to reach an event a plain prompt cannot.
This module declares only the **abstraction** (no concrete plugin, no orchestrator/manifest deps),
so the parser and the engine can depend on it without a cycle:

* :class:`EnvironmentPlugin` — a ``validate`` callable (manifest side: is the requested value
  legal?) and a ``configure`` callable (engine side: contribute to the run), so a plugin is a pair
  of functions.
* :class:`RunPlan` — the mutable accumulator an environment plugin contributes to.
* :class:`RunContext` — the slice of run state + engine helpers an environment plugin may touch.

Concrete plugins live one-per-module in this package; ``__init__`` assembles them into the
``ENVIRONMENT_PLUGINS`` registry, which ``__main__`` injects into the parser and the engine.
"""

from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class RunPlan:
    """What a scenario's environment plugins contribute to one ``claude`` invocation.

    The engine seeds ``settings_path`` (the default probe settings), lets each requested plugin
    mutate the plan, then executes it: prepend ``argv_prefix``, append ``extra_argv``, merge ``env``,
    enter each ``run_contexts`` manager (merging any env dict it yields), and run each ``teardown``
    callback after ``/exit``.
    """

    settings_path: Path
    argv_prefix: list[str] = field(default_factory=list)
    extra_argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    run_contexts: list[AbstractContextManager] = field(default_factory=list)
    teardown: list[Callable[[], None]] = field(default_factory=list)


class RunContext(Protocol):
    """The run state and engine helpers an environment plugin may use from ``configure``."""

    sandbox: Path
    native_settings_path: Path | None  # probe settings without the WorktreeCreate shim (P9)

    def sleep(self, seconds: float) -> None: ...
    def send_text(self, text: str) -> None: ...
    def send_key(self, key: str) -> None: ...
    def wait_for_event(self, event: str, timeout_s: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class EnvironmentPlugin:
    """One opt-in mechanism a scenario may request under ``[scenario.environment_plugins]``.

    ``validate`` returns the coerced value or raises ``ValueError`` (the manifest adds the scenario
    id). ``configure`` contributes this plugin's behaviour to ``plan`` for the upcoming run.
    """

    validate: Callable[[object], object]
    configure: Callable[[object, RunContext, RunPlan], None]


def require_bool(value: object) -> object:
    """Validator: accept a boolean, else raise ``ValueError`` (the manifest adds scenario context)."""
    if not isinstance(value, bool):
        raise ValueError("must be a boolean")
    return value


def require_one_of(allowed: Collection[str], value: object) -> object:
    """Validator: accept a string in ``allowed``, else raise ``ValueError``."""
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"must be one of {sorted(allowed)}")
    return value
