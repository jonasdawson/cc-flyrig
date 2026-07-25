#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "SubagentStop": [{ "type": "command", "command": "python -m <pkg>.subagent_stop" }] }

import sys
from ._harness import SubagentStopInput, SubagentStopOutput, run


def handle(event: SubagentStopInput) -> SubagentStopOutput | None:
    """Decide what to do with this SubagentStop event.

    Return a SubagentStopOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
