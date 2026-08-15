# Capture coverage — cc-2.1.233

Captured at: 2026-08-15T15:12:59.677354+00:00

Observed 27/31 events · 4 expected-but-missing · 0 not-attempted.

> ⚠️ Some events the battery expected were not captured — see **expected-but-missing** below.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 33 | launch-flag, promptable |
| Setup | observed | 1 | launch-flag |
| InstructionsLoaded | observed | 1 | side-effect |
| UserPromptSubmit | observed | 32 | promptable |
| UserPromptExpansion | observed | 1 | side-effect |
| MessageDisplay | observed | 51 | interactive |
| PreToolUse | observed | 37 | failure-induced, interactive, promptable |
| PermissionRequest | observed | 1 | interactive |
| PostToolUse | observed | 35 | interactive, promptable |
| PostToolUseFailure | observed | 2 | failure-induced |
| PostToolBatch | observed | 35 | promptable |
| PermissionDenied | expected-but-missing | 0 | promptable |
| Notification | observed | 6 | interactive |
| SubagentStart | observed | 3 | promptable, side-effect |
| SubagentStop | observed | 13 | promptable, side-effect |
| TaskCreated | expected-but-missing | 0 | promptable |
| TaskCompleted | expected-but-missing | 0 | promptable |
| Stop | observed | 32 | promptable |
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
| PostToolBatch | Agent, Bash, Edit, Read, SendMessage, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, Bash, Edit, Read, SendMessage, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Agent, Read |
| PreToolUse | Agent, Bash, Edit, Read, SendMessage, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
