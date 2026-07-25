# Capture coverage — cc-2.1.220

Captured at: 2026-07-25T14:57:21.381970+00:00

Observed 29/31 events · 2 expected-but-missing · 0 not-attempted.

> ⚠️ Some events the battery expected were not captured — see **expected-but-missing** below.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 33 | launch-flag, promptable |
| Setup | observed | 1 | launch-flag |
| InstructionsLoaded | observed | 1 | side-effect |
| UserPromptSubmit | observed | 31 | promptable |
| UserPromptExpansion | observed | 1 | side-effect |
| MessageDisplay | observed | 54 | interactive |
| PreToolUse | observed | 36 | failure-induced, interactive, promptable |
| PermissionRequest | observed | 1 | interactive |
| PostToolUse | observed | 35 | interactive, promptable |
| PostToolUseFailure | observed | 1 | failure-induced |
| PostToolBatch | observed | 33 | promptable |
| PermissionDenied | expected-but-missing | 0 | promptable |
| Notification | observed | 6 | interactive |
| SubagentStart | observed | 4 | promptable, side-effect |
| SubagentStop | observed | 10 | promptable, side-effect |
| TaskCreated | observed | 1 | promptable |
| TaskCompleted | observed | 1 | promptable |
| Stop | observed | 29 | promptable |
| StopFailure | observed | 1 | failure-induced |
| TeammateIdle | observed | 2 | promptable |
| ConfigChange | observed | 1 | side-effect |
| CwdChanged | observed | 1 | promptable |
| FileChanged | observed | 1 | side-effect |
| WorktreeCreate | observed | 1 | side-effect |
| WorktreeRemove | expected-but-missing | 0 | interactive |
| PreCompact | observed | 2 | interactive, side-effect |
| PostCompact | observed | 1 | interactive, side-effect |
| SessionEnd | observed | 32 | promptable |
| Elicitation | observed | 1 | interactive |
| ElicitationResult | observed | 1 | interactive |
| DirectoryAdded | observed | 1 | side-effect |

## Tools observed (tool-bearing events)

| Event | Tools seen |
| --- | --- |
| PermissionDenied | — |
| PermissionRequest | Write |
| PostToolBatch | Agent, Bash, Edit, Read, TaskCreate, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, Bash, Edit, Read, TaskCreate, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Read |
| PreToolUse | Agent, Bash, Edit, Read, TaskCreate, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
