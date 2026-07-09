"""Build the output coverage report model from a committed ``output_manifest.json``.

Reads the manifest as plain JSON; never imports from the writer side. Each field in the IR
field inventory is classified as pass / fail / unobservable / not-tested by merging against
the manifest results. ``not-tested`` does not appear in the manifest — it is synthesised here
by comparing the inventory against what was tested.
"""

import json
from dataclasses import dataclass
from pathlib import Path

PASS = "pass"
FAIL = "fail"
UNOBSERVABLE = "unobservable"
NOT_TESTED = "not-tested"

# Every (event, field, variant) the IR claims to support — derived from the §Field inventory in
# 20260619-feature__output-validation.md. Adding an entry here is a conscious act; auto-generation
# from the schema is intentionally avoided (output inventory is about behavioral coverage, not shape
# completeness).
FIELD_INVENTORY: list[dict] = [
    # PreToolUse — hookSpecificOutput-permissionDecision
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "deny"},
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "allow"},
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "ask"},
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecision", "variant": "defer"},
    {"event": "PreToolUse", "field": "hookSpecificOutput.permissionDecisionReason", "variant": None},
    {"event": "PreToolUse", "field": "hookSpecificOutput.updatedInput", "variant": None},
    {"event": "PreToolUse", "field": "hookSpecificOutput.additionalContext", "variant": None},
    # PermissionRequest — hookSpecificOutput-decision-behavior
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.behavior", "variant": "deny"},
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.behavior", "variant": "allow"},
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.updatedInput", "variant": None},
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.updatedPermissions", "variant": None},
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.message", "variant": None},
    {"event": "PermissionRequest", "field": "hookSpecificOutput.decision.interrupt", "variant": None},
    # PermissionDenied — hookSpecificOutput-retry
    {"event": "PermissionDenied", "field": "hookSpecificOutput.retry", "variant": "true"},
    {"event": "PermissionDenied", "field": "hookSpecificOutput.retry", "variant": "false"},
    # Elicitation — hookSpecificOutput-action-content
    {"event": "Elicitation", "field": "hookSpecificOutput.action", "variant": "accept"},
    {"event": "Elicitation", "field": "hookSpecificOutput.action", "variant": "decline"},
    {"event": "Elicitation", "field": "hookSpecificOutput.action", "variant": "cancel"},
    {"event": "Elicitation", "field": "hookSpecificOutput.content", "variant": None},
    # WorktreeCreate — worktree-path-return
    {"event": "WorktreeCreate", "field": "stdout-bare-path", "variant": None},
    {"event": "WorktreeCreate", "field": "hookSpecificOutput.worktreePath", "variant": None},
    # UserPromptSubmit — top-level-decision
    {"event": "UserPromptSubmit", "field": "decision", "variant": "block"},
    {"event": "UserPromptSubmit", "field": "reason", "variant": None},
    {"event": "UserPromptSubmit", "field": "hookSpecificOutput.sessionTitle", "variant": None},
    # PostToolUse — top-level-decision
    {"event": "PostToolUse", "field": "decision", "variant": "block"},
    {"event": "PostToolUse", "field": "hookSpecificOutput.additionalContext", "variant": None},
    {"event": "PostToolUse", "field": "hookSpecificOutput.updatedToolOutput", "variant": None},
    {"event": "PostToolUse", "field": "hookSpecificOutput.updatedMCPToolOutput", "variant": None},
    # SessionStart — context-only
    {"event": "SessionStart", "field": "hookSpecificOutput.additionalContext", "variant": None},
    {"event": "SessionStart", "field": "hookSpecificOutput.initialUserMessage", "variant": None},
    {"event": "SessionStart", "field": "hookSpecificOutput.sessionTitle", "variant": None},
    {"event": "SessionStart", "field": "hookSpecificOutput.watchPaths", "variant": None},
    {"event": "SessionStart", "field": "hookSpecificOutput.reloadSkills", "variant": None},
    # TaskCreated — exit-code-or-continue
    {"event": "TaskCreated", "field": "exit-code-2", "variant": None},
    # CommonOutput — all non-none events (tested on UserPromptSubmit)
    {"event": "UserPromptSubmit", "field": "continue", "variant": "false"},
    {"event": "UserPromptSubmit", "field": "stopReason", "variant": None},
    {"event": "UserPromptSubmit", "field": "suppressOutput", "variant": None},
    {"event": "UserPromptSubmit", "field": "systemMessage", "variant": None},
    {"event": "UserPromptSubmit", "field": "terminalSequence", "variant": None},
    # MessageDisplay — display-content
    {"event": "MessageDisplay", "field": "hookSpecificOutput.displayContent", "variant": None},
]


@dataclass(frozen=True, slots=True)
class FieldResult:
    event: str
    field: str
    variant: str | None
    result: str  # PASS | FAIL | UNOBSERVABLE | NOT_TESTED
    assertion: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class OutputCoverageReport:
    cc_version: str
    validated_at: str | None
    rows: tuple[FieldResult, ...]
    passed: int
    failed: int
    unobservable: int
    not_tested: int


def build_output_report(
    manifest_path: str | Path,
    ir_field_inventory: list[dict] = FIELD_INVENTORY,
) -> OutputCoverageReport:
    """Read ``manifest_path`` and assemble the output coverage report model."""
    manifest_path = Path(manifest_path)

    index: dict[tuple[str, str, str | None], dict] = {}
    cc_version = "unknown"
    validated_at: str | None = None

    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        cc_version = data.get("cc_version", "unknown")
        validated_at = data.get("validated_at")
        for row in data.get("results", []):
            key = (row.get("event", ""), row.get("field", ""), row.get("variant"))
            index[key] = row

    rows: list[FieldResult] = []
    tally = {PASS: 0, FAIL: 0, UNOBSERVABLE: 0, NOT_TESTED: 0}
    for entry in ir_field_inventory:
        event = entry["event"]
        field = entry["field"]
        variant = entry.get("variant")
        key = (event, field, variant)
        manifest_row = index.get(key)
        if manifest_row is not None:
            result = manifest_row.get("result", NOT_TESTED)
        else:
            result = NOT_TESTED
        rows.append(
            FieldResult(
                event=event,
                field=field,
                variant=variant,
                result=result,
                assertion=manifest_row.get("assertion") if manifest_row else None,
                note=manifest_row.get("note") if manifest_row else None,
            )
        )
        tally[result] = tally.get(result, 0) + 1

    return OutputCoverageReport(
        cc_version=cc_version,
        validated_at=validated_at,
        rows=tuple(rows),
        passed=tally[PASS],
        failed=tally[FAIL],
        unobservable=tally[UNOBSERVABLE],
        not_tested=tally[NOT_TESTED],
    )
