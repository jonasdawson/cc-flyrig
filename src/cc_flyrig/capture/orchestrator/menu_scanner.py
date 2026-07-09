"""Scan the ``/hooks`` TUI menu of an interactive ``claude`` and parse it into plain data.

Maintainer-run, in the devcontainer (needs ``claude`` + tmux). The ``/hooks`` menu is the running
binary's own enumeration of every hook event plus, per entry, an input-JSON note, exit-code
semantics, and sometimes an output-JSON note (proven by a since-retired spike — see git history for
capture_harness/spikes/hooks_menu_spike.py). This module drives that menu — reusing
``scenario_runner``'s tmux readiness helpers — and returns a list of entry dicts.

It produces **plain data**, not a shared dataclass: the parsed entries are written to
``captures/cc-<version>/hooks_menu.json`` and read back as JSON by ``schema.drift_detector`` (the
menu-vs-IR comparison) and ``coverage_report`` (the rendered ``HOOKS_MENU.md``). The artifact is the interface,
mirroring how ``output_builder`` reads ``output_manifest.json``.

The menu wraps and **resets focus to the top whenever an entry detail is closed** (Esc), so scanning
is two-pass: scroll-follow the list to collect the roster, then re-open and reach each detail by
absolute index from the top.
"""

import re
import tempfile
import time
from pathlib import Path

from ...cli.tmux import Tmux
from .scenario_runner import _session_name, _wait_for, _wait_ready

# A numbered list row, e.g. "  ❯ 7.  UserPromptSubmit     When the user submits a prompt" — the
# leading glyph is the focus marker (❯) or a scroll indicator (↑/↓) or nothing.
_ROW = re.compile(r"^\s*(?P<focus>[❯>])?\s*(?:[↑↓]\s*)?(?P<num>\d+)\.\s+(?P<name>\w+)\s{2,}(?P<desc>.+?)\s*$")

# Footers that identify which screen the pane is showing.
_LIST_FOOTER = "Esc to cancel"
_DETAIL_FOOTER = "go back"

# Lines that are menu chrome, not documentation, dropped before classifying a detail body.
_BOILERPLATE = ("No hooks configured", "To add hooks")

# Parenthetical clarifications and inline JSON examples hold enum values / nested keys, not top-level
# field names — strip them before extracting fields (e.g. `Return {"hookSpecificOutput":{...}}`).
_PAREN = re.compile(r"\([^)]*\)")
_BRACE = re.compile(r"\{[^{}]*\}")
# A possibly-dotted token; we keep only the root segment so "hookSpecificOutput.watchPaths" → the
# top-level "hookSpecificOutput" (nested keys aren't top-level IR props).
_TOKEN = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_.]*\b")
# A root that is snake_case or camelCase — conservative field-name extraction (drops prose words).
_IDENT = re.compile(r"(?:[a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z]+[A-Z][a-zA-Z0-9]*)\Z")


def _list_rows(pane: str) -> list[dict]:
    rows = []
    for line in pane.splitlines():
        m = _ROW.match(line)
        if m:
            rows.append(
                {
                    "focused": bool(m.group("focus")),
                    "num": int(m.group("num")),
                    "name": m.group("name"),
                    "desc": m.group("desc"),
                }
            )
    return rows


def _focused_row(pane: str) -> dict | None:
    for row in _list_rows(pane):
        if row["focused"]:
            return row
    return None


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


def _open_menu(tmux: Tmux, session: str, sleep, clock) -> None:
    tmux.send_text(session, "/hooks")
    sleep(0.5)
    tmux.send_key(session, "Enter")
    _wait_for(lambda: _LIST_FOOTER in tmux.capture_pane(session), 10.0, sleep, clock, poll=0.3, required=False)


def _scrape_roster(tmux: Tmux, session: str, sleep, max_presses: int = 80) -> list[dict]:
    """Phase A: Down-only, follow focus until it wraps, accumulating visible list rows by number."""
    rows: dict[int, dict] = {}
    seen_focus: list[int] = []
    for _ in range(max_presses):
        pane = tmux.capture_pane(session)
        for r in _list_rows(pane):
            rows[r["num"]] = r
        focused = _focused_row(pane)
        if focused is not None:
            if focused["num"] in seen_focus:
                break
            seen_focus.append(focused["num"])
        tmux.send_key(session, "Down")
        sleep(0.25)
    return [rows[k] for k in sorted(rows)]


def _capture_details(tmux: Tmux, session: str, count: int, sleep, clock) -> dict[int, str]:
    """Phase B: reach entry k by stepping Down k-1 from the top; return {num: detail_body}."""
    bodies: dict[int, str] = {}
    for k in range(1, count + 1):
        _wait_for(lambda: _LIST_FOOTER in tmux.capture_pane(session), 5.0, sleep, clock, poll=0.3, required=False)
        for _ in range(k - 1):
            tmux.send_key(session, "Down")
            sleep(0.15)
        tmux.send_key(session, "Enter")
        _wait_for(lambda: _DETAIL_FOOTER in tmux.capture_pane(session), 5.0, sleep, clock, poll=0.3, required=False)
        bodies[k] = _detail_body(tmux.capture_pane(session))
        tmux.send_key(session, "Escape")
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
    """
    tmux = tmux or Tmux()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="flyrig_menu_", dir=sandbox_root))
    session = _session_name("menu", "scan")

    try:
        tmux.new_session(session, cwd=str(sandbox), command=[claude_bin, "--setting-sources", "project"])
        _wait_ready(tmux, session, 30.0, sleep, clock, poll=1.0)
        _open_menu(tmux, session, sleep, clock)
        roster = _scrape_roster(tmux, session, sleep)
        # Phase A leaves focus mid-list; re-open so Phase B starts at the top.
        tmux.send_key(session, "Escape")
        sleep(0.5)
        _open_menu(tmux, session, sleep, clock)
        bodies = _capture_details(tmux, session, len(roster), sleep, clock)
    finally:
        tmux.kill_session(session)

    entries: list[dict] = []
    raw_chunks: list[str] = []
    for row in roster:
        body = bodies.get(row["num"], "")
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
