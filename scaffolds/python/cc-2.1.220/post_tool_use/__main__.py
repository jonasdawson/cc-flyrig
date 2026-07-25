#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PostToolUse": [{ "type": "command", "command": "python -m <pkg>.post_tool_use" }] }

import sys
from ._harness import PostToolUseInput, PostToolUseOutput, run


def handle(event: PostToolUseInput) -> PostToolUseOutput | None:
    """Decide what to do with this PostToolUse event.

    Return a PostToolUseOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
