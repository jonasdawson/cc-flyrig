#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "TeammateIdle": [{ "type": "command", "command": "python -m <pkg>.teammate_idle" }] }

import sys
from ._harness import TeammateIdleInput, TeammateIdleOutput, run


def handle(event: TeammateIdleInput) -> TeammateIdleOutput | None:
    """Decide what to do with this TeammateIdle event.

    Return a TeammateIdleOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
