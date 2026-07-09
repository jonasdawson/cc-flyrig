"""Integration tests for the esbuild CLI wrapper (cli.esbuild) — exercises the real ``esbuild`` binary."""

import shutil
import subprocess
from pathlib import Path

import pytest

from cc_flyrig.cli import esbuild

ROOT = Path(__file__).parent.parent.parent.parent
LOCAL_ESBUILD = ROOT / "node_modules" / ".bin" / "esbuild"

pytestmark = pytest.mark.skipif(
    not (LOCAL_ESBUILD.exists() or shutil.which("esbuild")),
    reason="esbuild not installed (run `npm install`)",
)


class TestCheck:
    def test_check__valid_typescript__returns_none(self):
        assert esbuild.check("const x: number = 1;\n") is None

    def test_check__type_only_constructs__pass(self):
        source = "interface Foo { a?: number }\ntype Bar = string | number;\nconst x: Bar = 1;\n"
        assert esbuild.check(source) is None

    def test_check__unbalanced_brace__raises_called_process_error(self):
        with pytest.raises(subprocess.CalledProcessError):
            esbuild.check("function foo() {\n")
