#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PermissionDenied": [{ "type": "command", "command": "python -m <pkg>.permission_denied" }] }

import sys
from ._harness import PermissionDeniedInput, PermissionDeniedOutput, run


def handle(event: PermissionDeniedInput) -> PermissionDeniedOutput | None:
    """Decide what to do with this PermissionDenied event.

    Return a PermissionDeniedOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
