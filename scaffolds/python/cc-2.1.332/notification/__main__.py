#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "Notification": [{ "type": "command", "command": "python -m <pkg>.notification" }] }

import sys
from ._harness import NotificationInput, run


def handle(event: NotificationInput) -> None:
    """React to this Notification event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
