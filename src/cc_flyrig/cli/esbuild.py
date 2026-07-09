"""Wrapper over the ``esbuild`` command-line tool."""

import os
import shutil
import subprocess
from pathlib import Path


def _binary() -> str:
    """Resolve esbuild: repo-local node_modules/.bin first (CWD-relative, matching the codegen
    CLI's repo-root assumption), then PATH. Windows installs a .cmd shim."""
    local = Path("node_modules") / ".bin" / ("esbuild.cmd" if os.name == "nt" else "esbuild")
    if local.exists():
        return str(local)
    if found := shutil.which("esbuild"):
        return found
    raise FileNotFoundError(
        "esbuild not found — run `npm install` at the repo root; "
        "the typescript runtime requires it as its generation-time syntax gate"
    )


def check(source: str) -> None:
    """Syntax-check TypeScript with ``esbuild --loader=ts`` (stdin; transform output discarded).

    Raises ``subprocess.CalledProcessError`` on a syntax error, ``FileNotFoundError`` when esbuild
    is missing. esbuild parses only — type errors are ``cli.tsc``'s job (tests + release).
    """
    subprocess.run([_binary(), "--loader=ts"], input=source, stdout=subprocess.DEVNULL, text=True, check=True)
