"""P10/P12: drive the keep/remove worktree dialog to Remove when a ``--worktree`` session exits.

Pre-accepts workspace trust (else ``--worktree`` exits before the TUI), strips ``$TMUX``/``$TMUX_PANE``
from the argv (#39281: ``--worktree --tmux`` suppresses hooks), and navigates the dialog on teardown.
"""

import json
from pathlib import Path

from .base import EnvironmentPlugin, RunContext, RunPlan, require_bool

_CLAUDE_JSON = Path.home() / ".claude" / ".claude.json"


def _pre_seed_trust(sandbox: Path) -> None:
    """Pre-accept workspace trust so a ``--worktree`` session shows the TUI instead of exiting.

    CC checks ~/.claude/.claude.json projects[path].hasTrustDialogAccepted before creating a worktree;
    if false/absent it exits immediately with an error rather than showing the TUI.
    """
    try:
        config = json.loads(_CLAUDE_JSON.read_text(encoding="utf-8"))
        config.setdefault("projects", {}).setdefault(str(sandbox), {})["hasTrustDialogAccepted"] = True
        _CLAUDE_JSON.write_text(json.dumps(config), encoding="utf-8")
    except Exception:
        pass  # best-effort; a failed write produces a clear error at the capture run


def _navigate(ctx: RunContext) -> None:
    # capture_pane returns stale pre-dialog content while CC redraws, so a fixed sleep is more robust
    # than marker detection. "❯ 1. Keep worktree / 2. Remove worktree" — typing 2 selects Remove.
    ctx.sleep(3.0)
    ctx.send_text("2")
    ctx.send_key("Enter")
    ctx.wait_for_event("WorktreeRemove", 30.0)


def _configure(ctx: RunContext, plan: RunPlan) -> None:
    _pre_seed_trust(ctx.sandbox)
    plan.argv_prefix = ["env", "-u", "TMUX", "-u", "TMUX_PANE"]
    plan.teardown.append(lambda: _navigate(ctx))


ENVIRONMENT_PLUGIN = EnvironmentPlugin(
    validate=require_bool,
    configure=lambda v, ctx, plan: _configure(ctx, plan) if v else None,
)
