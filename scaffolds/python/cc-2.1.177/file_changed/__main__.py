#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "FileChanged": [{ "type": "command", "command": "python -m <pkg>.file_changed" }] }

import sys
from ._harness import FileChangedInput, run


def handle(event: FileChangedInput) -> None:
    """React to this FileChanged event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
