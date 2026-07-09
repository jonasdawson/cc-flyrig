#!/usr/bin/env python3
"""Passive capture probe for the ``statusLine`` surface (Group 1, U2).

Wired via the ``statusLine`` settings key (not ``hooks``).
Mirrors ``capture_harness/hooks/probe.py`` byte-for-byte in shape:
same ``FLYRIG_SPOOL_DIR`` / ``FLYRIG_CC_VERSION`` / ``FLYRIG_RUN_ID`` env contract, same temp-then-
``os.replace`` spool write, same fail-safe-to-exit-0 discipline. It is intentionally:

* **Standalone** — stdlib only, never imports ``cc_flyrig``.
* **Passive** — always exits 0 and prints nothing to stdout. ``statusLine`` output is normally the
  freeform status text CC renders; an empty line here means nothing is displayed for this probe run,
  which is fine for capture (the point is to observe the *input*, not to render anything) and — per
  the evolution's Q7 note — sidesteps any collision with the orchestrator's own pane markers.
* **Fail-safe** — any error (missing env, unreadable stdin, unwritable spool) results in a clean
  ``exit 0`` with empty stdout.

This module is a sibling to the hooks probe, not a variant of it: status line is not a hook (ADR
0010), so it gets its own spool tag (``StatusLine``) and lives outside ``capture_harness/hooks/``.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

TAG = "StatusLine"


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
    # Always exit 0 with empty stdout, regardless of what happened.
    sys.exit(main())
