"""Authoritative registry of the hook events this toolkit tracks.

``EVENTS`` is the full ordered set of events the IR covers across every committed CC version; it is
the expected-coverage contract for the battery and the drift gate. ``TOOL_EVENTS`` is the subset
that carry a tool identity, making an event × tool matrix meaningful for them.

Not every event in ``EVENTS`` exists in every committed schema version -- CC adds events over time
(e.g. ``DirectoryAdded`` first appeared in 2.1.220). ``EVENT_SINCE`` records the earliest CC version
an event's ``$defs`` entry is expected in; an event absent from it is assumed present since the
original 2.1.168 baseline. Use ``events_as_of(cc_version)`` rather than the raw ``EVENTS`` tuple
when comparing against a *specific* committed schema version's ``$defs`` (see
``schema.drift_detector.roster_agreement``) -- comparing a historical version's defs against the
full, unscoped ``EVENTS`` would flag every not-yet-introduced event as missing.
"""

# Every hook event the IR covers across all committed CC versions, in lifecycle order. Mirrors
# tests/test_ir_schema.py (for the original 2.1.168 baseline). A payload's ``hook_event_name``
# matches one of these names, and each maps to ``<Event>Input`` / ``<Event>Output`` definitions in
# the schema's ``$defs`` -- but only from the version named in ``EVENT_SINCE`` onward, see above.
EVENTS: tuple[str, ...] = (
    "SessionStart",
    "Setup",
    "InstructionsLoaded",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "MessageDisplay",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "PermissionDenied",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Elicitation",
    "ElicitationResult",
    "DirectoryAdded",
    "PreModelSwitch",
    "PostModelSwitch",
    "PreSkillShellCommand",
)

# Earliest CC version each event's $defs entry is expected in. An event absent from this map is
# assumed present since the 2.1.168 baseline (the original 30). Keep in ascending version order.
EVENT_SINCE: dict[str, str] = {
    "DirectoryAdded": "2.1.220",
    # Docs: "requires Claude Code v2.1.251 or later" (no committed schema between 2.1.233 and 2.1.332).
    "PreModelSwitch": "2.1.251",
    "PostModelSwitch": "2.1.251",
    # Docs: "requires Claude Code v2.1.332 or later".
    "PreSkillShellCommand": "2.1.332",
}


def _version_tuple(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def events_as_of(cc_version: str) -> frozenset[str]:
    """The subset of ``EVENTS`` expected to have ``$defs`` entries in ``cc_version``'s schema.

    Filters out events whose ``EVENT_SINCE`` entry postdates ``cc_version``, so a historical
    schema version isn't flagged as missing an event CC hadn't introduced yet. A non-dotted-numeric
    ``cc_version`` (e.g. a test placeholder) fails open to the full roster rather than raising.
    """
    target = _version_tuple(cc_version)
    if target is None:
        return frozenset(EVENTS)
    return frozenset(e for e in EVENTS if _version_tuple(EVENT_SINCE.get(e, "0")) <= target)


# Events that carry a tool identity, so an event x tool coverage matrix is meaningful for them. The
# rest are tracked as event x observed-bool.
TOOL_EVENTS: frozenset[str] = frozenset(
    {
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "PermissionDenied",
    }
)
