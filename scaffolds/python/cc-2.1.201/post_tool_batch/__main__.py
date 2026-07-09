#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PostToolBatch": [{ "type": "command", "command": "python -m <pkg>.post_tool_batch" }] }

import sys
from ._harness import PostToolBatchInput, PostToolBatchOutput, run


def handle(event: PostToolBatchInput) -> PostToolBatchOutput | None:
    """Decide what to do with this PostToolBatch event.

    Return a PostToolBatchOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
