"""A language-neutral type AST — the structured replacement for Python type-expression strings.

``TypeNode`` is the discriminated union the schema half of the pipeline (``load`` / ``translate`` /
``resolve``) hands to the render half. It carries *structure*, not language syntax: an ``ArrayNode``
of a ``RefNode`` is "a list of X", and each runtime's Jinja2 macros decide whether that renders as
``list[X]`` (Python) or ``X[]`` (TypeScript). Pushing the language-specific rendering into the
templates is what lets a new runtime be a macro + template contribution with no Python changes.

Each node carries a ``kind`` discriminant (a ``ClassVar`` — not a field, so it stays out of equality
and ``__init__``) so a Jinja2 macro can branch with ``{% if node.kind == "scalar" %}`` rather than
the ``isinstance`` checks it cannot express. ``RefNode`` stores an already-resolved *class name*
(codegen-config-controlled, resolved in Python the same way ``EnumSpec.class_name`` is): a reference may
point at a synthesized inline-object class that has no ``$defs`` key, so a class name — not a def
name — is the only representation that covers every reference.
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ScalarNode:
    """A JSON primitive: ``name`` is one of ``string`` / ``boolean`` / ``integer`` / ``number``."""

    kind: ClassVar[str] = "scalar"
    name: str


@dataclass(frozen=True, slots=True)
class RefNode:
    """A reference to a named class (enum or dataclass) — ``class_name`` is already codegen-config-resolved."""

    kind: ClassVar[str] = "ref"
    class_name: str


@dataclass(frozen=True, slots=True)
class ArrayNode:
    """A homogeneous array of ``items``."""

    kind: ClassVar[str] = "array"
    items: "TypeNode"


@dataclass(frozen=True, slots=True)
class UnionNode:
    """A union of ``members`` (from JSON-Schema ``oneOf``), deduped with order preserved."""

    kind: ClassVar[str] = "union"
    members: tuple["TypeNode", ...]


@dataclass(frozen=True, slots=True)
class LiteralNode:
    """Inline ``const`` / string ``enum`` values rendered as a literal type per language."""

    kind: ClassVar[str] = "literal"
    values: tuple[str | int | bool, ...]


@dataclass(frozen=True, slots=True)
class OpenObjectNode:
    """A genuinely open object — ``dict`` (Python) / ``Record<string, unknown>`` (TS); no schema."""

    kind: ClassVar[str] = "open_object"


TypeNode = ScalarNode | RefNode | ArrayNode | UnionNode | LiteralNode | OpenObjectNode
