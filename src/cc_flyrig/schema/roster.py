"""Authoritative registry of the hook events this toolkit tracks.

``EVENTS`` is the full ordered set of 30 events the IR covers; it is the expected-coverage
contract for the battery and the drift gate.  ``TOOL_EVENTS`` is the subset that carry a tool
identity, making an event × tool matrix meaningful for them.

Both constants are tied to the IR version in ``schemas/``.  When CC adds or removes an event the
registry and the IR must be updated together.
"""

# The 30 hook events the IR covers, in lifecycle order. Mirrors
# tests/test_ir_schema.py. A payload's ``hook_event_name`` matches one of these names, and each maps
# to ``<Event>Input`` / ``<Event>Output`` definitions in the schema's ``$defs``.
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
)

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
