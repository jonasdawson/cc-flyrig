# Capture coverage — cc-2.1.168

Captured at: 2026-06-08T08:38:17.856272+00:00

Observed 29/30 events · 1 reference-only · 0 expected-but-missing · 0 not-attempted.

## Events

| Event | Status | Payloads | Capture method |
| --- | --- | ---: | --- |
| SessionStart | observed | 168 | — |
| Setup | observed | 6 | — |
| InstructionsLoaded | observed | 8 | — |
| UserPromptSubmit | observed | 160 | — |
| UserPromptExpansion | observed | 6 | — |
| MessageDisplay | observed | 246 | — |
| PreToolUse | observed | 191 | — |
| PermissionRequest | observed | 6 | — |
| PostToolUse | observed | 176 | — |
| PostToolUseFailure | observed | 14 | — |
| PostToolBatch | observed | 180 | — |
| PermissionDenied | observed | 1 | — |
| Notification | observed | 24 | — |
| SubagentStart | observed | 10 | — |
| SubagentStop | observed | 40 | — |
| TaskCreated | observed | 1 | — |
| TaskCompleted | observed | 1 | — |
| Stop | observed | 149 | — |
| StopFailure | observed | 2 | — |
| TeammateIdle | observed | 3 | — |
| ConfigChange | observed | 6 | — |
| CwdChanged | observed | 5 | — |
| FileChanged | observed | 3 | — |
| WorktreeCreate | observed | 2 | — |
| WorktreeRemove | reference-only | 0 | interactive |
| PreCompact | observed | 9 | — |
| PostCompact | observed | 3 | — |
| SessionEnd | observed | 163 | — |
| Elicitation | observed | 2 | — |
| ElicitationResult | observed | 2 | — |

## Tools observed (tool-bearing events)

| Event | Tools seen |
| --- | --- |
| PermissionDenied | Bash |
| PermissionRequest | Write |
| PostToolBatch | Agent, Bash, Edit, Read, SendMessage, Skill, TaskCreate, TaskGet, TaskUpdate, TeamCreate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUse | Agent, Bash, Edit, Read, SendMessage, Skill, TaskCreate, TaskGet, TaskUpdate, TeamCreate, ToolSearch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
| PostToolUseFailure | Bash, Edit, Read, WebFetch |
| PreToolUse | Agent, Bash, Edit, Read, SendMessage, Skill, TaskCreate, TaskGet, TaskUpdate, TeamCreate, ToolSearch, WebFetch, WebSearch, Write, mcp__elicit-probe__probe_elicit |
