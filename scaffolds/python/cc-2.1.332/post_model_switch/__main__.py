#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PostModelSwitch": [{ "type": "command", "command": "python -m <pkg>.post_model_switch" }] }

import sys
from ._harness import PostModelSwitchInput, PostModelSwitchOutput, run


def handle(event: PostModelSwitchInput) -> PostModelSwitchOutput | None:
    """Decide what to do with this PostModelSwitch event.

    Return a PostModelSwitchOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
