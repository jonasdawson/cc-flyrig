"""Event family descriptor — the single source of truth for what capture families exist.

An **event family** is a named set of events sharing one schema file, one Claude Code settings-key
wiring, one probe set, and one ``captures/`` subtree. Hooks is one family; statusline is another.
Downstream code keys off ``EventFamily.events`` / ``captures_subdir`` / ``settings_keys``
rather than hard-coding either family. Dependency-free leaf: imports only ``roster.EVENTS``.
"""

from dataclasses import dataclass

from ..schema.roster import EVENTS


@dataclass(frozen=True, slots=True)
class EventFamily:
    name: str
    events: tuple[str, ...]
    settings_keys: tuple[str, ...]
    probe_names: dict[str, str]
    captures_subdir: str | None


HOOKS_FAMILY = EventFamily(
    name="hooks",
    events=EVENTS,
    settings_keys=("hooks",),
    probe_names={},
    captures_subdir=None,
)

STATUSLINE_FAMILY = EventFamily(
    name="statusline",
    events=("StatusLine", "SubagentStatusLine"),
    settings_keys=("statusLine", "subagentStatusLine"),
    probe_names={"statusLine": "probe.py", "subagentStatusLine": "subagent_probe.py"},
    captures_subdir="statusline",
)

EVENT_FAMILIES: tuple[EventFamily, ...] = (HOOKS_FAMILY, STATUSLINE_FAMILY)
