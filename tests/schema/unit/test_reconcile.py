"""Unit tests for the reconcile pure core (schema.reconcile): observe() and propose().

All literal dicts — no filesystem, no tmp paths. See tests/schema/integration/test_reconcile.py
for the real-capture / real-schema replay.
"""

import copy

from cc_flyrig.schema.reconcile import observe, propose


def _schema(**defs) -> dict:
    return {"$defs": defs}


def _event_def(properties=None, required=None) -> dict:
    return {"type": "object", "properties": dict(properties or {}), "required": list(required or [])}


class TestObserveRequired:
    def test_key_present_in_all_samples__is_required(self):
        observed = observe({"Foo": [{"a": 1}, {"a": 2}]})
        (field,) = observed.fields
        assert field.key == "a"
        assert field.count == 2
        assert field.total == 2

    def test_key_present_in_only_some_samples__not_all(self):
        observed = observe({"Foo": [{"a": 1}, {}]})
        (field,) = observed.fields
        assert field.count == 1
        assert field.total == 2


class TestProposeRequired:
    def test_addition_required_iff_present_in_every_sample(self):
        schema = _schema(FooInput=_event_def())
        observed = observe({"Foo": [{"a": 1}, {"a": 2}]})
        proposal = propose(schema, observed)
        (addition,) = proposal.additions
        assert addition.key == "a"
        assert addition.required is True
        assert addition.seen == 2
        assert addition.total == 2

    def test_addition_not_required_when_absent_from_some_samples(self):
        schema = _schema(FooInput=_event_def())
        observed = observe({"Foo": [{"a": 1}, {}]})
        proposal = propose(schema, observed)
        (addition,) = proposal.additions
        assert addition.required is False
        assert addition.seen == 1
        assert addition.total == 2


class TestTypeInference:
    def test_string(self):
        observed = observe({"Foo": [{"a": "x"}]})
        assert observed.fields[0].type == "string"

    def test_integer(self):
        observed = observe({"Foo": [{"a": 1}]})
        assert observed.fields[0].type == "integer"

    def test_float(self):
        observed = observe({"Foo": [{"a": 1.5}]})
        assert observed.fields[0].type == "number"

    def test_boolean(self):
        observed = observe({"Foo": [{"a": True}]})
        assert observed.fields[0].type == "boolean"

    def test_boolean_never_conflated_with_integer(self):
        observed = observe({"Foo": [{"a": True}, {"a": False}]})
        assert observed.fields[0].type == "boolean"

    def test_dict(self):
        observed = observe({"Foo": [{"a": {"nested": 1}}]})
        assert observed.fields[0].type == "object"

    def test_list(self):
        observed = observe({"Foo": [{"a": [1, 2]}]})
        assert observed.fields[0].type == "array"

    def test_int_and_float_mix__collapses_to_number(self):
        observed = observe({"Foo": [{"a": 1}, {"a": 1.5}]})
        assert observed.fields[0].type == "number"

    def test_none_present__nullable_multi_type(self):
        observed = observe({"Foo": [{"a": "x"}, {"a": None}]})
        field_type = observed.fields[0].type
        assert isinstance(field_type, tuple)
        assert field_type == ("null", "string")

    def test_disagreeing_non_null_types__sorted_type_tuple(self):
        observed = observe({"Foo": [{"a": "x"}, {"a": 1}]})
        field_type = observed.fields[0].type
        assert isinstance(field_type, tuple)
        assert field_type == tuple(sorted(field_type))
        assert set(field_type) == {"integer", "string"}


class TestCommonInputNote:
    def test_key_proposed_for_two_or_more_events__emits_note(self):
        schema = _schema(FooInput=_event_def(), BarInput=_event_def())
        observed = observe({"Foo": [{"shared": 1}], "Bar": [{"shared": 2}]})
        proposal = propose(schema, observed)
        assert len(proposal.additions) == 2
        assert any("shared" in note for note in proposal.notes)

    def test_key_proposed_for_one_event_only__no_note(self):
        schema = _schema(FooInput=_event_def(), BarInput=_event_def())
        observed = observe({"Foo": [{"only_foo": 1}]})
        proposal = propose(schema, observed)
        assert proposal.notes == ()


class TestUnknownEventWarning:
    def test_event_with_no_matching_def__warns_no_crash_no_addition(self):
        schema = _schema(FooInput=_event_def())
        observed = observe({"NoSuchEvent": [{"a": 1}]})
        proposal = propose(schema, observed)
        assert proposal.additions == ()
        assert any("NoSuchEvent" in w for w in proposal.warnings)


class TestTypeConflictWarning:
    def test_conflicting_declared_type__warns_and_leaves_existing_declaration_untouched(self):
        schema = _schema(FooInput=_event_def(properties={"a": {"type": "string"}}))
        observed = observe({"Foo": [{"a": 123}]})
        proposal = propose(schema, observed)
        assert proposal.additions == ()
        assert any("a" in w and "conflict" in w for w in proposal.warnings)
        assert proposal.schema["$defs"]["FooInput"]["properties"]["a"] == {"type": "string"}

    def test_compatible_declared_type__no_warning_no_addition(self):
        schema = _schema(FooInput=_event_def(properties={"a": {"type": "string"}}))
        observed = observe({"Foo": [{"a": "hello"}]})
        proposal = propose(schema, observed)
        assert proposal.additions == ()
        assert proposal.warnings == ()

    def test_observed_integer_against_declared_number__not_a_conflict(self):
        # JSON Schema's "number" already validates integers (integer is its subtype) — this must
        # not warn, matching real committed data (e.g. duration_ms observed as int, declared number).
        schema = _schema(FooInput=_event_def(properties={"a": {"type": "number"}}))
        observed = observe({"Foo": [{"a": 5}]})
        proposal = propose(schema, observed)
        assert proposal.additions == ()
        assert proposal.warnings == ()

    def test_observed_number_against_declared_integer__is_a_conflict(self):
        schema = _schema(FooInput=_event_def(properties={"a": {"type": "integer"}}))
        observed = observe({"Foo": [{"a": 5.5}]})
        proposal = propose(schema, observed)
        assert any("a" in w and "conflict" in w for w in proposal.warnings)


class TestNoMutation:
    def test_propose_does_not_mutate_input_schema(self):
        schema = _schema(FooInput=_event_def())
        snapshot = copy.deepcopy(schema)
        observed = observe({"Foo": [{"a": 1}, {"a": 2}]})
        propose(schema, observed)
        assert schema == snapshot

    def test_proposal_schema_is_a_new_object(self):
        schema = _schema(FooInput=_event_def())
        observed = observe({"Foo": [{"a": 1}]})
        proposal = propose(schema, observed)
        assert proposal.schema is not schema
        assert proposal.schema["$defs"]["FooInput"] is not schema["$defs"]["FooInput"]
