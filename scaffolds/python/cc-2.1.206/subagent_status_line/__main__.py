#!/usr/bin/env python3
# Edit handle() with your logic.
# Wire into settings.json (a single command, not a hook array): { "subagentStatusLine": { "type": "command", "command": "python -m <pkg>.subagent_status_line" } }

import sys
from ._harness import SubagentStatusLineInput, SubagentStatusLineOutput, run


def handle(event: SubagentStatusLineInput) -> list[SubagentStatusLineOutput]:
    """Return one SubagentStatusLineOutput row per visible subagent for this SubagentStatusLine event."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
