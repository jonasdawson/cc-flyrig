"""Scrub machine-specific / PII values from a captured hook payload.

Used as the ``on_process_payload`` hook of ``capture.spool_consolidator``: it recursively rewrites
sensitive dict values (session ids, transcript/worktree paths) to fixed placeholders and replaces the
user's home directory in any string value. Only string values change, so a scrubbed payload still
validates against the IR.
"""

import os

# Keys whose values are session/machine specific and must never be committed. Values are replaced by
# fixed placeholders (kept as strings so the payload still validates against the IR).
REDACT_KEYS: dict[str, str] = {
    "session_id": "<SESSION_ID>",
    "transcript_path": "<TRANSCRIPT_PATH>",
    "agent_transcript_path": "<TRANSCRIPT_PATH>",
    # WorktreeCreate/WorktreeRemove carry the absolute worktree dir path; redact for a
    # machine-independent corpus so the committed diff is stable across environments (P7).
    "worktree_path": "<WORKTREE_PATH>",
}


def scrub(value: object, home: str | None = None, redact_keys: dict[str, str] = REDACT_KEYS) -> object:
    """Recursively redact sensitive keys and replace the home directory in any string value.

    ``home`` defaults to the current user's home directory; pass it explicitly (e.g. in tests) to make
    the substitution deterministic.
    """
    if home is None:
        home = os.path.expanduser("~")
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if k in redact_keys:
                out[k] = redact_keys[k]
            else:
                out[k] = scrub(v, home, redact_keys)
        return out
    if isinstance(value, list):
        return [scrub(v, home, redact_keys) for v in value]
    if isinstance(value, str) and home and home in value:
        return value.replace(home, "<HOME>")
    return value
