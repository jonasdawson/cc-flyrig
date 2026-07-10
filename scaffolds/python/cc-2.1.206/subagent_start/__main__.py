#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "SubagentStart": [{ "type": "command", "command": "python -m <pkg>.subagent_start" }] }

import sys
from ._harness import SubagentStartInput, SubagentStartOutput, run


def handle(event: SubagentStartInput) -> SubagentStartOutput | None:
    """Decide what to do with this SubagentStart event.

    Return a SubagentStartOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
