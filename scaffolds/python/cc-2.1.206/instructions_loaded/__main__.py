#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "InstructionsLoaded": [{ "type": "command", "command": "python -m <pkg>.instructions_loaded" }] }

import sys
from ._harness import InstructionsLoadedInput, run


def handle(event: InstructionsLoadedInput) -> None:
    """React to this InstructionsLoaded event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
