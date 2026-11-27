#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PreModelSwitch": [{ "type": "command", "command": "python -m <pkg>.pre_model_switch" }] }

import sys
from ._harness import PreModelSwitchInput, PreModelSwitchOutput, run


def handle(event: PreModelSwitchInput) -> PreModelSwitchOutput | None:
    """Decide what to do with this PreModelSwitch event.

    Return a PreModelSwitchOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
