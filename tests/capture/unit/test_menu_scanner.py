"""Tests for the /hooks menu scanner (capture.orchestrator.menu_scanner).

The parse helpers run against captured-pane text (no tmux); ``scan_hooks_menu`` runs against a fake
``Tmux`` driven by canned panes so the two-pass navigation is exercised without claude/tmux.
"""

from cc_flyrig.capture.orchestrator import menu_scanner
from cc_flyrig.cli.tmux import Tmux

# A real detail body shape observed in the Group 1 spike (PostToolUseFailure).
_DETAIL_FAILURE = """\
  PostToolUseFailure - Matchers
  Input to command is JSON with tool_name, tool_input, tool_use_id, error,
  error_type, is_interrupt, and is_timeout.
  Exit code 0 - stdout shown in transcript mode (ctrl+o)
  Exit code 2 - show stderr to model immediately
  Other exit codes - show stderr to user only

  No hooks configured for this event
  To add hooks, edit settings.json directly or ask Claude"""

_DETAIL_ELICITATION = """\
  Elicitation - Matchers
  Input to command is JSON with mcp_server_name, message, and
  requested_schema.
  Output JSON with hookSpecificOutput containing action
  (accept/decline/cancel) and optional content.
  Exit code 0 - use hook response if provided
  Exit code 2 - deny the elicitation
  Other exit codes - show stderr to user only"""

_DETAIL_PRETOOLUSE = """\
  PreToolUse - Matchers
  Input to command is JSON of tool call arguments.
  Exit code 0 - stdout/stderr not shown
  Exit code 2 - show stderr to model and block tool call
  Other exit codes - show stderr to user only but continue with tool call"""


class TestParseDetail:
    def test_parse_detail__entry_with_fields__extracts_input_note_and_exit_codes(self):
        parsed = menu_scanner._parse_detail(_DETAIL_FAILURE)
        assert parsed["input_note"].startswith("Input to command is JSON with tool_name")
        assert "is_timeout" in parsed["input_note"]  # wrapped continuation joined
        assert parsed["output_note"] == ""
        assert "Exit code 0 - stdout shown in transcript mode (ctrl+o)" in parsed["exit_codes"]
        assert "Other exit codes - show stderr to user only" in parsed["exit_codes"]

    def test_parse_detail__entry_with_output__captures_output_note(self):
        parsed = menu_scanner._parse_detail(_DETAIL_ELICITATION)
        assert "hookSpecificOutput containing action" in parsed["output_note"]
        assert "requested_schema" in parsed["input_note"]

    def test_parse_detail__boilerplate_lines__excluded(self):
        parsed = menu_scanner._parse_detail(_DETAIL_FAILURE)
        assert "No hooks configured" not in parsed["input_note"]
        assert "To add hooks" not in parsed["exit_codes"]


class TestFieldNames:
    def test_field_names__comma_listed_snake_case__all_extracted(self):
        note = "Input to command is JSON with tool_name, tool_input, tool_use_id, and reason."
        assert menu_scanner._field_names(note) == ["tool_name", "tool_input", "tool_use_id"]

    def test_field_names__camel_case__extracted(self):
        note = "Output JSON with hookSpecificOutput containing action and optional content."
        assert "hookSpecificOutput" in menu_scanner._field_names(note)

    def test_field_names__prose_only__yields_nothing(self):
        # PreToolUse's note names no identifiers, only prose.
        assert menu_scanner._field_names("Input to command is JSON of tool call arguments.") == []

    def test_field_names__parenthetical_enum_values__excluded(self):
        # The parenthesised enum values must not be extracted; the bare word "source" is also dropped
        # (single lowercase words are indistinguishable from prose — conservative by design).
        note = "Input to command is JSON with source (user_settings, project_settings) and file_path."
        assert menu_scanner._field_names(note) == ["file_path"]

    def test_field_names__dotted_path__reduced_to_root(self):
        # Nested keys are not top-level props: keep only the root segment.
        assert menu_scanner._field_names("can include hookSpecificOutput.watchPaths") == ["hookSpecificOutput"]

    def test_field_names__inline_json_example__nested_keys_dropped(self):
        # A `Return {...}` example illustrates output; its nested keys are not field declarations.
        note = 'Return {"hookSpecificOutput":{"hookEventName":"PermissionDenied","retry":true}} to retry.'
        assert menu_scanner._field_names(note) == []


_DETAIL_PERMISSION_DENIED = """\
  PermissionDenied - Matchers
  Input to command is JSON with tool_name, tool_input, tool_use_id, and
  reason.
  Return
  {"hookSpecificOutput":{"hookEventName":"PermissionDenied","retry":true}} to
  tell the model it may retry.
  Exit code 0 - stdout shown in transcript mode (ctrl+o)
  Other exit codes - show stderr to user only"""


class TestParseDetailReturnExample:
    def test_parse_detail__return_on_own_line__bucketed_as_output_not_input(self):
        parsed = menu_scanner._parse_detail(_DETAIL_PERMISSION_DENIED)
        assert "hookSpecificOutput" not in parsed["input_note"]  # the Return example must not leak to input
        assert parsed["output_note"].startswith("Return")
        # The JSON example's nested keys are not extracted as fields on either side.
        assert menu_scanner._field_names(parsed["input_note"]) == ["tool_name", "tool_input", "tool_use_id"]
        assert menu_scanner._field_names(parsed["output_note"]) == []


class TestListRows:
    def test_list_rows__focus_and_scroll_markers__parsed(self):
        pane = (
            "  Hooks\n"
            "  ❯ 1.  PreToolUse           Before tool execution\n"
            "    2.  PostToolUse          After tool execution\n"
            "  ↓ 3.  PostToolUseFailure   After tool execution fails\n"
            "  Enter to confirm · Esc to cancel\n"
        )
        rows = menu_scanner._list_rows(pane)
        assert [r["name"] for r in rows] == ["PreToolUse", "PostToolUse", "PostToolUseFailure"]
        assert menu_scanner._focused_row(pane)["name"] == "PreToolUse"


# --- scan_hooks_menu against a fake Tmux ---------------------------------------------------------

_RULE = "─" * 40


def _list_pane(focus_num: int, rows: list[tuple[int, str, str]]) -> str:
    lines = ["  Hooks", _RULE]
    for num, name, desc in rows:
        marker = "❯" if num == focus_num else " "
        lines.append(f"  {marker} {num}.  {name}    {desc}")
    lines.append("  Enter to confirm · Esc to cancel")
    return "\n".join(lines)


def _detail_pane(body: str) -> str:
    return "\n".join(["  Detail", _RULE, body, "", "  Esc to go back"])


class _FakeTmux(Tmux):
    """A scripted Tmux: navigation mutates an index; capture_pane renders the current screen."""

    def __init__(self, rows: list[tuple[int, str, str]], bodies: dict[int, str]) -> None:
        super().__init__(runner=lambda argv: None)  # runner never used
        self._rows = rows
        self._bodies = bodies
        self._focus = 1
        self._screen = "ready"  # ready (prompt) | list | detail
        self._pending = ""

    def new_session(self, name, cwd, command, env=None) -> None:
        self._screen = "ready"

    def has_session(self, name) -> bool:
        return self._screen != "dead"

    def send_text(self, name, text) -> None:
        self._pending = text  # typed into the prompt, not yet submitted

    def send_key(self, name, key) -> None:
        if key == "Enter" and self._screen == "ready" and self._pending == "/hooks":
            self._screen = "list"  # /hooks submitted → menu opens at the top
            self._focus = 1
        elif key == "Enter" and self._screen == "list":
            self._screen = "detail"  # confirm focused entry → detail view
        elif key == "Down" and self._screen == "list":
            self._focus = self._focus % len(self._rows) + 1  # wraps
        elif key == "Escape" and self._screen == "detail":
            self._screen = "list"
            self._focus = 1  # menu resets focus to top on Esc-from-detail
        elif key == "Escape" and self._screen == "list":
            self._screen = "ready"  # Esc closes the menu back to the prompt

    def capture_pane(self, name) -> str:
        if self._screen == "ready":
            return "  ? for shortcuts"
        if self._screen == "detail":
            return _detail_pane(self._bodies[self._focus])
        return _list_pane(self._focus, self._rows)

    def kill_session(self, name) -> None:
        self._screen = "dead"


class TestScanHooksMenu:
    def test_scan_hooks_menu__three_entries__parses_in_order(self, tmp_path):
        rows = [
            (1, "PreToolUse", "Before tool execution"),
            (2, "PostToolUseFailure", "After tool execution fails"),
            (3, "Elicitation", "When an MCP server requests user input"),
        ]
        bodies = {1: _DETAIL_PRETOOLUSE, 2: _DETAIL_FAILURE, 3: _DETAIL_ELICITATION}
        fake = _FakeTmux(rows, bodies)
        ticks = iter(range(10_000))  # advancing clock so any unmet wait times out instead of hanging

        entries, raw = menu_scanner.scan_hooks_menu(
            claude_bin="claude", sandbox_root=tmp_path, tmux=fake, sleep=lambda s: None, clock=lambda: next(ticks)
        )

        assert [e["event"] for e in entries] == ["PreToolUse", "PostToolUseFailure", "Elicitation"]
        failure = entries[1]
        assert failure["description"] == "After tool execution fails"
        assert "tool_name" in failure["input_fields"]
        assert "Exit code 2 - show stderr to model immediately" in failure["exit_codes"]
        assert entries[2]["output_fields"]  # Elicitation has an output note with hookSpecificOutput
        assert "### Elicitation" in raw
