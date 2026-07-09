"""Tests for the scenario manifest loader (capture.scenario_manifest)."""

from pathlib import Path

import pytest

from cc_flyrig.capture import scenario_manifest as m
from cc_flyrig.capture.environment_plugins import build_registry as _build_registry

MANIFEST_PATH = Path(__file__).parent.parent.parent.parent / "capture_harness" / "scenarios.toml"

_ENV_PLUGINS = _build_registry(Path())


def parse(text: str):
    """Parse with the real capability registry injected (composition happens in __main__)."""
    return m.parse_manifest(text, _ENV_PLUGINS)


_MINIMAL = """
[[scenario]]
id = "baseline"
prompt = "say hi"
[scenario.expect]
events = ["Stop"]
"""


class TestRealManifest:
    def test_parse_manifest__committed_battery__parses_and_validates(self):
        manifest = parse(MANIFEST_PATH.read_text())
        assert manifest.scenarios
        ids = [s.id for s in manifest.scenarios]
        assert len(ids) == len(set(ids))  # ids unique
        assert "read-tool" in ids

    def test_parse_manifest__committed_battery__worktree_remove_expected(self):
        """WorktreeRemove (a tracked CC bug) is still expected by a scenario, so it surfaces as
        expected-but-missing in coverage rather than being silently dropped."""
        manifest = parse(MANIFEST_PATH.read_text())
        expected = {e for s in manifest.scenarios for e in s.expect.events}
        assert "WorktreeRemove" in expected


class TestParseManifest:
    def test_parse_manifest__minimal_scenario__builds_defaults(self):
        manifest = parse(_MINIMAL)
        (scenario,) = manifest.scenarios
        assert scenario.id == "baseline"
        assert scenario.expect.method == "promptable"
        assert scenario.drive.timeout_s == 180
        assert scenario.environment_plugins.selected == ()

    def test_parse_manifest__sandbox_files_and_interactions__parsed(self):
        text = """
[[scenario]]
id = "s"
prompt = "go"
[scenario.setup]
sandbox_files = [{ path = "a.txt", content = "x" }]
[scenario.drive]
interactions = [{ wait_for = "Stop", send_keys = ["/compact", "Enter"] }]
"""
        (scenario,) = parse(text).scenarios
        assert scenario.setup.sandbox_files[0].path == "a.txt"
        assert scenario.drive.interactions[0].send_keys == ("/compact", "Enter")


class TestValidation:
    def test_parse_manifest__no_scenarios__raises(self):
        with pytest.raises(m.ManifestError):
            parse("[meta]\ndescription = 'x'\n")

    def test_parse_manifest__missing_id__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nprompt = "hi"\n')

    def test_parse_manifest__duplicate_id__raises(self):
        text = '[[scenario]]\nid = "a"\nprompt = "x"\n[[scenario]]\nid = "a"\nprompt = "y"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__unknown_top_level_key__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nid = "a"\nprompt = "x"\nbogus = 1\n')

    def test_parse_manifest__unknown_subtable_key__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nid = "a"\nprompt = "x"\n[scenario.launch]\nbogus = 1\n')

    def test_parse_manifest__bad_capture_method__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nid = "a"\nprompt = "x"\n[scenario.expect]\nmethod = "nope"\n')

    def test_parse_manifest__unknown_expect_event__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nid = "a"\nprompt = "x"\n[scenario.expect]\nevents = ["NotAnEvent"]\n')

    def test_parse_manifest__no_prompt_and_no_launch_flags__raises(self):
        with pytest.raises(m.ManifestError):
            parse('[[scenario]]\nid = "a"\n')

    def test_parse_manifest__prompt_absent_but_launch_flags_present__ok(self):
        text = """
[[scenario]]
id = "setup"
[scenario.expect]
method = "launch-flag"
[scenario.launch]
flags = ["--init-only"]
"""
        (scenario,) = parse(text).scenarios
        assert scenario.launch.flags == ("--init-only",)


class TestExpect:
    def test_parse_manifest__expect_events_and_tools__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.expect]\nevents = ["PreToolUse"]\ntools = ["Read"]\n'
        (scenario,) = parse(text).scenarios
        assert scenario.expect.events == ("PreToolUse",)
        assert scenario.expect.tools == ("Read",)


class TestLaunch:
    def test_parse_manifest__model_free_string__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.launch]\nmodel = "claude-haiku-4-5-20251001"\n'
        (scenario,) = parse(text).scenarios
        assert scenario.launch.model == "claude-haiku-4-5-20251001"

    def test_parse_manifest__permission_mode__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.launch]\npermission_mode = "auto"\n'
        (scenario,) = parse(text).scenarios
        assert scenario.launch.permission_mode == "auto"


class TestSetupEnv:
    def test_parse_manifest__env_table__parsed_as_sorted_pairs(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.setup.env]\nBOO = "bar"\nAAA = "val"\n'
        (scenario,) = parse(text).scenarios
        assert scenario.setup.env == (("AAA", "val"), ("BOO", "bar"))

    def test_parse_manifest__env_missing__defaults_to_empty(self):
        (scenario,) = parse('[[scenario]]\nid = "s"\nprompt = "go"\n').scenarios
        assert scenario.setup.env == ()

    def test_parse_manifest__env_non_string_value__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.setup.env]\nKEY = 123\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__env_not_table__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.setup]\nenv = ["not", "a", "table"]\n'
        with pytest.raises(m.ManifestError):
            parse(text)


class TestDriveInteractions:
    def test_parse_manifest__interaction_write_sandbox_file__parsed(self):
        text = """
[[scenario]]
id = "s"
prompt = "go"
[[scenario.drive.interactions]]
wait_for = "Stop"
send_keys = []
write_sandbox_file = "watched.txt"
content = "changed\\n"
"""
        (scenario,) = parse(text).scenarios
        step = scenario.drive.interactions[0]
        assert step.write_sandbox_file == "watched.txt"
        assert step.content == "changed\n"

    def test_parse_manifest__interaction_no_write__defaults_none(self):
        text = """
[[scenario]]
id = "s"
prompt = "go"
[[scenario.drive.interactions]]
wait_for = "Stop"
send_keys = []
"""
        (scenario,) = parse(text).scenarios
        step = scenario.drive.interactions[0]
        assert step.write_sandbox_file is None
        assert step.content == ""

    def test_parse_manifest__interaction_write_sandbox_file_non_string__raises(self):
        lines = [
            "[[scenario]]",
            'id = "s"',
            'prompt = "go"',
            "[[scenario.drive.interactions]]",
            'wait_for = "Stop"',
            "send_keys = []",
            "write_sandbox_file = 42",
        ]
        with pytest.raises(m.ManifestError):
            parse("\n".join(lines))

    def test_parse_manifest__bad_complete_on__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.drive]\ncomplete_on = "NotAnEvent"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__bad_timeout__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.drive]\ntimeout_s = 0\n'
        with pytest.raises(m.ManifestError):
            parse(text)


class TestCapabilities:
    def test_parse_manifest__no_capabilities__defaults_empty(self):
        (scenario,) = parse('[[scenario]]\nid = "s"\nprompt = "go"\n').scenarios
        assert scenario.environment_plugins.selected == ()
        assert scenario.environment_plugins.get("git_repo", False) is False

    def test_parse_manifest__known_fixture_server__parsed(self):
        text = (
            '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nfixture_server = "ratelimit-429"\n'
        )
        (scenario,) = parse(text).scenarios
        assert scenario.environment_plugins.get("fixture_server") == "ratelimit-429"
        assert "fixture_server" in scenario.environment_plugins

    def test_parse_manifest__unknown_fixture_server_value__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nfixture_server = "bogus"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__mcp_server_in_registry__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nmcp_server = "elicit-probe"\n'
        (scenario,) = parse(text).scenarios
        assert scenario.environment_plugins.get("mcp_server") == "elicit-probe"

    def test_parse_manifest__unknown_mcp_server_value__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nmcp_server = "not-a-server"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__git_init_true__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\ngit_repo = true\n'
        (scenario,) = parse(text).scenarios
        assert scenario.environment_plugins.get("git_repo") is True

    def test_parse_manifest__git_init_non_bool__raises(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\ngit_repo = "yes"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__worktree_remove_on_exit_true__parsed(self):
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nworktree = true\n'
        (scenario,) = parse(text).scenarios
        assert scenario.environment_plugins.get("worktree") is True

    def test_parse_manifest__unknown_capability_name__raises(self):
        """An unregistered capability name is rejected generically against the registry."""
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\nteleport = true\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__capability_without_registry__raises(self):
        """No injected registry → every requested capability is unknown (composition is explicit)."""
        text = '[[scenario]]\nid = "s"\nprompt = "go"\n[scenario.environment_plugins]\ngit_repo = true\n'
        with pytest.raises(m.ManifestError):
            m.parse_manifest(text, {})  # empty registry, bypassing the parse() helper


class TestRun:
    def test_parse_manifest__run_absent__run_is_none(self):
        manifest = parse(_MINIMAL)
        assert manifest.run is None

    def test_parse_manifest__run_settings__parsed(self):
        text = """
[[scenario]]
id = "s"
prompt = "go"

[run.settings.standard]
default_script = "probe.py"
[run.settings.standard.script_overrides]
WorktreeCreate = "worktree_probe.py"
[run.settings.standard.matchers]
FileChanged = "watched.txt"

[run.settings.native]
default_script = "probe.py"
exclude_events = ["WorktreeCreate"]
[run.settings.native.matchers]
FileChanged = "watched.txt"
"""
        manifest = parse(text)
        std = manifest.run.settings.standard
        nat = manifest.run.settings.native
        assert std.default_script == "probe.py"
        assert dict(std.script_overrides) == {"WorktreeCreate": "worktree_probe.py"}
        assert dict(std.matchers) == {"FileChanged": "watched.txt"}
        assert nat.default_script == "probe.py"
        assert "WorktreeCreate" in nat.exclude_events
        assert dict(nat.matchers) == {"FileChanged": "watched.txt"}
        assert nat.script_overrides == ()

    def test_parse_manifest__run_not_table__raises(self):
        text = 'run = "bad"\n[[scenario]]\nid = "s"\nprompt = "go"\n'
        with pytest.raises(m.ManifestError, match=r"\[run\]"):
            parse(text)

    def test_parse_manifest__run_settings_missing__raises(self):
        text = '[run]\n[[scenario]]\nid = "s"\nprompt = "go"\n'
        with pytest.raises(m.ManifestError, match=r"run\.settings"):
            parse(text)

    def test_parse_manifest__hook_config_missing_default_script__raises(self):
        text = """
[run.settings.standard]
[run.settings.native]
default_script = "probe.py"
[[scenario]]
id = "s"
prompt = "go"
"""
        with pytest.raises(m.ManifestError, match="default_script"):
            parse(text)

    def test_parse_manifest__hook_config_unknown_exclude_event__raises(self):
        text = """
[run.settings.standard]
default_script = "probe.py"
exclude_events = ["NotAnEvent"]
[run.settings.native]
default_script = "probe.py"
[[scenario]]
id = "s"
prompt = "go"
"""
        with pytest.raises(m.ManifestError, match="unknown event"):
            parse(text)

    def test_parse_manifest__hook_config_unknown_override_event__raises(self):
        text = """
[run.settings.standard]
default_script = "probe.py"
[run.settings.standard.script_overrides]
NotAnEvent = "probe.py"
[run.settings.native]
default_script = "probe.py"
[[scenario]]
id = "s"
prompt = "go"
"""
        with pytest.raises(m.ManifestError, match="unknown event"):
            parse(text)

    def test_parse_manifest__real_battery__run_settings_configured(self):
        manifest = parse(MANIFEST_PATH.read_text())
        assert manifest.run is not None
        std = manifest.run.settings.standard
        assert std.default_script == "probe.py"
        assert dict(std.script_overrides).get("WorktreeCreate") == "worktree_probe.py"
        assert dict(std.matchers).get("FileChanged") == "watched.txt"
        nat = manifest.run.settings.native
        assert "WorktreeCreate" in nat.exclude_events
        assert nat.script_overrides == ()


class TestMeta:
    def test_parse_manifest__meta_default_model_and_effort__parsed(self):
        text = '[meta]\ndefault_model = "haiku"\ndefault_effort = "low"\n[[scenario]]\nid = "s"\nprompt = "go"\n'
        manifest = parse(text)
        assert manifest.meta.default_model == "haiku"
        assert manifest.meta.default_effort == "low"

    def test_parse_manifest__meta_bad_default_effort__raises(self):
        text = '[meta]\ndefault_effort = "turbo"\n[[scenario]]\nid = "s"\nprompt = "go"\n'
        with pytest.raises(m.ManifestError):
            parse(text)

    def test_parse_manifest__meta_not_table__raises(self):
        with pytest.raises(m.ManifestError):
            parse('meta = "notatable"\n[[scenario]]\nid = "s"\nprompt = "go"\n')


class TestRealBatteryScenarios:
    def test_parse_manifest__group4_scenarios__present_with_required_fields(self):
        by_id = {s.id: s for s in parse(MANIFEST_PATH.read_text()).scenarios}

        tl = by_id["task-lifecycle"]
        assert tl.launch.model == "sonnet"
        assert tl.drive.complete_on == "TaskCompleted"
        assert "TaskCreated" in tl.expect.events
        assert dict(tl.setup.env)["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"

        pd = by_id["permission-denied"]
        assert pd.launch.model == "sonnet"
        assert pd.launch.permission_mode == "auto"
        assert "PermissionDenied" in pd.expect.events

    def test_parse_manifest__capability_scenarios__carry_their_capabilities(self):
        by_id = {s.id: s for s in parse(MANIFEST_PATH.read_text()).scenarios}
        assert by_id["stop-failure"].environment_plugins.get("fixture_server") == "ratelimit-429"
        assert by_id["elicitation"].environment_plugins.get("mcp_server") == "elicit-probe"

        wt = by_id["worktree-remove"]
        assert wt.environment_plugins.get("git_repo") is True
        assert wt.environment_plugins.get("worktree") is True
        assert "--worktree" in wt.launch.flags
