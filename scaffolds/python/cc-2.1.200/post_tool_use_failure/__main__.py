#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PostToolUseFailure": [{ "type": "command", "command": "python -m <pkg>.post_tool_use_failure" }] }

import sys
from ._harness import PostToolUseFailureInput, PostToolUseFailureOutput, run


def handle(event: PostToolUseFailureInput) -> PostToolUseFailureOutput | None:
    """Decide what to do with this PostToolUseFailure event.

    Return a PostToolUseFailureOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
