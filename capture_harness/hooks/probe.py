#!/usr/bin/env python3
"""Language-agnostic capture probe for the cc-flyrig.

Registered as a ``command`` hook on every captured event (wired by the orchestrator per scenario). For each
invocation it records the raw stdin payload to a spool directory so the consolidation step can build
a versioned ``captures/`` tree. It is intentionally:

* **Standalone** — stdlib only, and it never imports ``cc_flyrig``. A capture session runs it
  as a bare ``python3 probe.py`` hook in a sandbox with no editable install or ``PYTHONPATH`` set up,
  so it must not depend on the package being importable.
* **Passive** — it always exits 0 and writes nothing to stdout. It records inputs only and never
  gates, alters, or decides a tool call (a core toolkit constraint). It is therefore *not* registered
  on ``WorktreeCreate``, whose command hook must print a path on stdout or creation fails.
* **Fail-safe** — any error (missing env, unreadable stdin, unwritable spool) results in a clean
  ``exit 0`` with empty stdout, so the probe can never break a real session it is observing.

Configuration comes from environment variables injected by the orchestrator (inherited by the hook
process): ``FLYRIG_SPOOL_DIR`` (where to write; if unset the probe is a no-op), ``FLYRIG_CC_VERSION``, and
``FLYRIG_RUN_ID``.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone


def _safe(name: str) -> str:
    """Reduce a value to a filesystem-safe token for use in a spool filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "x"


def _record(spool_dir: str, payload: dict) -> None:
    """Write one envelope file per invocation, atomically (temp + os.replace)."""
    event = payload.get("hook_event_name") or "Unknown"
    run_id = os.environ.get("FLYRIG_RUN_ID") or "norun"
    envelope = {
        "cc_version": os.environ.get("FLYRIG_CC_VERSION") or "unknown",
        "event": event,
        "tool_name": payload.get("tool_name"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "payload": payload,
    }
    os.makedirs(spool_dir, exist_ok=True)
    # One unique filename per invocation -> race-free under parallel hook fan-out. The temp+replace
    # keeps a concurrent consolidator from ever reading a half-written file.
    final = os.path.join(spool_dir, f"{_safe(event)}__{_safe(run_id)}__{os.getpid()}__{uuid.uuid4().hex}.json")
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
