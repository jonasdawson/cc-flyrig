"""Render a typed hook entrypoint from the language-neutral specs + the IR's decision pattern (Jinja2).

``EntrypointRenderer`` is the **only** place Jinja2 is used. It selects the runtime's templates
(``templates/<runtime>/harness.jinja`` and ``stub.jinja``), which pull in that runtime's
``_macros.jinja`` to render the model block from the spec list, and switch ``run()``'s output
plumbing on the event's ``x-decision-pattern``. All 10 patterns from the IR are supported.

A generic ``regex_replace`` filter is registered on the environment: a language-agnostic string
primitive any runtime's macros can use to derive identifiers (Python's ``_macros.jinja`` uses it for
``snake_case`` field/enum naming). It is the one shared primitive — selecting a new runtime stays a
template + macro contribution with no Python changes here.

It is a pure text producer (no ``Settings``): writing the file is the ``Generator``'s job.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .resolve import EnumSpec, RecordSpec

_TEMPLATES = Path(__file__).parent / "templates"


def template_dir(runtime: str) -> Path:
    """The ``templates/<runtime>/`` directory a runtime's ``harness.jinja``/``stub.jinja`` live in.

    Lets the composition root check template existence at the CLI boundary without reaching into
    the private ``_TEMPLATES`` internal.
    """
    return _TEMPLATES / runtime


def template_runtimes() -> list[str]:
    """Every runtime with a complete template set under ``templates/`` (``harness`` + ``stub``).

    The source of truth for ``--runtime all``: a subdirectory counts only when it carries both
    ``harness.jinja`` and ``stub.jinja``, which excludes stray dirs (e.g. ``__pycache__``). Keeps
    ``_TEMPLATES`` encapsulated here rather than having the composition root glob it directly.
    """
    return sorted(
        p.name for p in _TEMPLATES.iterdir() if (p / "harness.jinja").is_file() and (p / "stub.jinja").is_file()
    )


SUPPORTED_PATTERNS = frozenset(
    {
        "hookSpecificOutput-permissionDecision",
        "top-level-decision",
        "none",
        "context-only",
        "exit-code-or-continue",
        "hookSpecificOutput-action-content",
        "display-content",
        "hookSpecificOutput-decision-behavior",
        "hookSpecificOutput-retry",
        "worktree-path-return",
        "text-return",
        "jsonlines-rows",
    }
)


def _regex_replace(value: str, pattern: str, repl: str) -> str:
    """Generic ``re.sub`` Jinja filter — a language-agnostic primitive for identifier derivation."""
    return re.sub(pattern, repl, value)


@dataclass(frozen=True, slots=True)
class EntrypointContext:
    """Everything the entrypoint templates need — assembled by the ``Generator`` from the IR + specs."""

    cc_version: str
    schema_date: str
    event: str
    event_snake: str
    input_class: str
    output_class: str | None
    decision_pattern: str
    runtime: str
    specs: list[EnumSpec | RecordSpec]


class EntrypointRenderer:
    """Renders the entrypoint files from an ``EntrypointContext``."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["regex_replace"] = _regex_replace

    def render_harness(self, ctx: EntrypointContext) -> str:
        return self._render(ctx, "harness.jinja")

    def render_stub(self, ctx: EntrypointContext) -> str:
        return self._render(ctx, "stub.jinja")

    def _render(self, ctx: EntrypointContext, name: str) -> str:
        if ctx.decision_pattern not in SUPPORTED_PATTERNS:
            raise NotImplementedError(f"decision pattern {ctx.decision_pattern!r} (event {ctx.event}) is not supported")
        return self._env.get_template(f"{ctx.runtime}/{name}").render(**_context_vars(ctx))


def _context_vars(ctx: EntrypointContext) -> dict:
    """A shallow field dict for ``Template.render`` — keeps ``specs`` as live objects (not ``asdict``).

    ``asdict`` would deep-convert the ``TypeNode`` / spec dataclasses to plain dicts and drop their
    ``kind`` discriminants, which the macros dispatch on.
    """
    return {
        "cc_version": ctx.cc_version,
        "schema_date": ctx.schema_date,
        "event": ctx.event,
        "event_snake": ctx.event_snake,
        "input_class": ctx.input_class,
        "output_class": ctx.output_class,
        "decision_pattern": ctx.decision_pattern,
        "specs": ctx.specs,
    }
