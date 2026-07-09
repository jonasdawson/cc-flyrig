#!/usr/bin/env python3
"""MCP elicitation probe server for the cc-flyrig (P8 — maintainer capture tooling).

A minimal stdlib MCP JSON-RPC 2.0 server over stdio. Exposes one tool (``probe_elicit``) that
calls ``elicitation/create`` mid-invocation, causing CC to fire the ``Elicitation`` and
``ElicitationResult`` hooks. Never part of a generated scaffold; exists only to drive capture.

Registered per-scenario via ``--mcp-config`` (not the shared probe settings). Protocol: MCP
spec 2025-03-26 (the version that introduced elicitation). Transport: newline-delimited JSON-RPC
over stdio with no Content-Length framing.
"""

import json
import sys
import uuid

_TOOL = {
    "name": "probe_elicit",
    "description": "Sends an elicitation/create request to the host to capture the Elicitation hook.",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}

_ELICIT_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string", "title": "Value"}},
    "required": ["value"],
}


def _handle_tools_call(request_id: object, *, stdin, write, id_gen) -> None:
    """Send elicitation/create, block for the response, then return the tools/call result."""
    elicit_id = id_gen()
    write(
        {
            "jsonrpc": "2.0",
            "id": elicit_id,
            "method": "elicitation/create",
            "params": {
                "message": "Enter a value for the capture probe",
                "requestedSchema": _ELICIT_SCHEMA,
            },
        }
    )
    # Block until we receive the matching response from the host.
    received = ""
    while True:
        line = stdin.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("id") == elicit_id:
            received = json.dumps(msg.get("result", {}))
            break
    write(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": received}], "isError": False},
        }
    )


def main(stdin=None, stdout=None, id_gen=None) -> None:
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout
    if id_gen is None:
        id_gen = lambda: f"elicit-{uuid.uuid4().hex[:8]}"  # noqa: E731

    def write(obj: dict) -> None:
        print(json.dumps(obj), file=stdout, flush=True)

    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"elicitation": {}, "tools": {}},
                        "serverInfo": {"name": "flyrig-elicit-probe", "version": "1.0.0"},
                    },
                }
            )
        elif method == "tools/list":
            write({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [_TOOL]}})
        elif method == "tools/call":
            _handle_tools_call(msg_id, stdin=stdin, write=write, id_gen=id_gen)
        # Notifications (no id) and unknown methods are silently ignored.


if __name__ == "__main__":
    main()
