#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "TaskCompleted": [{ "type": "command", "command": "python -m <pkg>.task_completed" }] }

import sys
from ._harness import TaskCompletedInput, TaskCompletedOutput, run


def handle(event: TaskCompletedInput) -> TaskCompletedOutput | None:
    """Decide what to do with this TaskCompleted event.

    Return a TaskCompletedOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
