#!/usr/bin/env python3
"""Worktree capture shim for the cc-flyrig (P7 — maintainer capture tooling).

Registered as a ``command`` hook on ``WorktreeCreate`` in place of the passive probe, which cannot
be used here: the ``WorktreeCreate`` command hook MUST print an absolute directory path on stdout
or CC aborts worktree creation. This shim satisfies that contract and also spools the payload.

The path is printed FIRST so the contract is met even if spooling fails. Like probe.py: stdlib
only, never imports ``cc_flyrig``, always exits 0.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "x"


def _make_worktree_dir(spool_dir: str | None, name_slug: str) -> str:
    """Create and return the absolute path for the worktree directory."""
    if spool_dir:
        try:
            root = Path(spool_dir).parent / "worktrees" / name_slug
            root.mkdir(parents=True, exist_ok=True)
            return str(root.resolve())
        except OSError:
            pass
    return tempfile.mkdtemp(prefix="flyrig_worktree_")


def _record(spool_dir: str, payload: dict) -> None:
    """Write one envelope file to the spool (same format as probe.py)."""
    event = payload.get("hook_event_name") or "WorktreeCreate"
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
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
    except BaseException:
        payload = {}

    name_slug = _safe(str(payload.get("name", "worktree")))
    worktree_dir = _make_worktree_dir(spool_dir, name_slug)

    # Print the absolute path first — this is the load-bearing contract for WorktreeCreate.
    print(worktree_dir, flush=True)

    if spool_dir:
        try:
            _record(spool_dir, payload)
        except BaseException:
            pass  # best-effort; the path has already been emitted

    return 0


if __name__ == "__main__":
    sys.exit(main())
