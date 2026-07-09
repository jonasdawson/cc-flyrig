#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "UserPromptSubmit": [{ "type": "command", "command": "python -m <pkg>.user_prompt_submit" }] }

import sys
from ._harness import UserPromptSubmitInput, UserPromptSubmitOutput, run


def handle(event: UserPromptSubmitInput) -> UserPromptSubmitOutput | None:
    """Decide what to do with this UserPromptSubmit event.

    Return a UserPromptSubmitOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
