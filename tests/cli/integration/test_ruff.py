"""Seam tests for the ruff CLI wrapper (cli.ruff), exercised against the real ``ruff`` binary.

These verify the wrapper's stdin/stdout plumbing and its raise-on-invalid-source contract — the
two things codegen's formatting step depends on — not ruff's own formatting behavior.
"""

import shutil
import subprocess

import pytest

from cc_flyrig.cli import ruff

pytestmark = pytest.mark.skipif(
    not shutil.which("ruff"),
    reason="ruff not installed (it is a dev dependency — sync the dev environment)",
)


class TestFormat:
    def test_format__unformatted_source__normalizes_it(self):
        assert ruff.format("x=1\n") == "x = 1\n"

    def test_format__invalid_python__raises_called_process_error(self):
        with pytest.raises(subprocess.CalledProcessError):
            ruff.format("x = = 1\n")
