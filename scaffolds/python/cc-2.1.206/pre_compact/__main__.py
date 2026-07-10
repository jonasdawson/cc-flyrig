#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PreCompact": [{ "type": "command", "command": "python -m <pkg>.pre_compact" }] }

import sys
from ._harness import PreCompactInput, PreCompactOutput, run


def handle(event: PreCompactInput) -> PreCompactOutput | None:
    """Decide what to do with this PreCompact event.

    Return a PreCompactOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
