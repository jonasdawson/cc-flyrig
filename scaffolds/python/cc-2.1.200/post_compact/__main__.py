#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PostCompact": [{ "type": "command", "command": "python -m <pkg>.post_compact" }] }

import sys
from ._harness import PostCompactInput, run


def handle(event: PostCompactInput) -> None:
    """React to this PostCompact event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
