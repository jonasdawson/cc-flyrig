#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PreToolUse": [{ "type": "command", "command": "python -m <pkg>.pre_tool_use" }] }

import sys
from ._harness import PreToolUseInput, PreToolUseOutput, run


def handle(event: PreToolUseInput) -> PreToolUseOutput | None:
    """Decide what to do with this PreToolUse event.

    Return a PreToolUseOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
