#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "Setup": [{ "type": "command", "command": "python -m <pkg>.setup" }] }

import sys
from ._harness import SetupInput, SetupOutput, run


def handle(event: SetupInput) -> SetupOutput | None:
    """Decide what to do with this Setup event.

    Return a SetupOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
