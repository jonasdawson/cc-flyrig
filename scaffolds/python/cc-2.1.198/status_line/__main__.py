#!/usr/bin/env python3
# Edit handle() with your logic.
# Wire into settings.json (a single command, not a hook array): { "statusLine": { "type": "command", "command": "python -m <pkg>.status_line" } }

import sys
from ._harness import StatusLineData, run


def handle(event: StatusLineData) -> str:
    """Return the status line text for this StatusLine event."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
