"""Build a language-neutral ``TypeNode`` AST from a JSON-Schema node.

``TypeNodeBuilder`` is a pure function of the loaded ``IntermediateRepresentation`` (no ``Settings``):
given a schema node it returns the ``TypeNode`` a field should carry, plus the set of ``$defs`` names
that node depends on (so the resolver can order emission). ``Resolver`` calls it per field; no
language syntax is produced here — that is the render layer's job.

Mapping rules (structure only; rendering is per-language):

- scalars: ``string``/``boolean``/``integer``/``number`` -> ``ScalarNode``;
- ``$ref``: -> ``RefNode`` of the target's class name (``OpenObject`` collapses to ``OpenObjectNode``;
  an alias collapses to its target's node);
- ``array`` -> ``ArrayNode``; ``oneOf`` -> ``UnionNode`` (deduped, order preserved);
- ``const`` and inline string ``enum`` -> ``LiteralNode`` (named ``$defs`` enums keep their class).

Inline objects with their own ``properties`` are handled by the resolver (it synthesizes a nested
dataclass and stores a ``RefNode`` to it), so here they fall through to ``OpenObjectNode`` only when
genuinely open.

``snake_case`` lives here because it converts *event* names (the output directory, the ``__main__``
import path) — a language-agnostic factory concern. Target field/enum naming (``snake_case`` +
reserved-word handling, ``acceptEdits`` -> ``ACCEPT_EDITS``) is Python-target idiom and lives in
``templates/python/_macros.jinja`` instead.
"""

import re
from dataclasses import dataclass

from .load import IntermediateRepresentation, ref_name
from .profile import RuntimeProfile
from .type_ast import (
    ArrayNode,
    LiteralNode,
    OpenObjectNode,
    RefNode,
    ScalarNode,
    TypeNode,
    UnionNode,
)

_SCALARS = frozenset({"string", "boolean", "integer", "number"})

# camelCase -> snake_case, modelled on inflection.underscore so acronym runs split correctly
# (``updatedMCPToolOutput`` -> ``updated_mcp_tool_output``). Owned rather than taken as a dependency:
# runtime mapper libraries are barred by the stdlib-only output rule, so
# the generated from_dict/to_dict already carry the wire<->field aliasing this conversion needs.
_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
_WORD_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def snake_case(name: str) -> str:
    """Convert a wire/event name to idiomatic ``snake_case`` (already-snake names pass through)."""
    name = _ACRONYM_BOUNDARY.sub(r"\1_\2", name)
    name = _WORD_BOUNDARY.sub(r"\1_\2", name)
    return name.lower()


@dataclass(frozen=True, slots=True)
class BuiltType:
    """A ``TypeNode`` plus the ``$defs`` names it references (for the resolver's toposort)."""

    node: TypeNode
    deps: frozenset[str]


class TypeNodeBuilder:
    """Maps schema nodes to ``TypeNode``s against a loaded ``IntermediateRepresentation``.

    ``profile`` supplies the class-name lookup for ``$ref`` targets — the codegen output config,
    injected alongside the IR rather than carried on it.
    """

    def __init__(self, ir: IntermediateRepresentation, profile: RuntimeProfile) -> None:
        self._ir = ir
        self._profile = profile

    def build(self, node: dict) -> BuiltType:
        if "$ref" in node:
            return self._build_ref(node["$ref"])
        if "oneOf" in node:
            return self._build_union(node["oneOf"])
        if "const" in node:
            return BuiltType(LiteralNode((node["const"],)), frozenset())
        type_ = node.get("type")
        if isinstance(type_, list):
            # JSON Schema allows "type": ["string", "null"] for nullable types.
            # "null" is handled by the required/optional mechanism; use the first non-null type.
            non_null = [t for t in type_ if t != "null"]
            type_ = non_null[0] if non_null else None
        if type_ == "string" and "enum" in node:
            return BuiltType(LiteralNode(tuple(node["enum"])), frozenset())
        if type_ in _SCALARS:
            return BuiltType(ScalarNode(type_), frozenset())
        if type_ == "array":
            items = self.build(node.get("items", {}))
            return BuiltType(ArrayNode(items.node), items.deps)
        # Open object, or a node we cannot type more precisely.
        return BuiltType(OpenObjectNode(), frozenset())

    def _build_ref(self, ref: str) -> BuiltType:
        name = ref_name(ref)
        if name == "OpenObject":
            return BuiltType(OpenObjectNode(), frozenset())
        if self._ir.def_kind(name) == "alias":
            return self._build_ref(self._ir.defs[name]["$ref"])
        return BuiltType(RefNode(self._profile.class_name(name)), frozenset({name}))

    def _build_union(self, branches: list[dict]) -> BuiltType:
        non_null = [b for b in branches if b.get("type") != "null"]
        built = [self.build(b) for b in non_null]
        members = [b.node for b in built]
        deps: set[str] = set()
        for b in built:
            deps |= b.deps
        unique = list(dict.fromkeys(members))  # dedupe, preserve order (TypeNodes are hashable)
        if len(unique) == 1:
            return BuiltType(unique[0], frozenset(deps))
        return BuiltType(UnionNode(tuple(unique)), frozenset(deps))
