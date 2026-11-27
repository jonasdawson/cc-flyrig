#!/usr/bin/env python3
# Edit handle() with your hook logic.
# Wire into settings.json: { "PreSkillShellCommand": [{ "type": "command", "command": "python -m <pkg>.pre_skill_shell_command" }] }

import sys
from ._harness import PreSkillShellCommandInput, PreSkillShellCommandOutput, run


def handle(event: PreSkillShellCommandInput) -> PreSkillShellCommandOutput | None:
    """Decide what to do with this PreSkillShellCommand event.

    Return a PreSkillShellCommandOutput to issue a decision, or None to defer to other hooks.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(run(handle))
