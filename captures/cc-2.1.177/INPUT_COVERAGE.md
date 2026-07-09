# Capture coverage — cc-2.1.177

Captured at: 2026-06-13T13:55:39.909114+00:00

Observed 29/30 events · 1 reference-only · 0 expected-but-missing · 0 not-attempted.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 33 | launch-flag, promptable |
| Setup | observed | 1 | launch-flag |
| InstructionsLoaded | observed | 1 | side-effect |
| UserPromptSubmit | observed | 31 | promptable |
| UserPromptExpansion | observed | 1 | side-effect |
| MessageDisplay | observed | 40 | interactive |
| PreToolUse | observed | 43 | failure-induced, interactive, promptable |
| PermissionRequest | observed | 1 | interactive |
| PostToolUse | observed | 41 | interactive, promptable |
| PostToolUseFailure | observed | 1 | failure-induced |
| PostToolBatch | observed | 41 | promptable |
| PermissionDenied | observed | 1 | promptable |
| Notification | observed | 4 | interactive |
| SubagentStart | observed | 2 | promptable, side-effect |
| SubagentStop | observed | 8 | promptable, side-effect |
| TaskCreated | observed | 1 | promptable |
| TaskCompleted | observed | 1 | promptable |
| Stop | observed | 27 | promptable |
| StopFailure | observed | 1 | failure-induced |
| TeammateIdle | observed | 1 | promptable |
| ConfigChange | observed | 1 | side-effect |
| CwdChanged | observed | 1 | promptable |
| FileChanged | observed | 1 | side-effect |
| WorktreeCreate | observed | 1 | side-effect |
| WorktreeRemove | reference-only | 0 | interactive |
| PreCompact | observed | 2 | interactive, side-effect |
| PostCompact | observed | 1 | interactive, side-effect |
| SessionEnd | observed | 32 | promptable |
| Elicitation | observed | 1 | interactive |
| ElicitationResult | observed | 1 | interactive |

## Tools observed (tool-bearing events)

| Event | Tools seen |
| --- | --- |
| PermissionDenied | Bash |
| PermissionRequest | Write |
| PostToolBatch | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskUpdate, TeamCreate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskUpdate, TeamCreate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Read |
| PreToolUse | Agent, Bash, Edit, Read, SendMessage, TaskCreate, TaskUpdate, TeamCreate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
