"""Walk the canonical IR to compute the known top-level property set per hook event.

This is the keystone shared by the coverage report and the CI drift detector: because the IR
declares no ``additionalProperties: false``, JSON Schema validation alone never flags a *new*
field, so additive CC drift is detected by comparing the top-level keys observed in a captured
payload against the set this module computes.

Pure stdlib: it reads the committed JSON Schema and resolves local ``#/$defs`` references only. It
deliberately collects **top-level** property names — it does not recurse into a property's own
subschema, so the open ``OpenObject`` payloads (``tool_input``/``tool_response``/``content``) keep
their nested keys unconstrained by design.
"""

from .keys import input_def_name


def _resolve_ref(schema: dict, ref: str) -> dict:
    """Resolve a local ``#/...`` JSON Pointer against the root schema."""
    if not ref.startswith("#/"):
        raise ValueError(f"only local '#/' refs are supported, got: {ref!r}")
    node: object = schema
    for part in ref[2:].split("/"):
        node = node[part]  # type: ignore[index]
    if not isinstance(node, dict):
        raise ValueError(f"ref {ref!r} did not resolve to an object")
    return node


def _walk(schema: dict, node: dict, seen: set[str]) -> set[str]:
    """Union the top-level property names reachable from ``node`` via ``$ref``/``allOf``/``anyOf``/``oneOf``."""
    props: set[str] = set()
    if not isinstance(node, dict):
        return props

    ref = node.get("$ref")
    if isinstance(ref, str) and ref not in seen:
        seen.add(ref)
        props |= _walk(schema, _resolve_ref(schema, ref), seen)

    for combinator in ("allOf", "anyOf", "oneOf"):
        for sub in node.get(combinator, []):
            if isinstance(sub, dict):
                props |= _walk(schema, sub, seen)

    properties = node.get("properties")
    if isinstance(properties, dict):
        props |= set(properties)

    return props


def walk_props(schema: dict, def_name: str) -> set[str]:
    """Return the full set of known top-level property names for the ``$defs`` definition ``def_name``.

    Walks ``allOf`` composition and local ``$ref`` indirection (e.g. ``<Event>Input`` -> ``CommonInput``)
    and unions ``anyOf``/``oneOf`` branches permissively, so a key valid under any branch counts as known.
    """
    if def_name not in schema.get("$defs", {}):
        raise KeyError(f"no such definition: $defs/{def_name}")
    return _walk(schema, {"$ref": f"#/$defs/{def_name}"}, set())


def walk_event_props(schema: dict, event: str) -> set[str]:
    """Convenience: known top-level input property names for a hook ``event``."""
    return walk_props(schema, input_def_name(event))
