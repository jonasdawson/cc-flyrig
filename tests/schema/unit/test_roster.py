"""Tests for the hook event registry (schema.roster)."""

from cc_flyrig.schema import roster


class TestEvents:
    def test_events__catalog__has_thirty_entries(self):
        assert len(roster.EVENTS) == 30

    def test_events__every_event__has_input_and_output_def(self, schema):
        defs = schema["$defs"]
        for event in roster.EVENTS:
            assert f"{event}Input" in defs
            assert f"{event}Output" in defs
