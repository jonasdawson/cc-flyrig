"""Scan the ``/hooks`` TUI menu of an interactive ``claude`` and parse it into plain data.

Maintainer-run, in the devcontainer (needs ``claude`` + tmux). The ``/hooks`` menu is the running
binary's own enumeration of every hook event plus, per entry, an input-JSON note, exit-code
semantics, and sometimes an output-JSON note. This module drives that menu — reusing
``scenario_runner``'s tmux readiness helpers — and returns a list of entry dicts.

It produces **plain data**, not a shared dataclass: the parsed entries are written to
``captures/cc-<version>/hooks_menu.json`` and read back as JSON by ``schema.drift_detector`` (the
menu-vs-IR comparison) and ``coverage_report`` (the rendered ``HOOKS_MENU.md``). The artifact is the interface,
mirroring how ``output_builder`` reads ``output_manifest.json``.

Screens (cc-2.1.332). ``/hooks`` is four screens deep, each identified by its footer:

* **prompt**: the input box (``? for shortcuts`` / ``(shift+tab to cycle)``).
* **landing**: ``Hooks`` + a single ``❯ All events`` item; footer ``Enter to view · Esc to close``.
* **list**: header ``N events · M with hooks``, then one *unnumbered* two-line row per event (a
  CamelCase name line, focus glyph ``❯`` on the focused one, then an indented description line),
  ``↑/↓ N more`` scroll indicators, footer ``↑/↓ to navigate · Enter to open · Esc to go back``.
* **detail**: the event name as a title, the input / output notes and exit-code lines, then the
  "No hooks for this event yet" boilerplate; footer ``Esc to go back``.

Esc steps back one screen (detail → list → landing → prompt). Rows carry no numbers, so navigation
is by **name** (names are unique in the menu). Scanning is two-pass: Phase A follows focus Down to
collect the roster (name + description); Phase B walks focus to each name in turn, opens its detail,
and keeps the body only if the detail title matches that name.

Observed cc-2.1.332 menu behavior, which picks the "real" fake-TUI variants in the tests:

* The list **wraps**: Down on the last entry (PreSkillShellCommand) focuses PreToolUse again.
* Esc from a detail **keeps focus** on that entry (it does not reset to the top). Esc from the
  list goes to the landing screen.
* No list description wraps, at 200×50 or at 80×24 (the longest list line is 69 columns). The
  session is still opened at 200×50 so the long detail lines (``Return {...}`` examples) stay on one
  line.

Phase A stops on a wrap *or* on the focus failing to move ``_STUCK_LIMIT`` presses in a row, so a
non-wrapping list still terminates; Phase B is correct whichever way Esc leaves focus. An
unrecognisable menu (0 rows parsed, or a roster that disagrees with the header's event count) raises
:class:`MenuScanError` carrying the last captured screen, rather than producing a partial artifact.
"""

import re
import tempfile
import time
from pathlib import Path

from ...cli.tmux import Tmux
from .scenario_runner import _session_name, _wait_for, _wait_ready

# Screen footers (cc-2.1.332). The list footer *also* contains "Esc to go back", so classify by the
# more specific markers first (see _screen).
_LANDING_FOOTER = "Enter to view"
_LIST_FOOTER = "Enter to open"
_DETAIL_FOOTER = "Esc to go back"
_ALL_EVENTS = "All events"
# List header "34 events · 0 with hooks": the binary's own count, used as a completeness check.
_COUNT = re.compile(r"(?P<total>\d+)\s+events\s+·")
# A list name line: optional focus glyph, then exactly one CamelCase identifier and nothing else.
# Descriptions ("Before tool execution") and the landing's "All events" contain spaces, so never match.
_NAME = re.compile(r"^\s*(?P<focus>❯)?\s*(?P<name>[A-Z][A-Za-z]+)\s*$")
_SCROLL = ("↑", "↓")
_SESSION_SIZE = (200, 50)  # wide enough that no 2.1.332 description wraps
_FOCUS_SETTLE_S = 1.5
_FOCUS_POLL_S = 0.1
_STUCK_LIMIT = 3  # consecutive presses that leave focus in place = end of a non-wrapping list

# Lines that are menu chrome, not documentation, dropped before classifying a detail body.
_BOILERPLATE = ("No hooks configured", "No hooks for this event yet", "To add hooks")

# Parenthetical clarifications and inline JSON examples hold enum values / nested keys, not top-level
# field names — strip them before extracting fields (e.g. `Return {"hookSpecificOutput":{...}}`).
_PAREN = re.compile(r"\([^)]*\)")
_BRACE = re.compile(r"\{[^{}]*\}")
# A possibly-dotted token; we keep only the root segment so "hookSpecificOutput.watchPaths" → the
# top-level "hookSpecificOutput" (nested keys aren't top-level IR props).
_TOKEN = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_.]*\b")
# A root that is snake_case or camelCase — conservative field-name extraction (drops prose words).
_IDENT = re.compile(r"(?:[a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z]+[A-Z][a-zA-Z0-9]*)\Z")


class MenuScanError(RuntimeError):
    """The /hooks menu could not be scraped (unknown screen, 0 rows, or a count mismatch)."""

    def __init__(self, message: str, pane: str) -> None:
        super().__init__(message)
        self.pane = pane  # the last captured screen, for hooks_menu.txt / debugging


def _screen(pane: str) -> str:
    """Classify the pane: 'list' | 'landing' | 'detail' | 'other' (most specific footer first)."""
    if _LIST_FOOTER in pane:
        return "list"
    if _LANDING_FOOTER in pane:
        return "landing"
    if _DETAIL_FOOTER in pane:
        return "detail"
    return "other"


def _list_region(pane: str) -> list[str]:
    """Lines strictly between the 'N events ·' header and the list footer ([] if no header)."""
    lines = pane.splitlines()
    start = next((i for i, ln in enumerate(lines) if _COUNT.search(ln)), None)
    if start is None:
        return []
    end = next((i for i, ln in enumerate(lines) if _LIST_FOOTER in ln), len(lines))
    return lines[start + 1 : end]


def _list_rows(pane: str) -> list[dict]:
    """Parse visible name/description pairs: [{'focused', 'name', 'desc'}] in screen order.

    A name line opens a row; following non-name lines are its description (joined, so a wrapped
    description survives). A description whose name scrolled off the top is dropped; a name whose
    description is below the viewport gets desc "" (a later capture fills it in, see _scrape_roster).
    """
    rows: list[dict] = []
    for ln in _list_region(pane):
        stripped = ln.strip()
        if not stripped or stripped.startswith(_SCROLL):
            continue
        m = _NAME.match(ln)
        if m:
            rows.append({"focused": bool(m.group("focus")), "name": m.group("name"), "desc": ""})
        elif rows:
            rows[-1]["desc"] = f"{rows[-1]['desc']} {stripped}".strip()
    return rows


def _focused_name(pane: str) -> str | None:
    return next((r["name"] for r in _list_rows(pane) if r["focused"]), None)


def _total_count(pane: str) -> int | None:
    m = next((m for m in (_COUNT.search(ln) for ln in pane.splitlines()) if m), None)
    return int(m.group("total")) if m else None


def _landing_focus_on_all_events(pane: str) -> bool:
    return any(ln.lstrip().startswith("❯") and _ALL_EVENTS in ln for ln in pane.splitlines())


def _detail_body(pane: str) -> str:
    """Return the detail-view body: lines after the last ─── rule, up to the 'Esc to go back' footer."""
    lines = pane.splitlines()
    sep_idx = max((i for i, ln in enumerate(lines) if ln.strip().startswith("─" * 10)), default=-1)
    out = []
    for ln in lines[sep_idx + 1 :]:
        if _DETAIL_FOOTER in ln or _LIST_FOOTER in ln:
            break
        out.append(ln.rstrip())
    return "\n".join(out).strip("\n")


def _field_names(note: str) -> list[str]:
    """Conservatively extract top-level field identifiers from a prose note.

    Drops parenthetical examples/enum values, reduces dotted paths to their root segment, and keeps
    only snake_case / camelCase roots (so prose words and enum values are ignored).
    """
    cleaned = _PAREN.sub(" ", note)
    while _BRACE.search(cleaned):  # collapse nested JSON examples inside-out
        cleaned = _BRACE.sub(" ", cleaned)
    seen: dict[str, None] = {}  # dict preserves first-seen order
    for token in _TOKEN.findall(cleaned):
        root = token.split(".")[0]
        if _IDENT.match(root):
            seen.setdefault(root, None)
    return list(seen)


def _parse_detail(body: str) -> dict:
    """Classify a detail body into input_note / output_note / exit_codes, retaining nothing else.

    The first line is the entry title; the rest is bucketed by line prefix. Wrapped continuation
    lines are joined into the current note. The full body is retained by the caller as ``raw``.
    """
    input_lines: list[str] = []
    output_lines: list[str] = []
    exit_lines: list[str] = []
    current: list[str] | None = None

    body_lines = body.splitlines()
    for ln in body_lines[1:]:  # skip the title line
        stripped = ln.strip()
        if not stripped or any(b in stripped for b in _BOILERPLATE):
            continue
        head = stripped.split(maxsplit=1)[0]
        if stripped.startswith("Input "):
            current = input_lines
            current.append(stripped)
        elif head in ("Output", "Return") or stripped.startswith("Hook output"):
            current = output_lines
            current.append(stripped)
        elif stripped.startswith(("Exit code", "Other exit codes")) or stripped == "Blocking errors are ignored":
            current = None
            exit_lines.append(stripped)
        elif current is not None:
            current.append(stripped)  # wrapped continuation of the current note

    return {
        "input_note": " ".join(input_lines),
        "output_note": " ".join(output_lines),
        "exit_codes": "\n".join(exit_lines),
    }


def _detail_title(body: str) -> str:
    """The first non-empty stripped line of a detail body: the entry's title ("" if none)."""
    return next((ln.strip() for ln in body.splitlines() if ln.strip()), "")


def _title_is(body: str, name: str) -> bool:
    # cc-2.1.332 titles are the bare name; older releases appended " - Matchers", so compare the
    # first token only.
    title = _detail_title(body).split()
    return bool(title) and title[0] == name


def _enter_list(tmux: Tmux, session: str, sleep, clock) -> None:
    """From the landing screen, focus 'All events' and open the list. No-op if already on the list."""
    _wait_for(
        lambda: _screen(tmux.capture_pane(session)) in ("landing", "list"),
        10.0,
        sleep,
        clock,
        poll=0.3,
        required=False,
    )
    if _screen(tmux.capture_pane(session)) == "landing":
        for _ in range(4):  # "All events" is the only landing item today; bounded in case that changes
            if _landing_focus_on_all_events(tmux.capture_pane(session)):
                break
            tmux.send_key(session, "Down")
            sleep(0.3)
        tmux.send_key(session, "Enter")
    _wait_for(
        lambda: _focused_name(tmux.capture_pane(session)) is not None,
        5.0,
        sleep,
        clock,
        poll=0.3,
        required=False,
    )


def _open_menu(tmux: Tmux, session: str, sleep, clock) -> None:
    tmux.send_text(session, "/hooks")
    sleep(0.5)
    tmux.send_key(session, "Enter")
    _enter_list(tmux, session, sleep, clock)


def _press_down_settled(tmux: Tmux, session: str, current: str | None, sleep, clock) -> None:
    """Press Down, then wait (bounded) for the focused *name* to move off ``current``.

    A press whose re-render hasn't landed yet is indistinguishable from a dropped one; timing out
    here means the caller re-reads the pane and decides — never that the focus definitely moved.
    """
    tmux.send_key(session, "Down")
    _wait_for(
        lambda: _focused_name(tmux.capture_pane(session)) != current,
        _FOCUS_SETTLE_S,
        sleep,
        clock,
        poll=_FOCUS_POLL_S,
        required=False,
    )


def _scrape_roster(tmux: Tmux, session: str, sleep, clock, max_presses: int = 120) -> tuple[list[dict], int | None]:
    """Phase A: Down-only, follow focus to the end of the list, accumulating every visible row.

    Returns ``([{'name', 'desc'}] in first-seen (= menu) order, the header's event count)``. Every
    capture is absorbed, keeping the longer description per name (a name seen at the viewport's
    bottom edge first arrives with desc ""). A press only counts once the focused name changes: a
    dropped keypress is retried rather than read as the end. The walk ends on a **wrap** (focus
    lands on an already-seen name) or, for a non-wrapping list, when focus fails to move
    ``_STUCK_LIMIT`` presses in a row.
    """
    order: list[str] = []
    desc: dict[str, str] = {}

    def absorb(pane: str) -> None:
        for r in _list_rows(pane):
            if r["name"] not in desc:
                order.append(r["name"])
                desc[r["name"]] = r["desc"]
            elif len(r["desc"]) > len(desc[r["name"]]):
                desc[r["name"]] = r["desc"]

    pane = tmux.capture_pane(session)
    absorb(pane)
    current = _focused_name(pane)
    seen_focus: list[str] = [current] if current is not None else []
    stuck = 0
    for _ in range(max_presses):
        _press_down_settled(tmux, session, current, sleep, clock)
        pane = tmux.capture_pane(session)
        absorb(pane)
        name = _focused_name(pane)
        if name == current:
            stuck += 1  # a dropped press (retry), or the bottom of a non-wrapping list
            if stuck >= _STUCK_LIMIT:
                break
            continue
        stuck = 0
        current = name
        if name is not None:
            if name in seen_focus:
                break  # wrapped back to an already-seen row: the whole list has been walked
            seen_focus.append(name)
    return [{"name": n, "desc": desc[n]} for n in order], _total_count(pane)


def _navigate_to(tmux: Tmux, session: str, target: str, sleep, clock, max_presses: int) -> bool:
    """Walk focus down to ``target``, re-pressing dropped keys; wrap-around recovers overshoot.

    Gives up early (False) if focus stops moving ``_STUCK_LIMIT`` presses in a row: the bottom of a
    non-wrapping list, which the caller recovers from by re-entering the list at the top.
    """
    stuck = 0
    for _ in range(max_presses):
        current = _focused_name(tmux.capture_pane(session))
        if current == target:
            return True
        _press_down_settled(tmux, session, current, sleep, clock)
        if _focused_name(tmux.capture_pane(session)) == current:
            stuck += 1
            if stuck >= _STUCK_LIMIT:
                return False
        else:
            stuck = 0
    return _focused_name(tmux.capture_pane(session)) == target


def _ensure_list(tmux: Tmux, session: str, sleep, clock) -> bool:
    """Get back to the event list from a detail (a dropped Esc) or the landing screen."""
    if _screen(tmux.capture_pane(session)) == "detail":
        tmux.send_key(session, "Escape")
        _wait_for(
            lambda: _screen(tmux.capture_pane(session)) != "detail",
            5.0,
            sleep,
            clock,
            poll=0.3,
            required=False,
        )
    if _screen(tmux.capture_pane(session)) == "landing":
        _enter_list(tmux, session, sleep, clock)
    return _screen(tmux.capture_pane(session)) == "list"


def _reenter_list(tmux: Tmux, session: str, sleep, clock) -> None:
    """Esc to the landing screen and open the list again (focus starts back at the top)."""
    tmux.send_key(session, "Escape")
    _wait_for(
        lambda: _screen(tmux.capture_pane(session)) == "landing",
        5.0,
        sleep,
        clock,
        poll=0.3,
        required=False,
    )
    _enter_list(tmux, session, sleep, clock)


def _capture_details(tmux: Tmux, session: str, names: list[str], sleep, clock) -> dict[str, str]:
    """Phase B: walk focus to each entry *by name* and open it; return {name: detail_body}.

    Works whether Esc-from-detail resets focus to the top or keeps it. A body is recorded only
    if the detail title is that entry's name, so another entry's text is never stored.
    """
    bodies: dict[str, str] = {}
    max_presses = 2 * len(names) + 8
    for name in names:
        if not _ensure_list(tmux, session, sleep, clock):
            continue
        if not _navigate_to(tmux, session, name, sleep, clock, max_presses):
            _reenter_list(tmux, session, sleep, clock)
            if not _navigate_to(tmux, session, name, sleep, clock, max_presses):
                continue  # never reached the entry — leave its body missing rather than capture a wrong one
        tmux.send_key(session, "Enter")
        opened = _wait_for(
            lambda: _screen(tmux.capture_pane(session)) == "detail",
            5.0,
            sleep,
            clock,
            poll=0.3,
            required=False,
        )
        if not opened:
            continue  # Enter dropped; still on the list, so no Esc (that would leave the list)
        body = _detail_body(tmux.capture_pane(session))
        if _title_is(body, name):
            bodies[name] = body
        tmux.send_key(session, "Escape")
        _wait_for(
            lambda: _screen(tmux.capture_pane(session)) in ("list", "landing"),
            5.0,
            sleep,
            clock,
            poll=0.3,
            required=False,
        )
    return bodies


def scan_hooks_menu(
    *,
    claude_bin: str,
    sandbox_root: Path,
    tmux: Tmux | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[list[dict], str]:
    """Drive ``/hooks`` in a throwaway sandbox, scrape every entry, return ``(entries, raw_text)``.

    ``entries`` is one dict per menu entry, in menu order, with keys ``event``, ``description``,
    ``input_note``, ``output_note``, ``input_fields``, ``output_fields``, ``exit_codes``, ``raw``.
    ``raw_text`` is the concatenated raw detail views (for ``hooks_menu.txt``).

    Raises :class:`MenuScanError` (with the last captured screen) if no list rows could be parsed or
    the roster disagrees with the list header's event count.
    """
    tmux = tmux or Tmux()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="flyrig_menu_", dir=sandbox_root))
    session = _session_name("menu", "scan")

    try:
        tmux.new_session(
            session,
            cwd=str(sandbox),
            command=[claude_bin, "--setting-sources", "project"],
            width=_SESSION_SIZE[0],
            height=_SESSION_SIZE[1],
        )
        _wait_ready(tmux, session, 30.0, sleep, clock, poll=1.0)
        _open_menu(tmux, session, sleep, clock)
        roster, total = _scrape_roster(tmux, session, sleep, clock)
        if not roster:
            raise MenuScanError("parsed 0 entries from /hooks", pane=tmux.capture_pane(session))
        if total is not None and total != len(roster):
            raise MenuScanError(
                f"/hooks header says {total} events but {len(roster)} were scraped",
                pane=tmux.capture_pane(session),
            )
        bodies = _capture_details(tmux, session, [r["name"] for r in roster], sleep, clock)
    finally:
        tmux.kill_session(session)

    entries: list[dict] = []
    raw_chunks: list[str] = []
    for row in roster:
        body = bodies.get(row["name"], "")
        parsed = _parse_detail(body)
        entries.append(
            {
                "event": row["name"],
                "description": row["desc"],
                "input_note": parsed["input_note"],
                "output_note": parsed["output_note"],
                "input_fields": _field_names(parsed["input_note"]),
                "output_fields": _field_names(parsed["output_note"]),
                "exit_codes": parsed["exit_codes"],
                "raw": body,
            }
        )
        raw_chunks.append(f"### {row['name']}\n{body}")

    return entries, "\n\n".join(raw_chunks) + "\n"
