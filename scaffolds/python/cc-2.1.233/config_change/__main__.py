#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "ConfigChange": [{ "type": "command", "command": "python -m <pkg>.config_change" }] }

import sys
from ._harness import ConfigChangeInput, ConfigChangeOutput, run


def handle(event: ConfigChangeInput) -> ConfigChangeOutput | None:
    """Decide what to do with this ConfigChange event.

    Return a ConfigChangeOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
