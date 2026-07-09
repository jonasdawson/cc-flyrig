"""Tests for the capture CLI (__main__) command dispatch."""

import argparse
import json
from pathlib import Path

import pytest

from cc_flyrig.capture.__main__ import (
    COVERAGE_FILENAME,
    _bucket_spool_events,
    _confirm_menu_change,
    _resolve_refresh_version,
    _write_menu_artifacts,
    main,
    partition_scenarios,
)
from cc_flyrig.capture.orchestrator.scenario_runner import ClaudeInstall, ScenarioResult
from cc_flyrig.schema.drift_detector import Finding

# run is not tested here: scenario_runner tests cover the engine end-to-end with a fake tmux.
# These tests verify that each CLI command routes, imports, and exits correctly.

_MAIN_MODULE = "cc_flyrig.capture.__main__"


def _write_manifest(tmp_path: Path, ids: list[str]) -> Path:
    manifest = tmp_path / "scenarios.toml"
    body = "\n".join(f'[[scenario]]\nid = "{i}"\n' for i in ids)
    manifest.write_text(body, encoding="utf-8")
    return manifest


def _write_output_scenarios(tmp_path: Path, ids: list[str]) -> Path:
    out = tmp_path / "output_scenarios.toml"
    body = "\n".join(f'[[scenarios]]\nid = "{i}"\n' for i in ids)
    out.write_text(body, encoding="utf-8")
    return out


def _write_envelope(
    spool: Path,
    name: str,
    cc_version: str,
    event: str,
    payload: dict | None = None,
    run_id: str = "run1",
) -> Path:
    spool.mkdir(parents=True, exist_ok=True)
    envelope = {
        "cc_version": cc_version,
        "event": event,
        "payload": payload if payload is not None else {},
        "run_id": run_id,
    }
    path = spool / name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


class TestValidateOutputsRemoved:
    def test_validate_outputs__unknown_subcommand__system_exit_2(self):
        """validate-outputs is gone; argparse rejects the unknown subcommand with exit code 2."""
        with pytest.raises(SystemExit) as exc_info:
            main(["validate-outputs"])
        assert exc_info.value.code == 2


class TestSubcommandDispatch:
    def test_inputs__dispatches_to_run_inputs_with_resolved_install(self, monkeypatch):
        install = ClaudeInstall(bin="stub-claude")
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: install)
        seen = {}

        def fake_run_inputs(args, resolved_install):
            seen["install"] = resolved_install
            return 0

        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", fake_run_inputs)

        rc = main(["inputs"])

        assert rc == 0
        assert seen["install"] is install

    def test_outputs__dispatches_to_run_outputs_with_resolved_install(self, monkeypatch):
        install = ClaudeInstall(bin="stub-claude")
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: install)
        seen = {}

        def fake_run_outputs(args, resolved_install):
            seen["install"] = resolved_install
            return 0

        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", fake_run_outputs)

        rc = main(["outputs"])

        assert rc == 0
        assert seen["install"] is install


class TestDefaultRunCombinesBatteries:
    def test_default_run__no_scenario_filter__runs_both_phases_in_order_with_same_install(self, monkeypatch):
        install = ClaudeInstall(bin="shared-claude")
        resolve_calls = []

        def fake_resolve(args):
            resolve_calls.append(args)
            return install

        order = []
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", fake_resolve)
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", lambda args, inst: order.append(("inputs", inst)) or 0)
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", lambda args, inst: order.append(("outputs", inst)) or 0)

        rc = main([])

        assert rc == 0
        assert len(resolve_calls) == 1
        assert order == [("inputs", install), ("outputs", install)]

    def test_default_run__nonzero_input_phase__short_circuits_before_output_phase(self, monkeypatch):
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: ClaudeInstall())
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", lambda args, inst: 1)
        output_called = []
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", lambda args, inst: output_called.append(1) or 0)

        rc = main([])

        assert rc == 1
        assert output_called == []

    def test_default_run__zero_input_phase__propagates_output_phase_rc(self, monkeypatch):
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: ClaudeInstall())
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", lambda args, inst: 0)
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", lambda args, inst: 1)

        rc = main([])

        assert rc == 1


class TestPartitionScenarios:
    def test_empty_request__both_match_lists_empty(self):
        assert partition_scenarios([], {"a"}, {"b"}) == ([], [], [])

    def test_all_input__matches_input_only(self):
        assert partition_scenarios(["a"], {"a", "b"}, {"c"}) == (["a"], [], [])

    def test_all_output__matches_output_only(self):
        assert partition_scenarios(["c"], {"a"}, {"c"}) == ([], ["c"], [])

    def test_mixed__splits_across_both_batteries(self):
        assert partition_scenarios(["a", "c"], {"a"}, {"c"}) == (["a"], ["c"], [])

    def test_unknown_id__reported_and_not_dropped(self):
        assert partition_scenarios(["z"], {"a"}, {"c"}) == ([], [], ["z"])

    def test_id_in_both_sets__goes_to_both_match_lists(self):
        assert partition_scenarios(["x"], {"x"}, {"x"}) == (["x"], ["x"], [])


class TestScenarioFilterDispatch:
    def test_input_only_id__skips_output_battery_with_stderr_note(self, tmp_path, monkeypatch, capsys):
        manifest = _write_manifest(tmp_path, ["in-1", "in-2"])
        output_scenarios = _write_output_scenarios(tmp_path, ["out-1"])
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: ClaudeInstall())
        calls = []
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", lambda args, inst: calls.append("inputs") or 0)
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", lambda args, inst: calls.append("outputs") or 0)

        rc = main(
            [
                "--manifest",
                str(manifest),
                "--output-scenarios",
                str(output_scenarios),
                "--scenario",
                "in-1",
            ]
        )

        assert rc == 0
        assert calls == ["inputs"]
        assert "skipping the output battery" in capsys.readouterr().err

    def test_unknown_id__raises_system_exit(self, tmp_path, monkeypatch):
        manifest = _write_manifest(tmp_path, ["in-1"])
        output_scenarios = _write_output_scenarios(tmp_path, ["out-1"])
        monkeypatch.setattr(f"{_MAIN_MODULE}._resolve_install", lambda args: ClaudeInstall())
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_inputs", lambda args, inst: 0)
        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", lambda args, inst: 0)

        with pytest.raises(SystemExit):
            main(
                [
                    "--manifest",
                    str(manifest),
                    "--output-scenarios",
                    str(output_scenarios),
                    "--scenario",
                    "nope",
                ]
            )


class TestOutputsProvisioningParity:
    def test_cc_version_with_default_claude_bin__provisioned_install_reaches_run_outputs(self, monkeypatch):
        provisioned = ClaudeInstall(bin="/cache/cc/2.1.1/bin/claude")
        monkeypatch.setattr(
            f"{_MAIN_MODULE}.provision",
            lambda version, root, method: provisioned,
        )
        seen = {}

        def fake_run_outputs(args, inst):
            seen["bin"] = inst.bin
            return 0

        monkeypatch.setattr(f"{_MAIN_MODULE}._run_outputs", fake_run_outputs)

        rc = main(["outputs", "--cc-version", "2.1.1"])

        assert rc == 0
        assert seen["bin"] == provisioned.bin


class TestRunInputsFamilySplitSummary:
    def test_run_inputs__mixed_hooks_and_statusline_results__final_summary_splits_by_family(
        self, tmp_path, monkeypatch, capsys
    ):
        """ADR 0012 §5: the input battery's final summary reports hooks and statusline observed
        events separately, rather than lumping both families into one ``observed events:`` line."""
        manifest = _write_manifest(tmp_path, ["s1"])
        monkeypatch.setattr(f"{_MAIN_MODULE}.detect_cc_version", lambda claude_bin: "9.9.9")
        monkeypatch.setattr(f"{_MAIN_MODULE}.scan_hooks_menu", lambda claude_bin, sandbox_root: ([], ""))
        monkeypatch.setattr(f"{_MAIN_MODULE}.drift_detector.check_documented_events", lambda events, source: [])
        monkeypatch.setattr(f"{_MAIN_MODULE}.build_registry", lambda root: {})
        monkeypatch.setattr(f"{_MAIN_MODULE}.parse_manifest", lambda text, registry: argparse.Namespace(scenarios=()))
        monkeypatch.setattr(
            f"{_MAIN_MODULE}.run_scenarios",
            lambda manifest, registry, paths, scenarios, claude: [
                ScenarioResult("s1", "batch:s1", frozenset({"Stop", "PreToolUse", "StatusLine", "SubagentStatusLine"}))
            ],
        )

        rc = main(
            [
                "inputs",
                "--manifest",
                str(manifest),
                "--captures",
                str(tmp_path / "captures"),
                "--spool",
                str(tmp_path / "spool"),
                "--sandbox",
                str(tmp_path / "sandbox"),
            ]
        )

        assert rc == 0
        out = capsys.readouterr().out
        assert "hooks observed: PreToolUse, Stop" in out
        assert "statusline observed: StatusLine, SubagentStatusLine" in out


class TestCommandsRemoved:
    def test_consolidate__unknown_subcommand__system_exit_2(self):
        """consolidate was folded into refresh; argparse rejects it (exit 2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["consolidate"])
        assert exc_info.value.code == 2

    def test_coverage__unknown_subcommand__system_exit_2(self):
        """coverage was folded into refresh; argparse rejects it (exit 2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["coverage"])
        assert exc_info.value.code == 2


def _write_refresh_manifest(tmp_path: Path) -> Path:
    """A minimal manifest that satisfies ``parse_manifest``'s full validation (unlike the
    cheap id-only ``_write_manifest`` used for ``_read_scenario_ids``)."""
    manifest = tmp_path / "refresh_scenarios.toml"
    manifest.write_text('[[scenario]]\nid = "s1"\nprompt = "do a thing"\n', encoding="utf-8")
    return manifest


def _refresh(tmp_path: Path, *, captures: Path, spool: Path, cc_version: str | None = "0.0.1", manifest=None) -> int:
    manifest_path = manifest or _write_refresh_manifest(tmp_path)
    argv = [
        "refresh",
        "--captures",
        str(captures),
        "--spool",
        str(spool),
        "--manifest",
        str(manifest_path),
    ]
    if cc_version is not None:
        argv += ["--cc-version", cc_version]
    return main(argv)


class TestCmdRefreshMergeAndRender:
    def test_hooks_envelope__merges_and_renders_input_coverage(self, tmp_path):
        """A hooks envelope is merged into the captures tree and INPUT_COVERAGE.md is rendered
        in the same invocation — the old ``consolidate`` case plus the render half."""
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        _write_envelope(spool, "0001.json", "0.0.1", "SessionStart", {"session_id": "s1"})

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        cov_dir = captures / "cc-0.0.1"
        assert (cov_dir / "SessionStart.jsonl").exists()
        assert (cov_dir / COVERAGE_FILENAME).exists()

    def test_statusline_envelope__scoped_to_statusline_subtree__hooks_tree_untouched(self, tmp_path):
        """A statusline-only spool merges into the statusline/ subtree and leaves the top-level
        hooks tree alone (the misfiling drift ``consolidate`` used to have)."""
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        _write_envelope(spool, "0001.json", "0.0.1", "StatusLine", {"foo": "bar"})

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        cov_dir = captures / "cc-0.0.1"
        statusline_dir = cov_dir / "statusline"
        assert (statusline_dir / "StatusLine.jsonl").exists()
        assert (statusline_dir / "input_manifest.json").exists()
        assert not (cov_dir / "input_manifest.json").exists()
        assert not list(cov_dir.glob("*.jsonl"))
        assert (statusline_dir / "STATUSLINE_COVERAGE.md").exists()


class TestCmdRefreshClobberGuard:
    def test_statusline_only_spool__preexisting_hooks_manifest_byte_unchanged(self, tmp_path):
        """Regression: a family with zero spooled envelopes must never be consolidated — else the
        unconditional ``input_manifest.json`` write in ``consolidate()`` clobbers a committed
        capture report with an empty one."""
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)
        preexisting = json.dumps({"cc_version": "0.0.1", "events": {"SessionStart": 5}, "total_payloads": 5}, indent=2)
        hooks_manifest = cov_dir / "input_manifest.json"
        hooks_manifest.write_text(preexisting, encoding="utf-8")
        _write_envelope(spool, "0001.json", "0.0.1", "StatusLine", {"foo": "bar"})

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        assert hooks_manifest.read_text(encoding="utf-8") == preexisting


class TestCmdRefreshRenderOnly:
    def test_empty_spool__merge_skipped_with_note__reports_still_rendered(self, tmp_path, capsys):
        spool = tmp_path / "spool"  # never created: absent spool
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        assert "skipped merge (spool empty)" in capsys.readouterr().out
        assert (cov_dir / COVERAGE_FILENAME).exists()


class TestCmdRefreshSkipWithNote:
    def test_no_output_manifest__output_coverage_skipped_with_note(self, tmp_path, capsys):
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        out = capsys.readouterr().out
        assert "skipped OUTPUT_COVERAGE.md (no output_manifest.json)" in out
        assert not (cov_dir / "OUTPUT_COVERAGE.md").exists()

    def test_no_statusline_subtree__statusline_coverage_skipped_with_note(self, tmp_path, capsys):
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        out = capsys.readouterr().out
        assert "skipped STATUSLINE_COVERAGE.md (no statusline/ subtree)" in out
        assert not (cov_dir / "statusline").exists()


class TestCmdRefreshOutputRender:
    def test_committed_output_manifest__renders_output_coverage(self, tmp_path):
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)
        (cov_dir / "output_manifest.json").write_text(
            json.dumps({"cc_version": "0.0.1", "validated_at": "2024-01-01T00:00:00Z", "results": []}),
            encoding="utf-8",
        )

        rc = _refresh(tmp_path, captures=captures, spool=spool)

        assert rc == 0
        assert (cov_dir / "OUTPUT_COVERAGE.md").exists()


class TestCmdRefreshIdempotence:
    def test_two_runs__rendered_artifacts_byte_identical(self, tmp_path):
        spool = tmp_path / "spool"
        captures = tmp_path / "captures"
        cov_dir = captures / "cc-0.0.1"
        cov_dir.mkdir(parents=True)
        (cov_dir / "output_manifest.json").write_text(
            json.dumps({"cc_version": "0.0.1", "validated_at": "2024-01-01T00:00:00Z", "results": []}),
            encoding="utf-8",
        )
        manifest_path = _write_refresh_manifest(tmp_path)

        rc1 = _refresh(tmp_path, captures=captures, spool=spool, manifest=manifest_path)
        assert rc1 == 0
        first = {
            p.relative_to(cov_dir): p.read_bytes() for p in cov_dir.rglob("*") if p.is_file() and p.suffix == ".md"
        }

        rc2 = _refresh(tmp_path, captures=captures, spool=spool, manifest=manifest_path)
        assert rc2 == 0
        second = {
            p.relative_to(cov_dir): p.read_bytes() for p in cov_dir.rglob("*") if p.is_file() and p.suffix == ".md"
        }

        assert first  # sanity: something was actually rendered
        assert first == second


class TestResolveRefreshVersion:
    def test_explicit_cc_version__wins(self, tmp_path):
        assert _resolve_refresh_version(tmp_path, tmp_path / "spool", "1.2.3") == "1.2.3"

    def test_single_capture_dir__inferred(self, tmp_path):
        (tmp_path / "cc-1.2.3").mkdir()
        assert _resolve_refresh_version(tmp_path, tmp_path / "spool", None) == "1.2.3"

    def test_multi_dir__single_version_spool__spool_wins(self, tmp_path):
        (tmp_path / "cc-1.2.3").mkdir()
        (tmp_path / "cc-4.5.6").mkdir()
        spool = tmp_path / "spool"
        _write_envelope(spool, "0001.json", "9.9.9", "SessionStart")

        assert _resolve_refresh_version(tmp_path, spool, None) == "9.9.9"

    def test_multi_dir__empty_spool__system_exit(self, tmp_path):
        (tmp_path / "cc-1.2.3").mkdir()
        (tmp_path / "cc-4.5.6").mkdir()

        with pytest.raises(SystemExit):
            _resolve_refresh_version(tmp_path, tmp_path / "spool", None)

    def test_no_dirs__multi_version_spool__system_exit(self, tmp_path):
        spool = tmp_path / "spool"
        _write_envelope(spool, "0001.json", "1.1.1", "SessionStart")
        _write_envelope(spool, "0002.json", "2.2.2", "SessionStart")

        with pytest.raises(SystemExit):
            _resolve_refresh_version(tmp_path, spool, None)


class TestBucketSpoolEvents:
    def test_hooks_only(self):
        envelopes = [{"cc_version": "1.0", "event": "SessionStart"}]
        assert _bucket_spool_events(envelopes, "1.0") == {"hooks": 1, "statusline": 0}

    def test_statusline_only(self):
        envelopes = [{"cc_version": "1.0", "event": "StatusLine"}]
        assert _bucket_spool_events(envelopes, "1.0") == {"hooks": 0, "statusline": 1}

    def test_mixed(self):
        envelopes = [
            {"cc_version": "1.0", "event": "SessionStart"},
            {"cc_version": "1.0", "event": "StatusLine"},
            {"cc_version": "1.0", "event": "SubagentStatusLine"},
        ]
        assert _bucket_spool_events(envelopes, "1.0") == {"hooks": 1, "statusline": 2}

    def test_wrong_version_filtered_out(self):
        envelopes = [{"cc_version": "2.0", "event": "SessionStart"}]
        assert _bucket_spool_events(envelopes, "1.0") == {"hooks": 0, "statusline": 0}

    def test_unknown_event_counts_toward_neither_family(self):
        envelopes = [{"cc_version": "1.0", "event": "NotARealEvent"}]
        assert _bucket_spool_events(envelopes, "1.0") == {"hooks": 0, "statusline": 0}


class TestWriteMenuArtifacts:
    def test_write_menu_artifacts__events_and_raw__writes_scrubbed_txt_and_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", "/home/tester")
        cov_dir = tmp_path / "cc-1.2.3"
        events = [{"event": "PreToolUse", "description": "Before tool execution"}]

        _write_menu_artifacts(events, "ran in /home/tester/sbx\n", cov_dir, "1.2.3")

        assert "<HOME>" in (cov_dir / "hooks_menu.txt").read_text()
        data = json.loads((cov_dir / "hooks_menu.json").read_text())
        assert data == {"cc_version": "1.2.3", "events": events}


class TestConfirmMenuChange:
    _FINDINGS = [Finding(Path("hooks_menu.json"), "NewHook", 0, "cc-hooks-skill-drift", "absent from IR")]

    def test_confirm_menu_change__allow_flag__returns_true(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # flag wins even when non-interactive
        args = argparse.Namespace(allow_menu_change=True)
        assert _confirm_menu_change(self._FINDINGS, args) is True

    def test_confirm_menu_change__non_interactive_no_flag__aborts(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        args = argparse.Namespace(allow_menu_change=False)
        assert _confirm_menu_change(self._FINDINGS, args) is False

    def test_confirm_menu_change__interactive_yes__continues(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "y")
        args = argparse.Namespace(allow_menu_change=False)
        assert _confirm_menu_change(self._FINDINGS, args) is True

    def test_confirm_menu_change__interactive_default_no__aborts(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "")
        args = argparse.Namespace(allow_menu_change=False)
        assert _confirm_menu_change(self._FINDINGS, args) is False


class TestCmdVersion:
    def test_cmd_version__monkeypatched_detect__returns_zero(self, monkeypatch):
        """version command calls detect_cc_version and prints the result."""
        monkeypatch.setattr(
            "cc_flyrig.capture.__main__.detect_cc_version",
            lambda _: "9.9.9",
        )

        rc = main(["version"])

        assert rc == 0
