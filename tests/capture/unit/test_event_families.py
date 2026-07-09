"""Tests for the event family descriptor (capture.event_families)."""

from cc_flyrig.capture.event_families import EVENT_FAMILIES, HOOKS_FAMILY, STATUSLINE_FAMILY
from cc_flyrig.schema import roster


def test_hooks_family_reuses_hook_events_roster():
    assert HOOKS_FAMILY.events == roster.EVENTS
    assert HOOKS_FAMILY.settings_keys == ("hooks",)
    assert HOOKS_FAMILY.captures_subdir is None


def test_statusline_family_roster_keys_subdir():
    assert STATUSLINE_FAMILY.events == ("StatusLine", "SubagentStatusLine")
    assert STATUSLINE_FAMILY.settings_keys == ("statusLine", "subagentStatusLine")
    assert STATUSLINE_FAMILY.probe_names == {
        "statusLine": "probe.py",
        "subagentStatusLine": "subagent_probe.py",
    }
    assert STATUSLINE_FAMILY.captures_subdir == "statusline"


def test_event_families_exhaustive():
    assert EVENT_FAMILIES == (HOOKS_FAMILY, STATUSLINE_FAMILY)
    all_events = {e for fam in EVENT_FAMILIES for e in fam.events}
    assert all_events == set(roster.EVENTS) | {"StatusLine", "SubagentStatusLine"}
