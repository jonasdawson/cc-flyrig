"""Unit tests for the esbuild CLI wrapper's binary resolution (cli.esbuild._binary)."""

from pathlib import Path

import pytest

from cc_flyrig.cli import esbuild


class TestBinary:
    def test_binary__local_node_modules_present__prefers_local(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / "node_modules" / ".bin"
        local.mkdir(parents=True)
        (local / "esbuild").touch()
        monkeypatch.setattr(esbuild.shutil, "which", lambda _: "/usr/bin/esbuild")

        assert esbuild._binary() == str(Path("node_modules") / ".bin" / "esbuild")

    def test_binary__absent_everywhere__raises_file_not_found_with_npm_install_hint(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(esbuild.shutil, "which", lambda _: None)

        with pytest.raises(FileNotFoundError, match="npm install"):
            esbuild._binary()
