"""Wrapper over the ``tsc`` command-line tool."""

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

# Flags rather than a committed tsconfig: the scaffolds are author-delivered fragments (no project
# of their own). Bundler resolution allows the extensionless `./_harness` import; `--types node`
# pulls in the node:fs / process declarations the harness uses.
_FLAGS = [
    "--noEmit",
    "--strict",
    "--skipLibCheck",
    "--target",
    "ES2020",
    "--module",
    "ESNext",
    "--moduleResolution",
    "Bundler",
    "--types",
    "node",
]


def _binary() -> str:
    """Resolve tsc: repo-local node_modules/.bin first, then PATH. Windows installs a .cmd shim."""
    local = Path("node_modules") / ".bin" / ("tsc.cmd" if os.name == "nt" else "tsc")
    if local.exists():
        return str(local)
    if found := shutil.which("tsc"):
        return found
    raise FileNotFoundError(
        "tsc not found — run `npm install` at the repo root; "
        "it type-checks generated TypeScript in tests and at release time"
    )


def check_paths(files: Sequence[Path]) -> None:
    """Batched ``tsc --noEmit`` over ``files``; raises ``CalledProcessError`` on type errors."""
    subprocess.run([_binary(), *_FLAGS, *(str(f) for f in files)], check=True)
