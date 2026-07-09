"""Resolve raw ``$defs`` into ordered emit-specs — the contract handed to the render macros.

``Resolver`` turns the loaded ``IntermediateRepresentation`` into a toposorted list of ``EnumSpec`` / ``RecordSpec``
DTOs: it classifies each def (``def_kind``), flattens ``allOf[CommonX, local]`` into one field set
(flatten, never inherit), synthesizes a nested record for each inline structured object (e.g.
``hookSpecificOutput``), and emits dependencies before dependents so generated source needs no
forward references.

The spec DTOs are the language-neutral seam between the schema half (``load`` / ``resolve`` /
``translate``) and the render half (the per-runtime Jinja2 macros): each field carries a ``TypeNode``
and each enum its wire values, so the macros derive language identifiers and source without ever
seeing a JSON-Schema node.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from .load import IntermediateRepresentation, ref_name
from .profile import RuntimeProfile
from .translate import TypeNodeBuilder
from .type_ast import RefNode, TypeNode


def is_version_gated(node: dict) -> bool:
    """True if a property is present only from some CC version on (so it must emit optional).

    A required-ness concern, not a type-translation one: it lives beside ``_build_fields``, which is
    its only caller.
    """
    return "x-version-gated" in node or "x-version-gated-defer" in node


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field: the wire name, its language-neutral ``TypeNode``, and required-ness.

    The language identifier is derived from ``json_name`` by each runtime's macros (Python:
    ``snake_case`` + reserved-word suffix), so no language-specific name is stored here.
    """

    json_name: str
    type_node: TypeNode
    required: bool
    doc: str | None = None


@dataclass(frozen=True, slots=True)
class EnumSpec:
    """A string enum: ``wire_values`` are the on-the-wire values; macros derive member identifiers."""

    kind: ClassVar[str] = "enum"
    class_name: str
    wire_values: tuple[str, ...]
    doc: str | None = None


@dataclass(frozen=True, slots=True)
class RecordSpec:
    """A structured type with its fields in emit order (required before optional)."""

    kind: ClassVar[str] = "record"
    class_name: str
    fields: tuple[FieldSpec, ...]
    doc: str | None = None


@dataclass
class _Walk:
    """Mutable accumulator for one ``resolve`` call: specs keyed by name, in toposort order."""

    specs: dict[str, EnumSpec | RecordSpec] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def add(self, key: str, spec: EnumSpec | RecordSpec) -> None:
        if key not in self.specs:
            self.specs[key] = spec
            self.order.append(key)

    def result(self) -> list[EnumSpec | RecordSpec]:
        return [self.specs[k] for k in self.order]


class Resolver:
    """Resolves IR ``$defs`` into ordered emit-specs.

    Pure given an ``IntermediateRepresentation``, a ``TypeNodeBuilder``, and a ``RuntimeProfile``
    (the class-name lookup for emitted specs).
    """

    def __init__(self, ir: IntermediateRepresentation, builder: TypeNodeBuilder, profile: RuntimeProfile) -> None:
        self._ir = ir
        self._tr = builder
        self._profile = profile

    def resolve(self, roots: list[str]) -> list[EnumSpec | RecordSpec]:
        """Return the toposorted specs for ``roots`` and their transitive dependencies."""
        walk = _Walk()
        for root in roots:
            self._visit(root, walk)
        return walk.result()

    def flatten(self, def_name: str) -> tuple[set[str], dict[str, dict]]:
        """Merge ``allOf[{$ref CommonX}, {local}]`` into one ``(required, properties)`` pair.

        Common fields come first (the ``$ref`` is absorbed before the local block), then event
        specifics; ``properties`` preserves that order for deterministic field emission.
        """
        required: set[str] = set()
        props: dict[str, dict] = {}

        def absorb(node: dict) -> None:
            if "$ref" in node:
                absorb(self._ir.resolve_ref(node["$ref"]))
                return
            for sub in node.get("allOf", []):
                absorb(sub)
            required.update(node.get("required", []))
            props.update(node.get("properties", {}))

        absorb(self._ir.defs[def_name])
        return required, props

    def _visit(self, def_name: str, walk: _Walk) -> None:
        if def_name == "OpenObject" or def_name in walk.specs:
            return
        kind = self._ir.def_kind(def_name)
        if kind == "alias":
            # Aliases collapse into their target's type; only the target is ever emitted.
            self._visit(ref_name(self._ir.defs[def_name]["$ref"]), walk)
            return
        if kind == "enum":
            walk.add(def_name, self._enum_spec(def_name))
            return
        self._visit_record(def_name, walk)

    def _enum_spec(self, def_name: str) -> EnumSpec:
        node = self._ir.defs[def_name]
        return EnumSpec(self._profile.class_name(def_name), tuple(node["enum"]), node.get("description"))

    def _visit_record(self, def_name: str, walk: _Walk) -> None:
        required, props = self.flatten(def_name)
        cls = self._profile.class_name(def_name)
        fields, deps, nested = self._build_fields(required, props, cls)
        for dep in sorted(deps):
            self._visit(dep, walk)
        for key, spec in nested:
            walk.add(key, spec)
        walk.add(def_name, RecordSpec(cls, tuple(fields), self._ir.defs[def_name].get("description")))

    def _build_fields(
        self, required: set[str], props: dict[str, dict], owner_class: str
    ) -> tuple[list[FieldSpec], set[str], list[tuple[str, RecordSpec]]]:
        """Build a class's fields, collecting ``$defs`` deps and any synthesized nested specs.

        Returns ``(fields, deps, nested)`` where ``nested`` is the list of synthesized inline-object
        records (innermost first), each as a ``(spec_key, RecordSpec)`` to add before the
        owner. Fields are sorted required-before-optional (stable, so wire order is preserved within
        each group), satisfying the dataclass default-ordering rule.
        """
        fields: list[FieldSpec] = []
        deps: set[str] = set()
        nested: list[tuple[str, RecordSpec]] = []
        for json_name, node in props.items():
            if self._is_inline_object(node):
                synth = self._synth_class_name(owner_class, json_name)
                sub_required = set(node.get("required", []))
                sub_fields, sub_deps, sub_nested = self._build_fields(sub_required, node["properties"], synth)
                nested.extend(sub_nested)
                nested.append((synth, RecordSpec(synth, tuple(sub_fields), node.get("description"))))
                deps |= sub_deps
                type_node: TypeNode = RefNode(synth)
            else:
                built = self._tr.build(node)
                type_node = built.node
                deps |= built.deps
            is_required = json_name in required and not is_version_gated(node)
            fields.append(FieldSpec(json_name, type_node, is_required, node.get("description")))
        fields.sort(key=lambda f: 0 if f.required else 1)
        return fields, deps, nested

    @staticmethod
    def _is_inline_object(node: dict) -> bool:
        """An inline structured object (its own ``properties``) — typed, not a bare open ``dict``."""
        return node.get("type") == "object" and "properties" in node

    @staticmethod
    def _synth_class_name(owner_class: str, json_name: str) -> str:
        """Name a synthesized nested class: ``<event base><PropertyTitleCase>``.

        The owner's ``Input``/``Output`` suffix is dropped so ``PreToolUseOutput.hookSpecificOutput``
        becomes ``PreToolUseHookSpecificOutput`` rather than the doubled ``...OutputHookSpecificOutput``.
        """
        base = owner_class.removesuffix("Output").removesuffix("Input")
        return base + json_name[:1].upper() + json_name[1:]
