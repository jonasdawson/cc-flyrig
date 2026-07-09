#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PermissionRequest": [{ "type": "command", "command": "python -m <pkg>.permission_request" }] }

import sys
from ._harness import PermissionRequestInput, PermissionRequestOutput, run


def handle(event: PermissionRequestInput) -> PermissionRequestOutput | None:
    """Decide what to do with this PermissionRequest event.

    Return a PermissionRequestOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
