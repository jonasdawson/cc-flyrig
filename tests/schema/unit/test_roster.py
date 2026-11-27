"""Tests for the hook event registry (schema.roster)."""

from cc_flyrig.schema import roster


class TestEvents:
    def test_events__catalog__has_thirty_four_entries(self):
        assert len(roster.EVENTS) == 34

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
        assert set(roster.EVENTS) - set(roster.EVENT_SINCE) <= roster.events_as_of("2.1.168")

    def test_events_as_of__2_1_233__excludes_all_three_new_events(self):
        assert {"PreModelSwitch", "PostModelSwitch", "PreSkillShellCommand"}.isdisjoint(roster.events_as_of("2.1.233"))

    def test_events_as_of__2_1_251__includes_model_switch_events_excludes_pre_skill_shell_command(
        self,
    ):
        events = roster.events_as_of("2.1.251")
        assert {"PreModelSwitch", "PostModelSwitch"} <= events
        assert "PreSkillShellCommand" not in events

    def test_events_as_of__2_1_332__includes_all_three_new_events(self):
        assert {"PreModelSwitch", "PostModelSwitch", "PreSkillShellCommand"} <= roster.events_as_of("2.1.332")
