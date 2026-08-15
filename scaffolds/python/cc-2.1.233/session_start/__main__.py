#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "SessionStart": [{ "type": "command", "command": "python -m <pkg>.session_start" }] }

import sys
from ._harness import SessionStartInput, SessionStartOutput, run


def handle(event: SessionStartInput) -> SessionStartOutput | None:
    """Decide what to do with this SessionStart event.

    Return a SessionStartOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
