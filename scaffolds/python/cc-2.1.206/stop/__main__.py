#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "Stop": [{ "type": "command", "command": "python -m <pkg>.stop" }] }

import sys
from ._harness import StopInput, StopOutput, run


def handle(event: StopInput) -> StopOutput | None:
    """Decide what to do with this Stop event.

    Return a StopOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
