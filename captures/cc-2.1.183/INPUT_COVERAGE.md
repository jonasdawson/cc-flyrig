# Capture coverage — cc-2.1.183

Captured at: 2026-06-19T22:09:40.653818+00:00

Observed 29/30 events · 0 expected-but-missing · 1 not-attempted.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 32 | promptable |
| Setup | observed | 1 | — |
| InstructionsLoaded | observed | 1 | — |
| UserPromptSubmit | observed | 32 | promptable |
| UserPromptExpansion | observed | 1 | — |
| MessageDisplay | observed | 52 | — |
| PreToolUse | observed | 40 | — |
| PermissionRequest | observed | 1 | — |
| PostToolUse | observed | 38 | — |
| PostToolUseFailure | observed | 1 | — |
| PostToolBatch | observed | 38 | — |
| PermissionDenied | observed | 1 | — |
| Notification | observed | 4 | — |
| SubagentStart | observed | 4 | — |
| SubagentStop | observed | 7 | — |
| TaskCreated | observed | 1 | — |
| TaskCompleted | observed | 1 | — |
| Stop | observed | 27 | promptable |
| StopFailure | observed | 1 | — |
| TeammateIdle | observed | 1 | — |
| ConfigChange | observed | 3 | — |
| CwdChanged | observed | 1 | — |
| FileChanged | observed | 1 | — |
| WorktreeCreate | observed | 1 | — |
| WorktreeRemove | not-attempted | 0 | — |
| PreCompact | observed | 2 | — |
| PostCompact | observed | 1 | — |
| SessionEnd | observed | 31 | promptable |
| Elicitation | observed | 1 | — |
| ElicitationResult | observed | 1 | — |

## Tools observed (tool-bearing events)

| Event | Tools seen |
| --- | --- |
| PermissionDenied | Bash |
| PermissionRequest | Write |
| PostToolBatch | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskGet, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskGet, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Read |
| PreToolUse | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskGet, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
