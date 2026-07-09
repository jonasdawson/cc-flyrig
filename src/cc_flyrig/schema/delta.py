"""Cross-version schema delta — the pure core behind ``schema diff --from cc-A --to cc-B``.

Compares two committed schemas' ``$defs`` **locally**: a change to a shared def (e.g.
``CommonInput`` gaining a property) is reported once against that def, not once per event that
references it via ``$ref``. ``$id``, ``description``, and any ``x-*`` metadata keys are ignored —
every real schema pair differs there and it is noise, not drift.

Pure: no filesystem, printing, clock, or env access; inputs are never mutated. All I/O (loading
the two committed schema files, ``--family`` looping, printing, exit code) lives in
``schema/__main__.py``.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TypeChange:
    property: str
    old_type: str | None
    new_type: str | None


@dataclass(frozen=True, slots=True)
class DefChange:
    def_name: str
    properties_added: tuple[str, ...]
    properties_removed: tuple[str, ...]
    type_changes: tuple[TypeChange, ...]
    required_added: tuple[str, ...]
    required_removed: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.properties_added
            or self.properties_removed
            or self.type_changes
            or self.required_added
            or self.required_removed
        )


@dataclass(frozen=True, slots=True)
class DeltaReport:
    defs_added: tuple[str, ...]
    defs_removed: tuple[str, ...]
    def_changes: tuple[DefChange, ...]


def _diff_def(def_name: str, def_a: dict, def_b: dict) -> DefChange | None:
    props_a = def_a.get("properties", {})
    props_b = def_b.get("properties", {})

    properties_added = tuple(sorted(set(props_b) - set(props_a)))
    properties_removed = tuple(sorted(set(props_a) - set(props_b)))

    type_changes = []
    for prop in sorted(set(props_a) & set(props_b)):
        old_type = props_a[prop].get("type")
        new_type = props_b[prop].get("type")
        if old_type != new_type:
            type_changes.append(TypeChange(property=prop, old_type=old_type, new_type=new_type))

    required_a = set(def_a.get("required", []))
    required_b = set(def_b.get("required", []))
    required_added = tuple(sorted(required_b - required_a))
    required_removed = tuple(sorted(required_a - required_b))

    change = DefChange(
        def_name=def_name,
        properties_added=properties_added,
        properties_removed=properties_removed,
        type_changes=tuple(type_changes),
        required_added=required_added,
        required_removed=required_removed,
    )
    return change if change.has_changes else None


def delta(schema_a: dict, schema_b: dict) -> DeltaReport:
    """Compute the per-def-local delta between two committed schemas.

    ``schema_a``/``schema_b`` are plain ``dict``s (already-loaded ``$defs``-based JSON Schema
    documents); neither is read from disk here and neither is mutated.
    """
    defs_a = schema_a.get("$defs", {})
    defs_b = schema_b.get("$defs", {})

    defs_added = tuple(sorted(set(defs_b) - set(defs_a)))
    defs_removed = tuple(sorted(set(defs_a) - set(defs_b)))

    def_changes = []
    for def_name in sorted(set(defs_a) & set(defs_b)):
        change = _diff_def(def_name, defs_a[def_name], defs_b[def_name])
        if change is not None:
            def_changes.append(change)

    return DeltaReport(
        defs_added=defs_added,
        defs_removed=defs_removed,
        def_changes=tuple(def_changes),
    )
