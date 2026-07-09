# Output Contract Coverage — cc-2.1.198

> **Validation limit.** Validation is by behavioral effect, not by shape-completeness: CC accepting
> a field is observed only through its downstream effect (tool blocked, input modified, etc.). A
> `pass` means the expected effect was observed; it does not mean CC parsed or stored every field
> correctly.

> **Model-observed fields** (require a follow-up turn): CC never echoes back what it accepted
> internally, so these fields are validated indirectly — a hook emits a unique canary string, and
> a follow-up prompt checks whether the model reproduces it. Classified `unobservable` if the
> canary was absent from the model's response.

> **Structurally unobservable fields**: unreachable from outside CC (MCP-specific wire, HTTP-only
> contract, `-p` mode only, or no external signal). Classified `unobservable` without testing.

> **`none`-pattern events**: CC ignores hook output and exit code entirely for these events.
> All fields are `unobservable` by pattern.

Validated: 2026-07-04T01:43:03.249175+00:00

## Summary

| Result | Count |
| --- | --- |
| pass | 18 |
| fail | 0 |
| unobservable | 3 |
| not-tested | 19 |

## Field results

| Event | Field | Variant | Result | Note |
| --- | --- | --- | --- | --- |
| PreToolUse | hookSpecificOutput.permissionDecision | deny | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | allow | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | ask | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | defer | not-tested |  |
| PreToolUse | hookSpecificOutput.permissionDecisionReason | — | not-tested |  |
| PreToolUse | hookSpecificOutput.updatedInput | — | pass |  |
| PreToolUse | hookSpecificOutput.additionalContext | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.behavior | deny | pass |  |
| PermissionRequest | hookSpecificOutput.decision.behavior | allow | pass |  |
| PermissionRequest | hookSpecificOutput.decision.updatedInput | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.updatedPermissions | — | not-tested |  |
| PermissionRequest | hookSpecificOutput.decision.message | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.interrupt | — | pass |  |
| PermissionDenied | hookSpecificOutput.retry | true | unobservable | CC 2.1.183 + Sonnet 4.x refuses in-context before calling any tool; auto-mode classifier never reached; PermissionDenied does not fire |
| PermissionDenied | hookSpecificOutput.retry | false | pass |  |
| Elicitation | hookSpecificOutput.action | accept | pass |  |
| Elicitation | hookSpecificOutput.action | decline | pass |  |
| Elicitation | hookSpecificOutput.action | cancel | not-tested |  |
| Elicitation | hookSpecificOutput.content | — | pass |  |
| WorktreeCreate | stdout-bare-path | — | not-tested |  |
| WorktreeCreate | hookSpecificOutput.worktreePath | — | not-tested |  |
| UserPromptSubmit | decision | block | not-tested |  |
| UserPromptSubmit | reason | — | pass |  |
| UserPromptSubmit | hookSpecificOutput.sessionTitle | — | not-tested |  |
| PostToolUse | decision | block | not-tested |  |
| PostToolUse | hookSpecificOutput.additionalContext | — | not-tested |  |
| PostToolUse | hookSpecificOutput.updatedToolOutput | — | unobservable |  |
| PostToolUse | hookSpecificOutput.updatedMCPToolOutput | — | not-tested |  |
| SessionStart | hookSpecificOutput.additionalContext | — | not-tested |  |
| SessionStart | hookSpecificOutput.initialUserMessage | — | not-tested |  |
| SessionStart | hookSpecificOutput.sessionTitle | — | not-tested |  |
| SessionStart | hookSpecificOutput.watchPaths | — | pass |  |
| SessionStart | hookSpecificOutput.reloadSkills | — | not-tested |  |
| TaskCreated | exit-code-2 | — | not-tested |  |
| UserPromptSubmit | continue | false | not-tested |  |
| UserPromptSubmit | stopReason | — | pass |  |
| UserPromptSubmit | suppressOutput | — | not-tested |  |
| UserPromptSubmit | systemMessage | — | pass |  |
| UserPromptSubmit | terminalSequence | — | unobservable | tmux strips OSC control sequences from capture-pane output; classify unobservable if canary absent |
| MessageDisplay | hookSpecificOutput.displayContent | — | not-tested |  |
