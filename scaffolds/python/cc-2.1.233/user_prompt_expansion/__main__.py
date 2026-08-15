#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "UserPromptExpansion": [{ "type": "command", "command": "python -m <pkg>.user_prompt_expansion" }] }

import sys
from ._harness import UserPromptExpansionInput, UserPromptExpansionOutput, run


def handle(event: UserPromptExpansionInput) -> UserPromptExpansionOutput | None:
    """Decide what to do with this UserPromptExpansion event.

    Return a UserPromptExpansionOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
