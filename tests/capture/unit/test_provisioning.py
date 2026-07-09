"""Tests for cc_flyrig.capture.provisioning (U1–U3) and the CLI surface (U2)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cc_flyrig.capture.orchestrator.scenario_runner import CaptureError
from cc_flyrig.capture.provisioning import isolation_env, provision


class TestProvision:
    def test_provision__npm_method__installs_to_versioned_prefix(self, tmp_path):
        """provision with method='npm' calls npm install with the versioned --prefix and
        returns a ClaudeInstall whose bin is rooted under that prefix."""
        run_mock = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
        with patch(
            "cc_flyrig.capture.provisioning.detect_cc_version",
            return_value="2.1.183",
        ):
            install = provision("2.1.183", root=tmp_path, method="npm", run=run_mock)

        run_mock.assert_called_once()
        cmd = run_mock.call_args[0][0]
        assert cmd[0] == "npm"
        assert "--prefix" in cmd
        prefix_idx = cmd.index("--prefix")
        assert cmd[prefix_idx + 1] == str(tmp_path / "2.1.183")
        assert "@anthropic-ai/claude-code@2.1.183" in cmd

        assert install.bin == str(tmp_path / "2.1.183" / "bin" / "claude")
        assert install.version == "2.1.183"

    def test_provision__any_method__sets_isolation_env(self, tmp_path):
        """isolation_env returns CLAUDE_CONFIG_DIR, DISABLE_AUTOUPDATER, and DISABLE_UPDATES
        scoped to the versioned prefix."""
        env = isolation_env("2.1.183", root=tmp_path)

        assert env["DISABLE_AUTOUPDATER"] == "1"
        assert env["DISABLE_UPDATES"] == "1"
        assert "CLAUDE_CONFIG_DIR" in env
        assert "2.1.183" in env["CLAUDE_CONFIG_DIR"]

    def test_provision__version_mismatch__raises_capture_error(self, tmp_path):
        """provision raises CaptureError when the installed binary reports a different version
        than was requested (pin-assertion guard)."""
        run_mock = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
        with patch(
            "cc_flyrig.capture.provisioning.detect_cc_version",
            return_value="2.1.999",
        ):
            with pytest.raises(CaptureError, match="provisioned '2.1.999', expected '2.1.183'"):
                provision("2.1.183", root=tmp_path, method="npm", run=run_mock)


class TestProvisionCommand:
    def test_provision_command__success__prints_bin_path(self, tmp_path, capsys):
        """The 'provision' CLI subcommand prints only the resolved bin path on stdout."""
        from cc_flyrig.capture.__main__ import main

        mock_install = MagicMock()
        mock_install.bin = str(tmp_path / "2.1.183" / "bin" / "claude")

        with patch("cc_flyrig.capture.__main__.provision", return_value=mock_install) as mock_prov:
            rc = main(["provision", "2.1.183", "--root", str(tmp_path)])

        assert rc == 0
        mock_prov.assert_called_once_with("2.1.183", root=Path(str(tmp_path)), method="npm")
        out = capsys.readouterr().out
        assert out.strip() == str(tmp_path / "2.1.183" / "bin" / "claude")


class TestRunExplicitClaudeBin:
    def test_inputs_command__explicit_claude_bin__does_not_provision(self, tmp_path):
        """`inputs` (today's former default) skips inline provisioning when --claude-bin is
        explicit, even with --cc-version given. Uses the `inputs` subcommand rather than the bare
        default so this test exercises only the input battery — the bare default now also drives
        the output battery via _cmd_all, which is covered separately in test_main.py."""
        from cc_flyrig.capture.__main__ import main

        with (
            patch("cc_flyrig.capture.__main__.provision") as mock_prov,
            patch(
                "cc_flyrig.capture.__main__.detect_cc_version",
                return_value="2.1.183",
            ),
            patch(
                "cc_flyrig.capture.__main__.scan_hooks_menu",
                return_value=([], ""),
            ),
            patch("cc_flyrig.capture.__main__.drift_detector") as mock_dd,
            patch("cc_flyrig.capture.__main__.build_registry", return_value={}),
            patch("cc_flyrig.capture.__main__.parse_manifest") as mock_pm,
            patch("cc_flyrig.capture.__main__.run_scenarios", return_value=[]),
            patch("cc_flyrig.capture.__main__._render_hooks_menu"),
            patch("cc_flyrig.capture.__main__._write_menu_artifacts"),
        ):
            mock_dd.check_documented_events.return_value = []
            mock_pm.return_value = MagicMock(scenarios=[])
            captures = tmp_path / "captures"
            captures.mkdir()

            rc = main(
                [
                    "inputs",
                    "--claude-bin",
                    "/usr/local/bin/claude",
                    "--cc-version",
                    "2.1.183",
                    "--captures",
                    str(captures),
                    "--spool",
                    str(tmp_path / "spool"),
                    "--sandbox",
                    str(tmp_path / "sandbox"),
                ]
            )

        mock_prov.assert_not_called()
        assert rc == 0
