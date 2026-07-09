"""The runtime profile — a frozen value object for one runtime's output shape and tooling.

``RuntimeProfile`` is the core-layer counterpart to ``lang/<runtime>.json``: the composition root
(``toolchain.py``, root layer) reads that file and constructs one, then injects it into the
pipeline. The core never imports ``..cli`` or reads the file itself — it only consumes the
already-resolved value object, which is what keeps ``generate.py``/``translate.py``/``resolve.py``
language-neutral.

``Toolchain`` is the formatter/checker pair a profile wires in. "No formatter configured" and "no
checker configured" are real, named values (``Toolchain.identity`` / ``Toolchain.no_check``)
rather than a fallback baked into the pipeline core — the core owns the concept of "explicitly
no-op" so the root layer never has to smuggle a magic ``None`` through call sites.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class Toolchain:
    """The formatter/checker pair a runtime profile wires in."""

    format: Callable[[str], str]
    check: Callable[[str], None]

    @staticmethod
    def identity(source: str) -> str:
        """The explicit no-op formatter: return the source unchanged."""
        return source

    @staticmethod
    def no_check(source: str) -> None:
        """The explicit no-op checker: perform no validation."""


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    """One runtime's output shape and tooling, resolved from ``lang/<runtime>.json``."""

    runtime: str
    extension: str
    stub_name: str
    class_names: dict[str, str]
    toolchain: Toolchain

    def class_name(self, def_name: str) -> str:
        """The generated class name for a ``$defs`` key (profile override, defaulting to the key)."""
        return self.class_names.get(def_name, def_name)
