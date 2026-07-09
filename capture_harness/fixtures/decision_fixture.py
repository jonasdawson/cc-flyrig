#!/usr/bin/env python3
"""Parameterized decision fixture for prototype scenarios.

Registered as a ``command`` hook by the prototype runner. Reads the desired decision JSON from
``FLYRIG_FIXTURE_DECISION`` and writes it to stdout so Claude Code acts on it. Stdlib only; never
imports cc_flyrig.

Fail-safe: missing env var or invalid JSON → write nothing to stdout, exit 0 (passive, never gates).
"""

import json
import os
import sys


def main() -> None:
    decision_raw = os.environ.get("FLYRIG_FIXTURE_DECISION", "")
    exit_code = int(os.environ.get("FLYRIG_FIXTURE_EXIT_CODE", "0"))
    sys.stdin.read()  # consume invocation so CC doesn't hang
    if decision_raw:
        try:
            json.loads(decision_raw)  # valid JSON: write as-is
            sys.stdout.write(decision_raw)
        except json.JSONDecodeError:
            # Bare string (e.g. a worktree path): print verbatim
            sys.stdout.write(decision_raw)
    sys.exit(exit_code)


main()
