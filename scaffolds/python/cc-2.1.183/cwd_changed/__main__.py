#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "CwdChanged": [{ "type": "command", "command": "python -m <pkg>.cwd_changed" }] }

import sys
from ._harness import CwdChangedInput, run


def handle(event: CwdChangedInput) -> None:
    """React to this CwdChanged event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
