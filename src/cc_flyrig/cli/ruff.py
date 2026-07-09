"""Wrapper over the ``ruff`` command-line tool."""

import subprocess


def format(source: str) -> str:
    """Normalize Python source with ``ruff format`` (reads stdin, returns the formatted text).

    Raises ``subprocess.CalledProcessError`` if the source is not valid Python (ruff exits non-zero).
    """
    completed = subprocess.run(["ruff", "format", "-"], input=source, capture_output=True, text=True, check=True)
    return completed.stdout
