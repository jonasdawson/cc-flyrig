"""Pure core of ``schema reconcile``: merge observed capture fields into additive proposals.

Two pure functions, no filesystem/printing/clock access:

- :func:`observe` folds a family's captured payloads (already parsed JSON) into, per event, per
  top-level key, an occurrence count / sample total / inferred JSON-Schema type.
- :func:`propose` compares that observation against a committed schema and returns a
  :class:`Proposal`: a **new** schema dict with additive property proposals applied, plus the
  additions/notes/warnings a human reviews via ``git diff schemas/``.

Type representation: a key's inferred type is a plain ``str`` (e.g. ``"string"``) in the common
single-type case, or a ``tuple[str, ...]`` (sorted, including ``"null"`` when observed) when the
samples disagree on type or include ``None``. A tuple is used rather than a list to keep the
observation/result types consistently immutable, matching the ``Addition``/``Proposal`` dataclasses
below.

v1 scope: additions are always proposed **per event**, never folded into
``CommonInput`` — a key observed across multiple events is proposed once per event and surfaced via
an advisory note; the human promotes it to ``CommonInput`` by hand during review.
"""

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .keys import input_def_name
from .walker import walk_props


@dataclass(frozen=True, slots=True)
class FieldObservation:
    event: str
    key: str
    count: int  # samples of this event in which the key was present
    total: int  # total samples observed for this event
    type: str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedFields:
    fields: tuple[FieldObservation, ...]


@dataclass(frozen=True, slots=True)
class Addition:
    event: str
    key: str
    type: str | tuple[str, ...]
    required: bool
    seen: int
    total: int


@dataclass(frozen=True, slots=True)
class Proposal:
    schema: dict
    additions: tuple[Addition, ...]
    notes: tuple[str, ...]
    warnings: tuple[str, ...]


def _json_type(value: object) -> str:
    """Map a single Python value to its JSON-Schema type name.

    ``bool`` is a subtype of ``int`` in Python, so it is checked first: an observed ``True``/
    ``False`` is always ``"boolean"``, never ``"integer"``.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "null"


def _infer_type(values: Sequence[object]) -> str | tuple[str, ...]:
    """Infer the JSON-Schema type of a key from its observed values across samples.

    int/float mixed across samples collapse to a single ``"number"``. Any ``None`` observed, or
    disagreement among the non-null types, produces a sorted ``tuple`` (including ``"null"`` when
    a ``None`` was observed) instead of a single ``str``.
    """
    non_null_types: set[str] = set()
    has_null = False
    for value in values:
        if value is None:
            has_null = True
        else:
            non_null_types.add(_json_type(value))

    if {"integer", "number"} <= non_null_types:
        non_null_types -= {"integer", "number"}
        non_null_types.add("number")

    if has_null or len(non_null_types) > 1:
        types = set(non_null_types)
        if has_null:
            types.add("null")
        return tuple(sorted(types))

    if non_null_types:
        return next(iter(non_null_types))
    return "null"


def observe(samples: Mapping[str, Sequence[Mapping]]) -> ObservedFields:
    """Fold captured payloads into, per event, per top-level key, count/total/inferred type."""
    fields: list[FieldObservation] = []
    for event in sorted(samples):
        event_samples = samples[event]
        total = len(event_samples)
        values_by_key: dict[str, list[object]] = {}
        for sample in event_samples:
            for key, value in sample.items():
                values_by_key.setdefault(key, []).append(value)
        for key in sorted(values_by_key):
            values = values_by_key[key]
            fields.append(
                FieldObservation(event=event, key=key, count=len(values), total=total, type=_infer_type(values))
            )
    return ObservedFields(fields=tuple(fields))


def _resolve_ref(schema: dict, ref: str) -> dict:
    """Resolve a local ``#/...`` JSON Pointer against the root schema (mirrors ``walker.py``)."""
    if not ref.startswith("#/"):
        raise ValueError(f"only local '#/' refs are supported, got: {ref!r}")
    node: object = schema
    for part in ref[2:].split("/"):
        node = node[part]  # type: ignore[index]
    if not isinstance(node, dict):
        raise ValueError(f"ref {ref!r} did not resolve to an object")
    return node


def _declared_properties(schema: dict, node: dict, seen: set[str]) -> dict[str, dict]:
    """Merge the property *schemas* (not just names) reachable from ``node``.

    A sibling of ``walker._walk`` that keeps each property's own subschema (needed here to compare
    an observed type against what is already declared) instead of collapsing to a name set.
    """
    props: dict[str, dict] = {}
    if not isinstance(node, dict):
        return props

    ref = node.get("$ref")
    if isinstance(ref, str) and ref not in seen:
        seen.add(ref)
        props.update(_declared_properties(schema, _resolve_ref(schema, ref), seen))

    for combinator in ("allOf", "anyOf", "oneOf"):
        for sub in node.get(combinator, []):
            if isinstance(sub, dict):
                props.update(_declared_properties(schema, sub, seen))

    properties = node.get("properties")
    if isinstance(properties, dict):
        props.update(properties)

    return props


def _type_set(type_value: str | tuple[str, ...] | list[str]) -> set[str]:
    if isinstance(type_value, str):
        return {type_value}
    return set(type_value)


def _type_compatible(observed_type: str | tuple[str, ...], declared_type: str | list[str]) -> bool:
    """True when every observed type is already accepted by the declared type.

    JSON Schema's ``"number"`` keyword validates both ints and floats (``"integer"`` is its
    subtype), so an observed ``"integer"`` against a declared ``"number"`` is compatible, not a
    conflict — only the reverse (declared ``"integer"``, observed float/``"number"``) is one.
    """
    observed_set = _type_set(observed_type)
    declared_set = _type_set(declared_type)
    for t in observed_set:
        if t in declared_set:
            continue
        if t == "integer" and "number" in declared_set:
            continue
        return False
    return True


def propose(schema: dict, observed: ObservedFields) -> Proposal:
    """Compare ``observed`` against ``schema`` and return an additive :class:`Proposal`.

    Never mutates ``schema``: ``Proposal.schema`` is a fresh deep copy with proposed additions
    applied. Never touches ``CommonInput`` or an event beyond what was observed, and never edits or
    removes an already-declared property — a type conflict is reported as a warning only.
    """
    new_schema = copy.deepcopy(schema)
    defs = new_schema.setdefault("$defs", {})

    by_event: dict[str, list[FieldObservation]] = {}
    for field in observed.fields:
        by_event.setdefault(field.event, []).append(field)

    additions: list[Addition] = []
    warnings: list[str] = []
    key_to_events: dict[str, set[str]] = {}

    for event in sorted(by_event):
        def_name = input_def_name(event)
        if def_name not in schema.get("$defs", {}):
            warnings.append(f"unknown event {event!r}: no $defs/{def_name} in schema")
            continue

        known = walk_props(schema, def_name)
        declared = _declared_properties(schema, {"$ref": f"#/$defs/{def_name}"}, set())

        for field in sorted(by_event[event], key=lambda f: f.key):
            if field.key in known:
                declared_schema = declared.get(field.key)
                declared_type = declared_schema.get("type") if declared_schema else None
                if declared_type is not None and not _type_compatible(field.type, declared_type):
                    warnings.append(
                        f"{event}.{field.key}: observed type {field.type!r} conflicts with "
                        f"declared type {declared_type!r}"
                    )
                continue

            required = field.count == field.total
            additions.append(
                Addition(
                    event=event,
                    key=field.key,
                    type=field.type,
                    required=required,
                    seen=field.count,
                    total=field.total,
                )
            )
            key_to_events.setdefault(field.key, set()).add(event)

            props = defs[def_name].setdefault("properties", {})
            props[field.key] = {"type": list(field.type) if isinstance(field.type, tuple) else field.type}
            if required:
                req = defs[def_name].setdefault("required", [])
                if field.key not in req:
                    req.append(field.key)

    notes = tuple(
        f"{key!r} proposed for {len(events)} events ({', '.join(sorted(events))}) — consider promoting to CommonInput"
        for key, events in sorted(key_to_events.items())
        if len(events) >= 2
    )

    return Proposal(schema=new_schema, additions=tuple(additions), notes=notes, warnings=tuple(warnings))
