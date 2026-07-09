"""Integration tests for the tsc CLI wrapper (cli.tsc) — exercises the real ``tsc`` binary."""

import subprocess
from pathlib import Path

import pytest

from cc_flyrig.cli import tsc

ROOT = Path(__file__).parent.parent.parent.parent
TSC = ROOT / "node_modules" / ".bin" / "tsc"
TYPES_NODE = ROOT / "node_modules" / "@types" / "node"

pytestmark = pytest.mark.skipif(
    not (TSC.exists() and TYPES_NODE.exists()),
    reason="typescript / @types/node not installed (run `npm install`)",
)


class TestCheckPaths:
    def test_check_paths__well_typed_file__returns_none(self, tmp_path):
        file = tmp_path / "ok.ts"
        file.write_text("const x: number = 1;\n")
        assert tsc.check_paths([file]) is None

    def test_check_paths__type_error__raises_called_process_error(self, tmp_path):
        file = tmp_path / "bad.ts"
        file.write_text('const x: number = "s";\n')
        with pytest.raises(subprocess.CalledProcessError):
            tsc.check_paths([file])
