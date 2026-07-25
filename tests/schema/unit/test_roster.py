"""Tests for the hook event registry (schema.roster)."""

from cc_flyrig.schema import roster


class TestEvents:
    def test_events__catalog__has_thirty_one_entries(self):
        assert len(roster.EVENTS) == 31

    def test_events__every_baseline_event__has_input_and_output_def(self, schema):
        """``schema`` fixture is the 2.1.168 baseline -- only events since-or-before it apply."""
        defs = schema["$defs"]
        for event in roster.events_as_of("2.1.168"):
            assert f"{event}Input" in defs
            assert f"{event}Output" in defs


class TestEventsAsOf:
    def test_events_as_of__pre_introduction_version__excludes_event(self):
        assert "DirectoryAdded" not in roster.events_as_of("2.1.206")

    def test_events_as_of__introduction_version__includes_event(self):
        assert "DirectoryAdded" in roster.events_as_of("2.1.220")

    def test_events_as_of__post_introduction_version__includes_event(self):
        assert "DirectoryAdded" in roster.events_as_of("2.1.230")

    def test_events_as_of__baseline_events__always_included(self):
        assert set(roster.EVENTS) - {"DirectoryAdded"} <= roster.events_as_of("2.1.168")
