"""Detect the installed Claude Code version."""

import re
import subprocess

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def detect_cc_version(bin: str = "claude", *, run=None) -> str:
    """Return the ``X.Y.Z`` version from ``<bin> --version``; raise ``ValueError`` if unparseable."""
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True, check=False))
    proc = run([bin, "--version"])
    text = f"{getattr(proc, 'stdout', '')}\n{getattr(proc, 'stderr', '')}"
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError(f"could not parse CC version from: {text!r}")
    return match.group(1)
