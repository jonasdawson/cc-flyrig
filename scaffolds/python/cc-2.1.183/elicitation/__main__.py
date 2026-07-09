#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "Elicitation": [{ "type": "command", "command": "python -m <pkg>.elicitation" }] }

import sys
from ._harness import ElicitationInput, ElicitationOutput, run


def handle(event: ElicitationInput) -> ElicitationOutput | None:
    """Decide what to do with this Elicitation event.

    Return a ElicitationOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
