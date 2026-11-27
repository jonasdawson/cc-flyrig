#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "FileChanged": [{ "type": "command", "command": "python -m <pkg>.file_changed" }] }

import sys
from ._harness import FileChangedInput, FileChangedOutput, run


def handle(event: FileChangedInput) -> FileChangedOutput | None:
    """Decide what to do with this FileChanged event.

    Return a FileChangedOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
