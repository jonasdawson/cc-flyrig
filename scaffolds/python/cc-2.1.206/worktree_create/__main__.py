#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "WorktreeCreate": [{ "type": "command", "command": "python -m <pkg>.worktree_create" }] }

import sys
from ._harness import WorktreeCreateInput, WorktreeCreateOutput, run


def handle(event: WorktreeCreateInput) -> WorktreeCreateOutput | None:
    """Decide what to do with this WorktreeCreate event.

    Return a WorktreeCreateOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
