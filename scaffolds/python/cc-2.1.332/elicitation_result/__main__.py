#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "ElicitationResult": [{ "type": "command", "command": "python -m <pkg>.elicitation_result" }] }

import sys
from ._harness import ElicitationResultInput, ElicitationResultOutput, run


def handle(event: ElicitationResultInput) -> ElicitationResultOutput | None:
    """Decide what to do with this ElicitationResult event.

    Return a ElicitationResultOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
