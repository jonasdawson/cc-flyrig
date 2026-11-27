"""Write the ``--settings`` JSON files injected into each capture scenario's ``claude`` invocation."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HookEntry:
    event: str
    command: str
    matcher: str | None = None


@dataclass(frozen=True, slots=True)
class StatusLineEntry:
    """A single top-level statusline-family settings key (``statusLine`` / ``subagentStatusLine``).

    Unlike hooks, statusline settings keys take a single command object rather than a matcher list,
    so there is no ``matcher`` field here.
    """

    settings_key: str
    command: str


def write_scenario_settings(
    path: str | Path,
    entries: list[HookEntry],
    statusline_entries: list[StatusLineEntry] | tuple[StatusLineEntry, ...] = (),
) -> Path:
    """Render hook (and, optionally, statusline-family) entries to a Claude Code settings JSON file.

    The emitted document is ``hooks`` + ``skipDangerousModePermissionPrompt`` (since cc-2.1.332),
    plus the statusline-family keys when ``statusline_entries`` is given.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(_build_scenario_settings(entries, statusline_entries), indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def _build_scenario_settings(
    entries: list[HookEntry],
    statusline_entries: list[StatusLineEntry] | tuple[StatusLineEntry, ...] = (),
) -> dict:
    hooks: dict = {}
    for entry in entries:
        hook = {"type": "command", "command": entry.command}
        if entry.matcher is not None:
            hooks[entry.event] = [{"matcher": entry.matcher, "hooks": [hook]}]
        else:
            hooks[entry.event] = [{"hooks": [hook]}]
    # cc-2.1.332 shows a launch-time Bypass Permissions warning (default-highlighted "No, exit") unless
    # this is set. The maintainer's own copy lives in *user* settings, which --setting-sources project
    # excludes, so every generated settings file carries it. Harmless in non-bypass scenarios.
    document: dict = {"hooks": hooks, "skipDangerousModePermissionPrompt": True}
    for entry in statusline_entries:
        command: dict = {"type": "command", "command": entry.command}
        if entry.settings_key == "subagentStatusLine":
            command["refreshInterval"] = 1
        document[entry.settings_key] = command
    return document
