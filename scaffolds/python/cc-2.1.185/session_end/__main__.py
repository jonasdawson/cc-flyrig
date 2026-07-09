#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "SessionEnd": [{ "type": "command", "command": "python -m <pkg>.session_end" }] }

import sys
from ._harness import SessionEndInput, run


def handle(event: SessionEndInput) -> None:
    """React to this SessionEnd event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
