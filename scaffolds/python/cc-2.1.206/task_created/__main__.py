#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "TaskCreated": [{ "type": "command", "command": "python -m <pkg>.task_created" }] }

import sys
from ._harness import TaskCreatedInput, TaskCreatedOutput, run


def handle(event: TaskCreatedInput) -> TaskCreatedOutput | None:
    """Decide what to do with this TaskCreated event.

    Return a TaskCreatedOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
