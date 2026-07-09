"""Load the canonical IR (schema facts only) into an in-memory ``IntermediateRepresentation``.

``IntermediateRepresentationLoader`` reads ``schemas/cc-<version>/{hooks,statusline}.schema.json``
(``Settings.family`` picks the sibling namespace) and exposes the structural primitives
the rest of the pipeline queries: the raw ``$defs``, local ``$ref`` resolution, the version stamp,
and ``def_kind`` (the enum / alias / record classification). Both ``resolve`` and ``translate``
depend only on this module, so the classification lives here rather than in either consumer.

Runtime output shape (extension, stub name, tooling, class-name overrides) is not a schema fact —
that lives in ``profile.RuntimeProfile``, built by the composition root via ``toolchain.py``.

Local ``#/$defs/...`` reference resolution mirrors ``schema/walker.py``; that helper is not
imported to keep the dependency one-way (``codegen`` never reaches into ``schema`` internals).
"""

import json
from dataclasses import dataclass
from typing import Literal

from .settings import Settings

DefKind = Literal["enum", "alias", "record"]


def ref_name(ref: str) -> str:
    """Return the ``$defs`` key a local ``#/$defs/<name>`` reference points at."""
    if not ref.startswith("#/$defs/"):
        raise ValueError(f"only local '#/$defs/' refs are supported, got: {ref!r}")
    return ref.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class IntermediateRepresentation:
    """The loaded IR for one CC version — schema facts only, no runtime/output config."""

    cc_version: str
    schema_date: str
    defs: dict

    def resolve_ref(self, ref: str) -> dict:
        """Resolve a local ``#/$defs/<name>`` reference to its node."""
        return self.defs[ref_name(ref)]

    def def_kind(self, def_name: str) -> DefKind:
        """Classify a ``$defs`` entry structurally — independent of any ``x-`` annotation.

        ``string`` + ``enum`` -> ``enum``; a ``$ref``-only node (plus optional ``description``) ->
        ``alias``; anything else -> ``record``.
        """
        node = self.defs[def_name]
        if node.get("type") == "string" and "enum" in node:
            return "enum"
        if "$ref" in node and not (set(node) - {"$ref", "description"}):
            return "alias"
        return "record"


@dataclass(frozen=True, slots=True)
class IntermediateRepresentationLoader:
    """Reads the committed schema named by the injected ``Settings``."""

    settings: Settings

    def load(self) -> IntermediateRepresentation:
        base = self.settings.version_dir
        schema = json.loads((base / self.settings.schema_filename).read_text())
        return IntermediateRepresentation(
            cc_version=schema.get("x-cc-version", self.settings.cc_version),
            schema_date=schema.get("x-schema-date", ""),
            defs=schema["$defs"],
        )
