#!/usr/bin/env python3
"""Passive capture probe for the ``subagentStatusLine`` surface (Group 1, U2).

Sibling to ``probe.py`` (this dir) — same stdlib-only, fail-safe, ``FLYRIG_*``-env-driven, temp-then-
``os.replace`` spool discipline — but tagged ``SubagentStatusLine`` so consolidation (Group 2) can
keep the two statusline surfaces' captures apart. Wired via the ``subagentStatusLine`` settings key.

``subagentStatusLine`` output is typed JSON-lines rows (``{"id","content"}`` per visible subagent),
unlike ``statusLine``'s freeform text — but this probe emits **inputs only**, so it prints an empty
JSON-lines body: no output rows, i.e. no lines at all. That renders no per-subagent row for this
probe run, which is fine for capture purposes.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

TAG = "SubagentStatusLine"


def _safe(name: str) -> str:
    """Reduce a value to a filesystem-safe token for use in a spool filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "x"


def _record(spool_dir: str, payload: dict) -> None:
    """Write one envelope file per invocation, atomically (temp + os.replace)."""
    run_id = os.environ.get("FLYRIG_RUN_ID") or "norun"
    envelope = {
        "cc_version": os.environ.get("FLYRIG_CC_VERSION") or "unknown",
        "event": TAG,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "payload": payload,
    }
    os.makedirs(spool_dir, exist_ok=True)
    final = os.path.join(spool_dir, f"{_safe(TAG)}__{_safe(run_id)}__{os.getpid()}__{uuid.uuid4().hex}.json")
    fd, tmp = tempfile.mkstemp(dir=spool_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh, ensure_ascii=False)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    spool_dir = os.environ.get("FLYRIG_SPOOL_DIR")
    if not spool_dir:
        return 0  # not running under the orchestrator: do nothing.
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
        _record(spool_dir, payload)
    except BaseException:
        # Never let an observability probe disturb the session it is watching.
        return 0
    return 0


if __name__ == "__main__":
    # Always exit 0 with an empty JSON-lines body (no rows), regardless of what happened.
    sys.exit(main())
