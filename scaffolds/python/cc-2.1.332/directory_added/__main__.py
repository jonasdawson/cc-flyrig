#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "DirectoryAdded": [{ "type": "command", "command": "python -m <pkg>.directory_added" }] }

import sys
from ._harness import DirectoryAddedInput, run


def handle(event: DirectoryAddedInput) -> None:
    """React to this DirectoryAdded event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
