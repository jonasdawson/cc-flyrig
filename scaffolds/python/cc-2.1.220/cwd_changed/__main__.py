#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "CwdChanged": [{ "type": "command", "command": "python -m <pkg>.cwd_changed" }] }

import sys
from ._harness import CwdChangedInput, CwdChangedOutput, run


def handle(event: CwdChangedInput) -> CwdChangedOutput | None:
    """Decide what to do with this CwdChanged event.

    Return a CwdChangedOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
