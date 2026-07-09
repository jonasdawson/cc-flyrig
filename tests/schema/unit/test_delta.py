"""Unit tests for the schema delta core (schema.delta).

Literal-dict cases only — no tmp files, no filesystem. See
tests/schema/integration/test_delta.py for the real cc-2.1.185 -> cc-2.1.198 replay.
"""

import copy

from cc_flyrig.schema.delta import delta


def _schema(defs: dict) -> dict:
    return {"$id": "irrelevant", "$defs": defs}


def test_def_added():
    a = _schema({"CommonInput": {"type": "object", "properties": {}}})
    b = _schema(
        {
            "CommonInput": {"type": "object", "properties": {}},
            "NewInput": {"type": "object", "properties": {}},
        }
    )
    report = delta(a, b)
    assert report.defs_added == ("NewInput",)
    assert report.defs_removed == ()
    assert report.def_changes == ()


def test_def_removed():
    a = _schema(
        {
            "CommonInput": {"type": "object", "properties": {}},
            "OldInput": {"type": "object", "properties": {}},
        }
    )
    b = _schema({"CommonInput": {"type": "object", "properties": {}}})
    report = delta(a, b)
    assert report.defs_removed == ("OldInput",)
    assert report.defs_added == ()
    assert report.def_changes == ()


def test_property_added_within_shared_def():
    a = _schema({"CommonInput": {"type": "object", "properties": {"session_id": {"type": "string"}}}})
    b = _schema(
        {
            "CommonInput": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "prompt_id": {"type": "string"},
                },
            }
        }
    )
    report = delta(a, b)
    assert len(report.def_changes) == 1
    change = report.def_changes[0]
    assert change.def_name == "CommonInput"
    assert change.properties_added == ("prompt_id",)
    assert change.properties_removed == ()
    assert change.type_changes == ()
    assert change.required_added == ()
    assert change.required_removed == ()


def test_property_removed_within_shared_def():
    a = _schema(
        {
            "CommonInput": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}, "gone": {"type": "string"}},
            }
        }
    )
    b = _schema({"CommonInput": {"type": "object", "properties": {"session_id": {"type": "string"}}}})
    report = delta(a, b)
    assert len(report.def_changes) == 1
    assert report.def_changes[0].properties_removed == ("gone",)
    assert report.def_changes[0].properties_added == ()


def test_property_retyped_within_shared_def():
    a = _schema({"CommonInput": {"type": "object", "properties": {"count": {"type": "integer"}}}})
    b = _schema({"CommonInput": {"type": "object", "properties": {"count": {"type": "string"}}}})
    report = delta(a, b)
    assert len(report.def_changes) == 1
    change = report.def_changes[0]
    assert len(change.type_changes) == 1
    tc = change.type_changes[0]
    assert tc.property == "count"
    assert tc.old_type == "integer"
    assert tc.new_type == "string"


def test_required_membership_added():
    a = _schema({"CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": []}})
    b = _schema({"CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}})
    report = delta(a, b)
    assert len(report.def_changes) == 1
    assert report.def_changes[0].required_added == ("x",)
    assert report.def_changes[0].required_removed == ()


def test_required_membership_removed():
    a = _schema({"CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}})
    b = _schema({"CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": []}})
    report = delta(a, b)
    assert len(report.def_changes) == 1
    assert report.def_changes[0].required_removed == ("x",)
    assert report.def_changes[0].required_added == ()


def test_metadata_differences_are_ignored():
    a = _schema(
        {
            "CommonInput": {
                "type": "object",
                "$id": "a-id",
                "description": "version A",
                "x-cc-version": "2.1.185",
                "x-schema-date": "2026-01-01",
                "properties": {"x": {"type": "string"}},
            }
        }
    )
    b = _schema(
        {
            "CommonInput": {
                "type": "object",
                "$id": "b-id",
                "description": "version B, totally different text",
                "x-cc-version": "2.1.198",
                "x-schema-date": "2026-07-04",
                "x-another-meta-key": "whatever",
                "properties": {"x": {"type": "string"}},
            }
        }
    )
    report = delta(a, b)
    assert report.def_changes == ()
    assert report.defs_added == ()
    assert report.defs_removed == ()


def test_unchanged_shared_def_produces_no_entry():
    a = _schema(
        {
            "CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            "OtherInput": {"type": "object", "properties": {"y": {"type": "integer"}}},
        }
    )
    b = _schema(
        {
            "CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            "OtherInput": {"type": "object", "properties": {"y": {"type": "integer"}, "z": {"type": "boolean"}}},
        }
    )
    report = delta(a, b)
    assert [c.def_name for c in report.def_changes] == ["OtherInput"]


def test_delta_does_not_mutate_inputs():
    a = _schema({"CommonInput": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}})
    b = _schema(
        {
            "CommonInput": {
                "type": "object",
                "properties": {"x": {"type": "string"}, "y": {"type": "string"}},
                "required": ["x", "y"],
            }
        }
    )
    a_copy = copy.deepcopy(a)
    b_copy = copy.deepcopy(b)
    delta(a, b)
    assert a == a_copy
    assert b == b_copy
