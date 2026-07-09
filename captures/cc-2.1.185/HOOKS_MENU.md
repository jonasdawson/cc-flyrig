# `/hooks` Menu — cc-2.1.185

> **What this is.** The Claude Code `/hooks` TUI menu, scraped from the running binary. MENU is
> **roster-authoritative** (its event set is the binary's own enumeration), a **cross-check** for
> field names and exit codes, and **doc-informal** otherwise. The notes below are scraped help text,
> not the contract authority — the IR (typed JSON Schema) remains authoritative for shapes. Menu
> prose is never machine-merged; it is promoted to IR `x-` annotations only by maintainer judgment.

## Roster

Documented 30/30 — **matches the IR roster.**

## Cross-check (advisory)

Field names documented by `/hooks` but absent from the IR — review; advisory only, never gates CI:

| Event | Finding |
| --- | --- |
| PostToolBatch | output field 'additionalContext' documented by /hooks, absent from IR |
| PermissionRequest | input field 'tool_use_id' documented by /hooks, absent from IR |
| MessageDisplay | output field 'displayContent' documented by /hooks, absent from IR |

## Entries

| Event | Description | Exit codes | Input note | Output note |
| --- | --- | --- | --- | --- |
| PreToolUse | Before tool execution | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to model and block tool call; Other exit codes - show stderr to user only but continue with tool call | Input to command is JSON of tool call arguments. |  |
| PostToolUse | After tool execution | Exit code 0 - stdout shown in transcript mode (ctrl+o); Exit code 2 - show stderr to model immediately; Other exit codes - show stderr to user only | Input to command is JSON with fields "inputs" (tool call arguments) and "response" (tool call response). |  |
| PostToolUseFailure | After tool execution fails | Exit code 0 - stdout shown in transcript mode (ctrl+o); Exit code 2 - show stderr to model immediately; Other exit codes - show stderr to user only | Input to command is JSON with tool_name, tool_input, tool_use_id, error, error_type, is_interrupt, and is_timeout. |  |
| PostToolBatch | After a batch of tool calls resolves | Exit code 2 - stop the agentic loop (stderr shown to user only); Other exit codes - show stderr to user only |  | Return additionalContext via hookSpecificOutput to inject context once for the whole batch. |
| PermissionDenied | After auto mode classifier denies a tool call | Exit code 0 - stdout shown in transcript mode (ctrl+o); Other exit codes - show stderr to user only | Input to command is JSON with tool_name, tool_input, tool_use_id, and reason. | Return {"hookSpecificOutput":{"hookEventName":"PermissionDenied","retry":true}} to tell the model it may retry. |
| Notification | When notifications are sent | Exit code 0 - stdout/stderr not shown; Other exit codes - show stderr to user only | Input to command is JSON with notification message and type. |  |
| UserPromptSubmit | When the user submits a prompt | Exit code 0 - stdout shown to Claude; Exit code 2 - block processing, erase original prompt, and show stderr to; Other exit codes - show stderr to user only | Input to command is JSON with original user prompt text. |  |
| UserPromptExpansion | When a user-typed slash command expands into a | Exit code 0 - stdout shown to Claude; Exit code 2 - block expansion and show stderr to user only; Other exit codes - show stderr to user only | Input to command is JSON with expansion_type, command_name, command_args, command_source, and original prompt. |  |
| SessionStart | When a new session is started | Exit code 0 - stdout shown to Claude; Blocking errors are ignored; Other exit codes - show stderr to user only | Input to command is JSON with session start source. |  |
| Stop | Right before Claude concludes its response | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to model and continue conversation; Other exit codes - show stderr to user only |  |  |
| StopFailure | When the turn ends due to an API error |  |  |  |
| SubagentStart | When a subagent (Agent tool call) is started | Exit code 0 - stdout shown to subagent; Blocking errors are ignored; Other exit codes - show stderr to user only | Input to command is JSON with agent_id and agent_type. |  |
| SubagentStop | Right before a subagent (Agent tool call) | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to subagent and continue having it run; Other exit codes - show stderr to user only | Input to command is JSON with agent_id, agent_type, and agent_transcript_path. |  |
| PreCompact | Before conversation compaction | Exit code 0 - stdout appended as custom compact instructions; Exit code 2 - block compaction; Other exit codes - show stderr to user only but continue with compaction | Input to command is JSON with compaction details. |  |
| PostCompact | After conversation compaction | Exit code 0 - stdout shown to user; Other exit codes - show stderr to user only | Input to command is JSON with compaction details and the summary. |  |
| SessionEnd | When a session is ending | Exit code 0 - command completes successfully; Other exit codes - show stderr to user only | Input to command is JSON with session end reason. |  |
| PermissionRequest | When a permission dialog is displayed | Exit code 0 - use hook decision if provided; Other exit codes - show stderr to user only | Input to command is JSON with tool_name, tool_input, and tool_use_id. | Output JSON with hookSpecificOutput containing decision to allow or deny. |
| Setup | Repo setup hooks for init and maintenance | Exit code 0 - stdout shown to Claude; Blocking errors are ignored; Other exit codes - show stderr to user only | Input to command is JSON with trigger (init or maintenance). |  |
| TeammateIdle | When a teammate is about to go idle | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to teammate and prevent idle (teammate continues; Other exit codes - show stderr to user only | Input to command is JSON with teammate_name and team_name. |  |
| TaskCreated | When a task is being created | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to model and prevent task creation; Other exit codes - show stderr to user only | Input to command is JSON with task_id, task_subject, task_description, teammate_name, and team_name. |  |
| TaskCompleted | When a task is being marked as completed | Exit code 0 - stdout/stderr not shown; Exit code 2 - show stderr to model and prevent task completion; Other exit codes - show stderr to user only | Input to command is JSON with task_id, task_subject, task_description, teammate_name, and team_name. |  |
| Elicitation | When an MCP server requests user input | Exit code 0 - use hook response if provided; Exit code 2 - deny the elicitation; Other exit codes - show stderr to user only | Input to command is JSON with mcp_server_name, message, and requested_schema. | Output JSON with hookSpecificOutput containing action (accept/decline/cancel) and optional content. |
| ElicitationResult | After a user responds to an MCP elicitation | Exit code 0 - use hook response if provided; Exit code 2 - block the response (action becomes decline); Other exit codes - show stderr to user only | Input to command is JSON with mcp_server_name, action, content, mode, and elicitation_id. | Output JSON with hookSpecificOutput containing optional action and content to override the response. |
| ConfigChange | When configuration files change during a session | Exit code 0 - allow the change; Exit code 2 - block the change from being applied to the session; Other exit codes - show stderr to user only | Input to command is JSON with source (user_settings, project_settings, local_settings, policy_settings, skills) and file_path. |  |
| InstructionsLoaded | When an instruction file (CLAUDE.md or rule) is | Exit code 0 - command completes successfully; Other exit codes - show stderr to user only | Input to command is JSON with file_path, memory_type (User, Project, Local, Managed), load_reason (session_start, nested_traversal, path_glob_match, include, compact), globs (optional — the paths: frontmatter patterns that matched), trigger_file_path (optional — the file Claude touched that caused the load), and parent_file_path (optional — the file that @-included this one). |  |
| WorktreeCreate | Create an isolated worktree for VCS-agnostic | Exit code 0 - worktree created successfully; Other exit codes - worktree creation failed | Input to command is JSON with name (suggested worktree slug). Stdout should contain the absolute path to the created worktree directory. |  |
| WorktreeRemove | Remove a previously created worktree | Exit code 0 - worktree removed successfully; Other exit codes - show stderr to user only | Input to command is JSON with worktree_path (absolute path to worktree). |  |
| CwdChanged | After the working directory changes | Exit code 0 - command completes successfully; Other exit codes - show stderr to user only | Input to command is JSON with old_cwd and new_cwd. CLAUDE_ENV_FILE is set — write bash exports there to apply env to subsequent BashTool commands. | Hook output can include hookSpecificOutput.watchPaths (array of absolute paths) to register with the FileChanged watcher. |
| FileChanged | When a watched file changes | Exit code 0 - command completes successfully; Other exit codes - show stderr to user only | Input to command is JSON with file_path and event (change, add, unlink). CLAUDE_ENV_FILE is set — write bash exports there to apply env to subsequent BashTool commands. The matcher field specifies filenames to watch in the current directory (e.g. ".envrc|.env"). | Hook output can include hookSpecificOutput.watchPaths (array of absolute paths) to dynamically update the watch list. |
| MessageDisplay | While assistant message text is displayed | Exit code 0 - use hook response if provided; Other exit codes - display the original delta | Input to command is JSON with turn_id, message_id, index, final, and delta (the newly completed lines). | Output JSON with hookSpecificOutput containing displayContent to replace the delta on screen. Display-only: the stored message and what the model sees are untouched. |
