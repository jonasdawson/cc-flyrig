#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "WorktreeRemove": [{ "type": "command", "command": "python -m <pkg>.worktree_remove" }] }

import sys
from ._harness import WorktreeRemoveInput, run


def handle(event: WorktreeRemoveInput) -> None:
    """React to this WorktreeRemove event. Fill in your logic."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
