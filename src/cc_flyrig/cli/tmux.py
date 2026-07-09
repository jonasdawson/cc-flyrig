"""Thin wrapper over the ``tmux`` CLI used to drive an interactive ``claude`` session.

Every tmux interaction goes through this class so the orchestrator can be unit-tested by injecting a
fake ``runner`` — no real tmux (or model) is needed in CI. tmux itself is a provisioned devcontainer
dependency (``.devcontainer/Dockerfile``), so this is a maintainer-environment tool, not a shipped
artifact.
"""

import subprocess
from collections.abc import Callable

RunnerFn = Callable[[list[str]], subprocess.CompletedProcess]

# Tokens the orchestrator may send as named keys rather than literal text (tmux key names).
NAMED_KEYS: frozenset[str] = frozenset(
    {"Enter", "Escape", "Tab", "Space", "BSpace", "Up", "Down", "Left", "Right", "Home", "End"}
)


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


class Tmux:
    def __init__(self, runner: RunnerFn = _default_runner) -> None:
        self._run = runner

    def new_session(self, name: str, cwd: str, command: list[str], env: dict[str, str] | None = None) -> None:
        argv = ["tmux", "new-session", "-d", "-s", name, "-c", cwd]
        for key, value in (env or {}).items():
            argv += ["-e", f"{key}={value}"]
        argv += list(command)
        self._run(argv)

    def has_session(self, name: str) -> bool:
        return self._run(["tmux", "has-session", "-t", name]).returncode == 0

    def send_text(self, name: str, text: str) -> None:
        """Send literal text (no trailing Enter)."""
        self._run(["tmux", "send-keys", "-t", name, "-l", text])

    def send_key(self, name: str, key: str) -> None:
        """Send a single named key (e.g. ``Enter``)."""
        self._run(["tmux", "send-keys", "-t", name, key])

    def send_tokens(self, name: str, tokens: list[str]) -> None:
        """Send a sequence: named-key tokens go as keys, everything else as literal text."""
        for token in tokens:
            if token in NAMED_KEYS:
                self.send_key(name, token)
            else:
                self.send_text(name, token)

    def capture_pane(self, name: str) -> str:
        return self._run(["tmux", "capture-pane", "-p", "-t", name]).stdout or ""

    def kill_session(self, name: str) -> None:
        self._run(["tmux", "kill-session", "-t", name])
