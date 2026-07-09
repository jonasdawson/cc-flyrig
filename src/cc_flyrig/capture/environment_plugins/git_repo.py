"""P9: seed the sandbox as a real git repo and select native (no-shim) probe settings.

A real repo lets CC's native git worktree machinery run (which fires ``WorktreeRemove``); the native
settings omit the ``WorktreeCreate`` shim so #37611 (a custom hook suppressing removal) is not in play.
"""

import os
import subprocess

from .base import EnvironmentPlugin, RunContext, RunPlan, require_bool


def _configure(ctx: RunContext, plan: RunPlan) -> None:
    # Strip inherited GIT_* vars (e.g. GIT_INDEX_FILE set by a pre-commit hook) so the sandbox
    # git commands use only their own isolated state, then overlay the vars we actually want.
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    git_env.update(
        {
            "GIT_AUTHOR_NAME": "flyrig",
            "GIT_AUTHOR_EMAIL": "flyrig@local",
            "GIT_COMMITTER_NAME": "flyrig",
            "GIT_COMMITTER_EMAIL": "flyrig@local",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
    )
    subprocess.run(["git", "init", "-q", str(ctx.sandbox)], check=True, env=git_env)
    subprocess.run(["git", "-C", str(ctx.sandbox), "commit", "--allow-empty", "-m", "init"], check=True, env=git_env)
    if ctx.native_settings_path is not None:
        plan.settings_path = ctx.native_settings_path


ENVIRONMENT_PLUGIN = EnvironmentPlugin(
    validate=require_bool,
    configure=lambda v, ctx, plan: _configure(ctx, plan) if v else None,
)
