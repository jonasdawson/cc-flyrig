"""Integration tests for the MCP elicitation probe server (capture_harness/servers/mcp_elicit_server.py).

Driven via injected stdin/stdout (StringIO) — exercises the full server event loop against the
real implementation. The server is imported directly by file path via importlib (it is a standalone
script, not a package member).
"""

import importlib.util
import json
from io import StringIO
from pathlib import Path

_SERVER_PATH = Path(__file__).parent.parent.parent.parent / "capture_harness" / "servers" / "mcp_elicit_server.py"
_spec = importlib.util.spec_from_file_location("mcp_elicit_server", _SERVER_PATH)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _send(*messages: dict) -> list[dict]:
    """Run the server with the given messages as stdin; return parsed stdout lines."""
    stdin = StringIO("\n".join(json.dumps(m) for m in messages) + "\n")
    stdout = StringIO()
    srv.main(stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


class TestMcpElicitServer:
    def test_mcp_elicit_server__initialize__declares_elicitation_and_tools_capability(self):
        """P8: initialize response advertises capabilities.elicitation + capabilities.tools + protocol 2025-03-26."""
        outputs = _send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        assert len(outputs) == 1
        result = outputs[0]["result"]
        assert result["protocolVersion"] == "2025-03-26"
        assert result["capabilities"]["elicitation"] == {}
        assert result["capabilities"]["tools"] == {}
        assert outputs[0]["id"] == 1

    def test_mcp_elicit_server__tools_list__returns_probe_elicit(self):
        """P8: tools/list returns exactly one tool named probe_elicit."""
        outputs = _send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert len(outputs) == 1
        tools = outputs[0]["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "probe_elicit"

    def test_mcp_elicit_server__tools_call__emits_elicitation_create_then_returns(self):
        """P8: tools/call probe_elicit emits elicitation/create, then returns a tool result on response."""
        fixed_id = "test-elicit-1"
        id_gen = lambda: fixed_id  # noqa: E731

        stdin = StringIO(
            "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "probe_elicit", "arguments": {}},
                        }
                    ),
                    # Pre-feed the host's elicitation response so the server unblocks.
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": fixed_id,
                            "result": {"action": "submit", "content": {"value": "capture-value"}},
                        }
                    ),
                ]
            )
            + "\n"
        )
        stdout = StringIO()
        srv.main(stdin=stdin, stdout=stdout, id_gen=id_gen)

        outputs = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        assert outputs[0]["id"] == 1  # initialize response
        elicit_req = outputs[1]
        assert elicit_req["method"] == "elicitation/create"
        assert elicit_req["id"] == fixed_id
        schema = elicit_req["params"]["requestedSchema"]
        assert "value" in schema["properties"]
        tool_result = outputs[2]
        assert tool_result["id"] == 2
        assert tool_result["result"]["isError"] is False
        assert "capture-value" in tool_result["result"]["content"][0]["text"]

    def test_mcp_elicit_server__notifications__silently_ignored(self):
        """P8: notifications (no id field) produce no response."""
        outputs = _send(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert len(outputs) == 1
        assert outputs[0]["id"] == 1
