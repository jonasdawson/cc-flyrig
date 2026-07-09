# Capture coverage — cc-2.1.200

Captured at: 2026-07-03T22:33:21.103277+00:00

Observed 27/30 events · 3 expected-but-missing · 0 not-attempted.

> ⚠️ Some events the battery expected were not captured — see **expected-but-missing** below.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 62 | launch-flag, promptable |
| Setup | observed | 2 | launch-flag |
| InstructionsLoaded | observed | 2 | side-effect |
| UserPromptSubmit | observed | 61 | promptable |
| UserPromptExpansion | observed | 2 | side-effect |
| MessageDisplay | observed | 106 | interactive |
| PreToolUse | observed | 89 | failure-induced, interactive, promptable |
| PermissionRequest | observed | 3 | interactive |
| PostToolUse | observed | 87 | interactive, promptable |
| PostToolUseFailure | observed | 2 | failure-induced |
| PostToolBatch | observed | 84 | promptable |
| PermissionDenied | expected-but-missing | 0 | promptable |
| Notification | observed | 10 | interactive |
| SubagentStart | observed | 9 | promptable, side-effect |
| SubagentStop | observed | 25 | promptable, side-effect |
| TaskCreated | observed | 2 | promptable |
| TaskCompleted | observed | 2 | promptable |
| Stop | observed | 62 | promptable |
| StopFailure | expected-but-missing | 0 | failure-induced |
| TeammateIdle | observed | 4 | promptable |
| ConfigChange | observed | 2 | side-effect |
| CwdChanged | observed | 2 | promptable |
| FileChanged | observed | 2 | side-effect |
| WorktreeCreate | observed | 2 | side-effect |
| WorktreeRemove | expected-but-missing | 0 | interactive |
| PreCompact | observed | 4 | interactive, side-effect |
| PostCompact | observed | 2 | interactive, side-effect |
| SessionEnd | observed | 60 | promptable |
| Elicitation | observed | 2 | interactive |
| ElicitationResult | observed | 2 | interactive |

## Tools observed (tool-bearing events)

| Event | Tools seen |
| --- | --- |
| PermissionDenied | — |
| PermissionRequest | AskUserQuestion, Write |
| PostToolBatch | Agent, AskUserQuestion, Bash, Edit, Read, ScheduleWakeup, SendMessage, TaskCreate, TaskGet, TaskList, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, AskUserQuestion, Bash, Edit, Read, ScheduleWakeup, SendMessage, TaskCreate, TaskGet, TaskList, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Read |
| PreToolUse | Agent, AskUserQuestion, Bash, Edit, Read, ScheduleWakeup, SendMessage, TaskCreate, TaskGet, TaskList, TaskUpdate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
