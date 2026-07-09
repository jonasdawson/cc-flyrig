#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "MessageDisplay": [{ "type": "command", "command": "python -m <pkg>.message_display" }] }

import sys
from ._harness import MessageDisplayInput, MessageDisplayOutput, run


def handle(event: MessageDisplayInput) -> MessageDisplayOutput | None:
    """Decide what to do with this MessageDisplay event.

    Return a MessageDisplayOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
