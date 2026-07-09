"""Type-check the generated TypeScript scaffolds with ``tsc --noEmit``.

A complement to the round-trip test: this proves the emitted interfaces, type aliases, and
parse/serialize signatures are internally type-consistent (e.g. a field's declared type matches what
``parse``/``serialize`` produce, optionals line up, the ``run(handle)`` signature fits the stub).
``tsc`` catches type errors the round-trip cannot (it exercises only the input path on captured data).

Uses the dev dependencies ``typescript`` + ``@types/node`` (for ``node:fs`` / ``process``); skips
cleanly when either is absent so a Python-only environment stays green.
"""

import subprocess
from pathlib import Path

import pytest

from cc_flyrig.cli import tsc

ROOT = Path(__file__).parent.parent.parent.parent
SCAFFOLDS_TS = ROOT / "scaffolds" / "typescript" / "cc-2.1.185"
SCAFFOLDS_TS_STATUSLINE = ROOT / "scaffolds" / "typescript" / "cc-2.1.198"
TSC = ROOT / "node_modules" / ".bin" / "tsc"
TYPES_NODE = ROOT / "node_modules" / "@types" / "node"

pytestmark = pytest.mark.skipif(
    not (TSC.exists() and TYPES_NODE.exists()),
    reason="typescript / @types/node not installed (run `npm install`)",
)


def test_generated_typescript__committed_scaffolds__type_checks_clean():
    files = sorted(SCAFFOLDS_TS.glob("*/*.ts"))
    assert files, "no generated TypeScript files found"
    try:
        tsc.check_paths(files)
    except subprocess.CalledProcessError as err:
        pytest.fail(f"tsc reported type errors (exit {err.returncode})")


def test_generated_typescript__committed_statusline_scaffolds__type_checks_clean():
    files = sorted(SCAFFOLDS_TS_STATUSLINE.glob("*/*.ts"))
    assert files, "no generated statusline TypeScript files found"
    try:
        tsc.check_paths(files)
    except subprocess.CalledProcessError as err:
        pytest.fail(f"tsc reported type errors (exit {err.returncode})")
