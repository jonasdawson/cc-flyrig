"""Root layer: concrete tooling registries and runtime-profile loading.

This is the **one** place ``codegen`` imports ``..cli`` from — adding a runtime with new output
tooling means registering it in ``FORMATTERS``/``CHECKERS`` here, not editing the pipeline core.
``load_runtime_profile`` is the composition root's seam: it reads ``lang/<runtime>.json`` and
resolves it into a ``profile.RuntimeProfile``, failing loudly (``ValueError``) on a missing
required key or an unregistered tool name rather than silently falling back to Python defaults.
"""

import json
from pathlib import Path

from ..cli import esbuild, ruff
from .profile import RuntimeProfile, Toolchain

FORMATTERS = {"ruff": ruff.format}
"""Registered output formatters, keyed by the name a runtime profile requests."""

CHECKERS = {"esbuild": esbuild.check}
"""Registered output checkers, keyed by the name a runtime profile requests."""

_REQUIRED_KEYS = ("extension", "stub_name", "formatter", "checker")


def resolve_toolchain(formatter: str | None, checker: str | None) -> Toolchain:
    """Resolve a runtime profile's ``formatter``/``checker`` names into a ``Toolchain``.

    ``None`` -> the explicit identity/no-op value. An unregistered name raises ``ValueError``
    naming the registered choices — there is no silent fallback.
    """
    if formatter is None:
        fmt = Toolchain.identity
    elif formatter in FORMATTERS:
        fmt = FORMATTERS[formatter]
    else:
        raise ValueError(f"unknown formatter {formatter!r}; registered formatters: {sorted(FORMATTERS)}")

    if checker is None:
        check = Toolchain.no_check
    elif checker in CHECKERS:
        check = CHECKERS[checker]
    else:
        raise ValueError(f"unknown checker {checker!r}; registered checkers: {sorted(CHECKERS)}")

    return Toolchain(format=fmt, check=check)


def load_runtime_profile(version_dir: Path, runtime: str) -> RuntimeProfile:
    """Read ``<version_dir>/lang/<runtime>.json`` and resolve it into a ``RuntimeProfile``.

    ``extension``, ``stub_name``, ``formatter``, and ``checker`` are required keys (the latter two
    may legitimately hold ``null``); a missing key raises ``ValueError`` naming the key and the
    file. ``class_names`` stays optional, defaulting to ``{}``.
    """
    path = version_dir / "lang" / f"{runtime}.json"
    data = json.loads(path.read_text())
    for key in _REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"runtime profile {path} is missing required key {key!r}")
    return RuntimeProfile(
        runtime=runtime,
        extension=data["extension"],
        stub_name=data["stub_name"],
        class_names=data.get("class_names", {}),
        toolchain=resolve_toolchain(data["formatter"], data["checker"]),
    )
