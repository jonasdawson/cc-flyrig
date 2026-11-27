"""Tests for the /hooks menu scanner (capture.orchestrator.menu_scanner).

The parse helpers run against captured-pane text (no tmux); ``scan_hooks_menu`` runs against a fake
``Tmux`` that models the cc-2.1.332 four-screen menu (prompt → landing → list → detail), so the
two-pass, name-based navigation is exercised without claude/tmux. The fake's defaults
(``wraps=True``, ``reset_focus_on_escape=False``) are the observed 2.1.332 behavior
(see the module docstring); the other variants keep the scanner correct if a release changes them.
"""

import pytest

from cc_flyrig.capture.orchestrator import menu_scanner
from cc_flyrig.cli.tmux import Tmux

# A real detail body shape observed on PostToolUseFailure.
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


_RULE = "─" * 60
_BANNER = [" ▐▛███▜▌   Claude Code v2.1.332", "▝▜█████▛▘  Haiku 5.5 · Claude Max", "❯ /hooks", _RULE]

# A real cc-2.1.332 detail pane (200×50), banner trimmed.
_PANE_PREMODELSWITCH = "\n".join(
    [
        *_BANNER,
        "  PreModelSwitch",
        "  Input to command is JSON with from_model, to_model, requested_model, source, context_tokens and the"
        " estimated re-cache cost.",
        "  Exit code 0 - switch proceeds; JSON permissionDecision allow/deny/ask as for PreToolUse",
        "  Exit code 2 - block the switch and show stderr to user",
        "  Other exit codes - show stderr to user only and continue",
        "  No hooks for this event yet",
        "  To add hooks, edit settings.json directly or ask Claude",
        "  Esc to go back",
    ]
)


class TestParseDetailV2_1_332:
    def test_parse_detail__v2_1_332_detail_pane__notes_exit_codes_and_title(self):
        body = menu_scanner._detail_body(_PANE_PREMODELSWITCH)
        assert menu_scanner._detail_title(body) == "PreModelSwitch"
        parsed = menu_scanner._parse_detail(body)
        assert parsed["input_note"].startswith("Input to command is JSON with from_model")
        assert menu_scanner._field_names(parsed["input_note"]) == [
            "from_model",
            "to_model",
            "requested_model",
            "context_tokens",
        ]
        assert parsed["exit_codes"].splitlines() == [
            "Exit code 0 - switch proceeds; JSON permissionDecision allow/deny/ask as for PreToolUse",
            "Exit code 2 - block the switch and show stderr to user",
            "Other exit codes - show stderr to user only and continue",
        ]
        assert "No hooks for this event yet" not in parsed["exit_codes"]
        assert "Esc to go back" not in body

    def test_detail_title__older_matchers_suffix__first_token_still_matches(self):
        assert menu_scanner._title_is(_DETAIL_PRETOOLUSE, "PreToolUse")
        assert not menu_scanner._title_is(_DETAIL_PRETOOLUSE, "PostToolUse")
        assert not menu_scanner._title_is("", "PreToolUse")


# --- pane builders -------------------------------------------------------------------------------


def _landing_pane(*, focused: bool = True) -> str:
    return "\n".join(
        [
            *_BANNER,
            "  Hooks",
            "  no hooks yet",
            "  This menu is read-only. To add or change a hook, edit settings.json or ask Claude. Learn more",
            f"  {'❯' if focused else ' '} All events",
            "  Enter to view · Esc to close",
        ]
    )


def _list_pane(
    focus_name: str | None,
    rows: list[tuple[str, str]],
    total: int,
    *,
    above: int = 0,
    below: int = 0,
    cut_last_desc: bool = False,
) -> str:
    lines = [*_BANNER, "  Hook events", f"  {total} events · 0 with hooks"]
    if above:
        lines.append(f"    ↑ {above} more")
    for i, (name, desc) in enumerate(rows):
        lines.append(f"  ❯ {name}" if name == focus_name else f"    {name}")
        if not (cut_last_desc and i == len(rows) - 1):
            lines.append(f"    {desc}")
    if below:
        lines.append(f"    ↓ {below} more")
    lines.append("  ↑/↓ to navigate · Enter to open · Esc to go back")
    return "\n".join(lines)


def _detail_pane(name: str, body: str) -> str:
    return "\n".join(
        [
            *_BANNER,
            f"  {name}",
            body,
            "  No hooks for this event yet",
            "  To add hooks, edit settings.json directly or ask Claude",
            "  Esc to go back",
        ]
    )


def _untitled(fixture: str) -> str:
    """A ``_DETAIL_*`` fixture without its (pre-2.1.332) title line; _detail_pane adds the title."""
    return fixture.split("\n", 1)[1]


_READY_PANE = "❯ \n" + _RULE + "\n  ⏵⏵ bypass permissions on (shift+tab to cycle)"


class TestListRows:
    def test_list_rows__v2_1_332_list_pane__pairs_names_with_descriptions(self):
        pane = _list_pane(
            "PreToolUse",
            [("PreToolUse", "Before tool execution"), ("PostToolUse", "After tool execution")],
            34,
        )
        assert menu_scanner._list_rows(pane) == [
            {"focused": True, "name": "PreToolUse", "desc": "Before tool execution"},
            {"focused": False, "name": "PostToolUse", "desc": "After tool execution"},
        ]
        assert menu_scanner._focused_name(pane) == "PreToolUse"
        assert menu_scanner._total_count(pane) == 34

    def test_list_rows__scroll_indicators__ignored(self):
        pane = _list_pane("Stop", [("Stop", "Right before Claude concludes its response")], 34, above=9, below=24)
        assert [r["name"] for r in menu_scanner._list_rows(pane)] == ["Stop"]

    def test_list_rows__landing_pane__no_rows(self):
        # "Hooks" / "All events" (and the "❯ /hooks" prompt echo) must not be parsed as events.
        assert menu_scanner._list_rows(_landing_pane()) == []
        assert menu_scanner._focused_name(_landing_pane()) is None
        assert menu_scanner._total_count(_landing_pane()) is None

    def test_list_rows__wrapped_description__joined_onto_its_row(self):
        pane = _list_pane("UserPromptExpansion", [("UserPromptExpansion", "When a user-typed slash command")], 1)
        pane = pane.replace("slash command\n", "slash command\n      expands into a prompt\n")
        (row,) = menu_scanner._list_rows(pane)
        assert row["desc"] == "When a user-typed slash command expands into a prompt"

    def test_list_rows__name_at_viewport_bottom__empty_desc(self):
        pane = _list_pane(
            None, [("Stop", "Right before Claude concludes"), ("StopFailure", "x")], 2, cut_last_desc=True
        )
        assert menu_scanner._list_rows(pane)[-1] == {"focused": False, "name": "StopFailure", "desc": ""}

    def test_list_rows__orphan_description_at_viewport_top__dropped(self):
        pane = _list_pane("Stop", [("Stop", "Right before Claude concludes")], 34, above=9)
        pane = pane.replace("    ↑ 9 more\n", "    ↑ 9 more\n    When a new session is started\n")
        assert menu_scanner._list_rows(pane) == [
            {"focused": True, "name": "Stop", "desc": "Right before Claude concludes"}
        ]


class TestScreen:
    def test_screen__list_footer_containing_go_back__classified_as_list(self):
        assert menu_scanner._screen(_list_pane("Stop", [("Stop", "x")], 1)) == "list"

    def test_screen__detail_footer_only__classified_as_detail(self):
        assert menu_scanner._screen(_PANE_PREMODELSWITCH) == "detail"

    def test_screen__landing_footer__classified_as_landing(self):
        assert menu_scanner._screen(_landing_pane()) == "landing"

    def test_screen__prompt__classified_as_other(self):
        assert menu_scanner._screen(_READY_PANE) == "other"


# --- scan_hooks_menu against a fake Tmux ---------------------------------------------------------


class _FakeTmux(Tmux):
    """A scripted cc-2.1.332 /hooks: screens ready → landing → list → detail; Esc steps back one.

    ``wraps``: Down on the last row wraps to the first (else it stays put). ``reset_focus_on_escape``:
    detail → list resets focus to the first row (else keeps it). Entering the list from the landing
    screen always starts at the first row. ``wrong_detail_once``: the first Enter on that name opens
    the *next* entry's detail. ``list_never_renders``: /hooks never opens (the screen stays ready).
    """

    def __init__(
        self,
        rows: list[tuple[str, str]],
        bodies: dict[str, str],
        *,
        total: int | None = None,
        wraps: bool = True,
        reset_focus_on_escape: bool = False,
        wrong_detail_once: str | None = None,
        list_never_renders: bool = False,
    ) -> None:
        super().__init__(runner=lambda argv: None)  # runner never used
        self._rows = rows
        self._bodies = bodies
        self._total = len(rows) if total is None else total
        self._wraps = wraps
        self._reset_focus_on_escape = reset_focus_on_escape
        self._wrong_detail_once = wrong_detail_once
        self._list_never_renders = list_never_renders
        self._focus = 0
        self._detail = 0
        self._screen = "ready"  # ready (prompt) | landing | list | detail | dead
        self._pending = ""
        self.session_size: tuple[int | None, int | None] | None = None
        self.opened: list[str] = []  # names whose detail was opened, in order
        self.downs = 0  # Down presses on the list screen

    def new_session(self, name, cwd, command, env=None, *, width=None, height=None) -> None:
        self._screen = "ready"
        self.session_size = (width, height)

    def has_session(self, name) -> bool:
        return self._screen != "dead"

    def send_text(self, name, text) -> None:
        self._pending = text  # typed into the prompt, not yet submitted

    def _down(self) -> None:
        last = len(self._rows) - 1
        self._focus = (self._focus + 1) % len(self._rows) if self._wraps else min(self._focus + 1, last)

    def send_key(self, name, key) -> None:
        screen = self._screen
        if screen == "ready" and key == "Enter" and self._pending == "/hooks":
            self._pending = ""
            if not self._list_never_renders:
                self._screen = "landing"
        elif screen == "landing" and key == "Enter":
            self._screen, self._focus = "list", 0
        elif screen == "landing" and key == "Escape":
            self._screen = "ready"
        elif screen == "list" and key == "Down":
            self.downs += 1
            self._down()
        elif screen == "list" and key == "Enter":
            self._detail = self._focus
            focused = self._rows[self._focus][0]
            if focused == self._wrong_detail_once:
                self._wrong_detail_once = None
                self._detail = (self._focus + 1) % len(self._rows)
            self.opened.append(self._rows[self._detail][0])
            self._screen = "detail"
        elif screen == "list" and key == "Escape":
            self._screen = "landing"
        elif screen == "detail" and key == "Escape":
            self._screen = "list"
            if self._reset_focus_on_escape:
                self._focus = 0

    def _render_list(self) -> str:
        return _list_pane(self._rows[self._focus][0], self._rows, self._total)

    def capture_pane(self, name) -> str:
        if self._screen == "landing":
            return _landing_pane()
        if self._screen == "list":
            return self._render_list()
        if self._screen == "detail":
            detail_name = self._rows[self._detail][0]
            return _detail_pane(detail_name, self._bodies[detail_name])
        return _READY_PANE

    def kill_session(self, name) -> None:
        self._screen = "dead"


class _LaggyFakeTmux(_FakeTmux):
    """Models a slow /hooks list: only a ``viewport`` of rows renders at once (with ↑/↓ N more), a Down
    re-renders only after ``lag`` subsequent pane captures, and a Down sent while the previous one is
    still pending is dropped — the input loss that broke the fixed-sleep scanner (CC 2.1.220).
    ``cut_last_desc`` leaves the bottom row's description below the viewport edge (while more rows
    follow)."""

    def __init__(self, rows, bodies, *, lag: int, viewport: int, cut_last_desc: bool = False, **kw) -> None:
        super().__init__(rows, bodies, **kw)
        self._lag = lag
        self._viewport = viewport
        self._cut_last_desc = cut_last_desc
        self._pending_down = 0  # captures remaining until the queued Down lands

    def send_key(self, name, key) -> None:
        if key == "Down" and self._screen == "list":
            if self._pending_down:
                return  # dropped: the previous press hasn't re-rendered yet
            self._pending_down = self._lag
            return
        self._pending_down = 0
        super().send_key(name, key)

    def capture_pane(self, name) -> str:
        if self._pending_down and self._screen == "list":
            self._pending_down -= 1
            if self._pending_down == 0:
                self._down()  # the queued press finally lands
        return super().capture_pane(name)

    def _render_list(self) -> str:
        n = len(self._rows)
        start = min(max(self._focus - 1, 0), n - self._viewport)
        visible = self._rows[start : start + self._viewport]
        return _list_pane(
            self._rows[self._focus][0],
            visible,
            self._total,
            above=start,
            below=n - start - len(visible),
            cut_last_desc=self._cut_last_desc and start + len(visible) < n,  # only when rows follow
        )


def _fake_time():
    """A sleep/clock pair over one fake timeline, so bounded waits progress and time out."""
    state = {"t": 0.0}

    def sleep(s: float) -> None:
        state["t"] += s

    def clock() -> float:
        state["t"] += 0.01  # each clock read costs a beat, so even poll-only loops advance
        return state["t"]

    return sleep, clock


def _scan(fake, tmp_path):
    sleep, clock = _fake_time()
    return menu_scanner.scan_hooks_menu(claude_bin="claude", sandbox_root=tmp_path, tmux=fake, sleep=sleep, clock=clock)


_ROWS3 = [
    ("PreToolUse", "Before tool execution"),
    ("PostToolUseFailure", "After tool execution fails"),
    ("Elicitation", "When an MCP server requests user input"),
]
_BODIES3 = {
    "PreToolUse": _untitled(_DETAIL_PRETOOLUSE),
    "PostToolUseFailure": _untitled(_DETAIL_FAILURE),
    "Elicitation": _untitled(_DETAIL_ELICITATION),
}
_ROWS6 = [
    ("PreToolUse", "Before tool execution"),
    ("PostToolUse", "After tool execution"),
    ("PostToolUseFailure", "After tool execution fails"),
    ("PermissionDenied", "After auto mode denies a tool call"),
    ("Elicitation", "When an MCP server requests user input"),
    ("SessionStart", "When a new session is started"),
]
_BODIES6 = {
    "PreToolUse": _untitled(_DETAIL_PRETOOLUSE),
    "PostToolUse": _untitled(_DETAIL_FAILURE),
    "PostToolUseFailure": _untitled(_DETAIL_FAILURE),
    "PermissionDenied": _untitled(_DETAIL_PERMISSION_DENIED),
    "Elicitation": _untitled(_DETAIL_ELICITATION),
    "SessionStart": _untitled(_DETAIL_PRETOOLUSE),
}


def _assert_each_body_is_its_own(entries):
    for e in entries:
        assert e["raw"].splitlines()[0].strip() == e["event"], e["event"]


class TestScanHooksMenu:
    def test_scan_hooks_menu__three_entries__parses_in_order(self, tmp_path):
        fake = _FakeTmux(_ROWS3, _BODIES3)

        entries, raw = _scan(fake, tmp_path)

        assert fake.session_size == (200, 50)
        assert [e["event"] for e in entries] == ["PreToolUse", "PostToolUseFailure", "Elicitation"]
        failure = entries[1]
        assert failure["description"] == "After tool execution fails"
        assert "tool_name" in failure["input_fields"]
        assert "Exit code 2 - show stderr to model immediately" in failure["exit_codes"]
        assert entries[2]["output_fields"]  # Elicitation has an output note with hookSpecificOutput
        assert "### Elicitation" in raw
        _assert_each_body_is_its_own(entries)
        assert set(entries[0]) == {
            "event",
            "description",
            "input_note",
            "output_note",
            "input_fields",
            "output_fields",
            "exit_codes",
            "raw",
        }

    def test_scan_hooks_menu__laggy_tui_dropping_rapid_keypresses__still_scrapes_every_entry(self, tmp_path):
        fake = _LaggyFakeTmux(_ROWS6, _BODIES6, lag=3, viewport=3)

        entries, raw = _scan(fake, tmp_path)

        assert [e["event"] for e in entries] == [name for name, _ in _ROWS6]
        assert all(e["raw"] for e in entries)  # every entry got a real detail body, not just the first
        _assert_each_body_is_its_own(entries)
        assert "hookSpecificOutput" in entries[4]["output_note"]  # Elicitation's body landed at its own name
        assert "### SessionStart" in raw

    def test_scan_hooks_menu__description_cut_at_viewport_edge__longer_capture_kept(self, tmp_path):
        fake = _LaggyFakeTmux(_ROWS6, _BODIES6, lag=1, viewport=3, cut_last_desc=True)

        entries, _ = _scan(fake, tmp_path)

        assert [(e["event"], e["description"]) for e in entries] == _ROWS6

    def test_scan_hooks_menu__escape_resets_focus__still_captures_every_entry_at_its_own_name(self, tmp_path):
        fake = _FakeTmux(_ROWS6, _BODIES6, reset_focus_on_escape=True)

        entries, _ = _scan(fake, tmp_path)

        assert all(e["raw"] for e in entries)
        _assert_each_body_is_its_own(entries)
        assert fake.opened == [name for name, _ in _ROWS6]

    def test_scan_hooks_menu__escape_keeps_focus__still_captures_every_entry_at_its_own_name(self, tmp_path):
        fake = _FakeTmux(_ROWS6, _BODIES6, reset_focus_on_escape=False)  # real cc-2.1.332

        entries, _ = _scan(fake, tmp_path)

        assert all(e["raw"] for e in entries)
        _assert_each_body_is_its_own(entries)
        assert fake.opened == [name for name, _ in _ROWS6]  # each detail opened exactly once, in order

    def test_scan_hooks_menu__list_does_not_wrap__roster_terminates_complete(self, tmp_path):
        fake = _FakeTmux(_ROWS6, _BODIES6, wraps=False)

        entries, _ = _scan(fake, tmp_path)

        assert [e["event"] for e in entries] == [name for name, _ in _ROWS6]
        # Phase A ends on the last row; Phase B re-enters the list to get back to the top.
        assert all(e["raw"] for e in entries)
        _assert_each_body_is_its_own(entries)
        # Phase A stopped after _STUCK_LIMIT presses at the bottom, not after max_presses (120).
        assert fake.downs < 30

    def test_scan_hooks_menu__count_header_mismatch__raises_menu_scan_error(self, tmp_path):
        fake = _FakeTmux(_ROWS3, _BODIES3, total=4)

        with pytest.raises(menu_scanner.MenuScanError, match="says 4 events but 3 were scraped") as exc_info:
            _scan(fake, tmp_path)

        assert "4 events · 0 with hooks" in exc_info.value.pane
        assert fake.opened == []  # no detail pass on an incomplete roster
        assert not fake.has_session("s")  # session still torn down

    def test_scan_hooks_menu__no_list_ever_renders__raises_menu_scan_error_with_last_pane(self, tmp_path):
        fake = _FakeTmux(_ROWS3, _BODIES3, list_never_renders=True)

        with pytest.raises(menu_scanner.MenuScanError, match="parsed 0 entries") as exc_info:
            _scan(fake, tmp_path)

        assert exc_info.value.pane == _READY_PANE

    def test_scan_hooks_menu__detail_title_mismatch__body_dropped(self, tmp_path):
        fake = _FakeTmux(_ROWS3, _BODIES3, wrong_detail_once="PostToolUseFailure")

        entries, _ = _scan(fake, tmp_path)

        by_name = {e["event"]: e for e in entries}
        assert by_name["PostToolUseFailure"]["raw"] == ""  # never another entry's text
        assert by_name["PostToolUseFailure"]["input_fields"] == []
        assert by_name["Elicitation"]["raw"].splitlines()[0].strip() == "Elicitation"
        assert by_name["PreToolUse"]["raw"]
