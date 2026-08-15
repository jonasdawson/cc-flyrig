#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "StopFailure": [{ "type": "command", "command": "python -m <pkg>.stop_failure" }] }

import sys
from ._harness import StopFailureInput, run


def handle(event: StopFailureInput) -> None:
    """React to this StopFailure event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
