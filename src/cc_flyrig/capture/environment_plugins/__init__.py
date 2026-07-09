"""The environment plugin registry — assembled explicitly from one module per plugin.

Each opt-in mechanism a scenario can request under ``[scenario.environment_plugins]`` lives in its own
module (definition + helpers + deps); ``build_registry`` assembles them into the dict that
``__main__`` injects into the parser and the engine. To add a plugin: add a module here, then add one
line in ``build_registry``.

The ``mcp_server`` plugin closes over its server root at construction time, so the registry cannot
be a static constant — it is built by the composition root (``__main__``) which knows the concrete
paths. The abstraction (``EnvironmentPlugin``, ``RunPlan``, ``RunContext``) lives in :mod:`.base`;
importing it does not pull in the concretes, so the parser and engine depend only on the contract.
"""

from pathlib import Path

from . import fixture_server, git_repo, mcp_server, worktree
from .base import EnvironmentPlugin


def build_registry(mcp_server_root: Path) -> dict[str, EnvironmentPlugin]:
    """Assemble the environment plugin registry, composing ``mcp_server`` with its server root.

    Called by the composition root (``__main__``) which knows the concrete paths.
    """
    return {
        "fixture_server": fixture_server.ENVIRONMENT_PLUGIN,
        "mcp_server": mcp_server.make_plugin(mcp_server_root),
        "git_repo": git_repo.ENVIRONMENT_PLUGIN,
        "worktree": worktree.ENVIRONMENT_PLUGIN,
    }
