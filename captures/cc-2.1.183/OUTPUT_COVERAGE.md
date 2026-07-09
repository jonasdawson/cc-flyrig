# Output Contract Coverage — cc-2.1.183

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

Validated: 2026-06-20T14:51:40.767641+00:00

## Summary

| Result | Count |
| --- | --- |
| pass | 21 |
| fail | 0 |
| unobservable | 19 |
| not-tested | 0 |

## Field results

| Event | Field | Variant | Result | Note |
| --- | --- | --- | --- | --- |
| PreToolUse | hookSpecificOutput.permissionDecision | deny | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | allow | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | ask | pass |  |
| PreToolUse | hookSpecificOutput.permissionDecision | defer | unobservable | Behaviorally indistinguishable from allow in TUI session; no external signal |
| PreToolUse | hookSpecificOutput.permissionDecisionReason | — | unobservable | no trigger mechanism available in standard TUI drive; field not yet validated |
| PreToolUse | hookSpecificOutput.updatedInput | — | pass |  |
| PreToolUse | hookSpecificOutput.additionalContext | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.behavior | deny | pass |  |
| PermissionRequest | hookSpecificOutput.decision.behavior | allow | pass |  |
| PermissionRequest | hookSpecificOutput.decision.updatedInput | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.updatedPermissions | — | unobservable | permission grant; no external signal observable from outside CC |
| PermissionRequest | hookSpecificOutput.decision.message | — | pass |  |
| PermissionRequest | hookSpecificOutput.decision.interrupt | — | pass |  |
| PermissionDenied | hookSpecificOutput.retry | true | unobservable | CC 2.1.183 + Sonnet 4.x refuses in-context before calling any tool; auto-mode classifier never reached; PermissionDenied does not fire |
| PermissionDenied | hookSpecificOutput.retry | false | pass |  |
| Elicitation | hookSpecificOutput.action | accept | pass |  |
| Elicitation | hookSpecificOutput.action | decline | pass |  |
| Elicitation | hookSpecificOutput.action | cancel | unobservable | cancel action not triggered by elicit-probe MCP server; scenario not yet written |
| Elicitation | hookSpecificOutput.content | — | pass |  |
| WorktreeCreate | stdout-bare-path | — | unobservable | requires git_repo env plugin; also tested as 'stdout bare path' in worktreecreate-stdout-path; FIELD_INVENTORY key uses hyphen |
| WorktreeCreate | hookSpecificOutput.worktreePath | — | unobservable | HTTP hook contract only; command hook does not carry this field |
| UserPromptSubmit | decision | block | pass | tested in userpromptsub-block as 'hookSpecificOutput.decision'; FIELD_INVENTORY key is 'decision' |
| UserPromptSubmit | reason | — | pass |  |
| UserPromptSubmit | hookSpecificOutput.sessionTitle | — | unobservable | no scenario; no external signal observable from pane |
| PostToolUse | decision | block | pass | tested in posttooluse-block as 'hookSpecificOutput.decision' (pane-contains 'Blocked by hook'); FIELD_INVENTORY key is 'decision' |
| PostToolUse | hookSpecificOutput.additionalContext | — | unobservable | same finding as PreToolUse additionalContext; model may receive context without echoing verbatim |
| PostToolUse | hookSpecificOutput.updatedToolOutput | — | unobservable |  |
| PostToolUse | hookSpecificOutput.updatedMCPToolOutput | — | unobservable | MCP-specific; not exercisable via built-in tool scenarios |
| SessionStart | hookSpecificOutput.additionalContext | — | unobservable | same finding as PreToolUse additionalContext; model may receive context without echoing verbatim |
| SessionStart | hookSpecificOutput.initialUserMessage | — | unobservable | applies in -p mode only; incompatible with tmux TUI drive |
| SessionStart | hookSpecificOutput.sessionTitle | — | unobservable | no scenario; no external signal observable from pane |
| SessionStart | hookSpecificOutput.watchPaths | — | pass |  |
| SessionStart | hookSpecificOutput.reloadSkills | — | unobservable | no external signal |
| TaskCreated | exit-code-2 | — | unobservable | requires agent-teams env (P2); also tested as 'exit code 2' in taskcreated-exitcode2; FIELD_INVENTORY key uses hyphens |
| UserPromptSubmit | continue | false | pass | tested in commonoutput-continue-false as 'CommonOutput.continue' (spool-present, pass); FIELD_INVENTORY key is 'continue' |
| UserPromptSubmit | stopReason | — | pass |  |
| UserPromptSubmit | suppressOutput | — | unobservable | suppresses hook's own stdout from CC transcript; no external signal |
| UserPromptSubmit | systemMessage | — | pass |  |
| UserPromptSubmit | terminalSequence | — | unobservable | tmux strips OSC control sequences from capture-pane output; classify unobservable if canary absent |
| MessageDisplay | hookSpecificOutput.displayContent | — | unobservable | none pattern: CC ignores hook output and exit code entirely for MessageDisplay |
