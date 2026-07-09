"""P8: register a per-scenario MCP server via ``--mcp-config`` / ``--strict-mcp-config``.

``mcp_elicit_server.py`` exposes ``probe_elicit`` and calls ``elicitation/create`` from within
``tools/call``, so CC fires ``Elicitation`` / ``ElicitationResult``. The server is per-scenario (not in
the shared probe settings), so it is absent from all other scenarios.
"""

import json
from pathlib import Path

from .base import EnvironmentPlugin, require_one_of

# registry key -> stdlib server module filename (resolved from capture_harness/servers/ at run time).
_SERVERS = {"elicit-probe": "mcp_elicit_server.py"}


def _flags(server_root: Path, sandbox: Path, server: str) -> list[str]:
    """Write ``<sandbox>/mcp-config.json`` for the server; return the argv flags."""
    server_path = str((server_root / _SERVERS[server]).resolve())
    config = {"mcpServers": {server: {"command": "python3", "args": [server_path]}}}
    out = sandbox / "mcp-config.json"
    out.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return ["--mcp-config", str(out), "--strict-mcp-config"]


def make_plugin(server_root: Path) -> EnvironmentPlugin:
    """Return an environment plugin that wires an MCP server from ``server_root``."""

    def _configure(v, ctx, plan):
        plan.extra_argv.extend(_flags(server_root, ctx.sandbox, str(v)))

    return EnvironmentPlugin(
        validate=lambda v: require_one_of(_SERVERS, v),
        configure=_configure,
    )
