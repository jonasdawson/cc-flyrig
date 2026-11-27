"""Tests for the scenario runner (capture.orchestrator.scenario_runner) with tmux mocked.

No real tmux or model is involved: a fake tmux simulates the probe firing by writing spool envelopes
when a session starts, so the orchestration sequence and completion signalling can be asserted.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cc_flyrig.capture.environment_plugins import build_registry as _build_registry
from cc_flyrig.capture.orchestrator import scenario_runner as orch
from cc_flyrig.capture.scenario_manifest import (
    Drive,
    EnvironmentPlugins,
    Expect,
    HookConfig,
    Interaction,
    Launch,
    Manifest,
    Meta,
    RunConfig,
    RunSettings,
    SandboxFile,
    Scenario,
    Setup,
)
from cc_flyrig.schema.roster import EVENTS

ENVIRONMENT_PLUGINS = _build_registry(Path())


def make_scenario(
    *,
    id,
    prompt="",
    expect_events=(),
    expect_tools=(),
    capture_method="promptable",
    model=None,
    permission_mode=None,
    launch_flags=(),
    sandbox_files=(),
    env=(),
    interactions=(),
    complete_on=None,
    timeout_s=180,
    fixture_server=None,
    mcp_server=None,
    git_repo=False,
    worktree=False,
):
    """Build a Scenario from flat kwargs — a test convenience over the nested model.

    Nested construction and TOML parsing are covered by test_capture_scenario_manifest; these
    orchestration tests only need concise scenarios, so capability fields are folded into the
    Capabilities mapping here.
    """
    caps: dict[str, object] = {}
    if fixture_server is not None:
        caps["fixture_server"] = fixture_server
    if mcp_server is not None:
        caps["mcp_server"] = mcp_server
    if git_repo:
        caps["git_repo"] = git_repo
    if worktree:
        caps["worktree"] = worktree
    return Scenario(
        id=id,
        prompt=prompt,
        expect=Expect(events=tuple(expect_events), tools=tuple(expect_tools), method=capture_method),
        launch=Launch(model=model, permission_mode=permission_mode, flags=tuple(launch_flags)),
        setup=Setup(sandbox_files=tuple(sandbox_files), env=tuple(env)),
        drive=Drive(interactions=tuple(interactions), complete_on=complete_on, timeout_s=timeout_s),
        environment_plugins=EnvironmentPlugins(tuple(sorted(caps.items()))),
    )


class FakeRun:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode

    def __call__(self, argv):
        return self


class FakeTmux:
    """Records calls; on new_session writes the given events into the spool for the run_id."""

    def __init__(self, emit=("Stop", "SessionEnd")):
        self.calls: list[tuple] = []
        self._emit = emit

    def new_session(self, name, cwd, command, env=None):
        self.calls.append(("new_session", name, tuple(command)))
        spool = Path(env["FLYRIG_SPOOL_DIR"])
        spool.mkdir(parents=True, exist_ok=True)
        for event in self._emit:
            (spool / f"{event}.json").write_text(json.dumps({"event": event, "run_id": env["FLYRIG_RUN_ID"]}))

    def has_session(self, name):
        return True

    def send_text(self, name, text):
        self.calls.append(("send_text", text))

    def send_key(self, name, key):
        self.calls.append(("send_key", key))

    def send_tokens(self, name, tokens):
        self.calls.append(("send_tokens", tuple(tokens)))

    def capture_pane(self, name):
        return "❯ \n  ? for shortcuts · ← for agents"

    def kill_session(self, name):
        self.calls.append(("kill_session", name))


@pytest.fixture
def fast_clock():
    state = {"t": 0.0}

    def clock():
        state["t"] += 1.0
        return state["t"]

    return clock


def _run_scenario(scenario, tmp_path, tmux, fast_clock):
    return orch.run_scenario(
        scenario,
        environment_plugins=ENVIRONMENT_PLUGINS,
        claude_bin="claude",
        settings_path=tmp_path / "probe-settings.json",
        spool_dir=tmp_path / "spool",
        sandbox_root=tmp_path / "sandbox",
        cc_version="2.1.168",
        batch_id="b1",
        tmux=tmux,
        sleep=lambda _: None,
        clock=fast_clock,
    )


class TestDetectVersion:
    def test_detect_cc_version__version_string__parsed(self):
        from cc_flyrig.capture.util.cc_version import detect_cc_version

        assert detect_cc_version(run=FakeRun(stdout="2.1.168 (Claude Code)")) == "2.1.168"

    def test_detect_cc_version__unparseable__raises(self):
        from cc_flyrig.capture.util.cc_version import detect_cc_version

        with pytest.raises(ValueError):
            detect_cc_version(run=FakeRun(stdout="no version here"))


# ---------------------------------------------------------------------------
# Hook entry generation from HookConfig
# ---------------------------------------------------------------------------


class TestHookEntries:
    def _make_config(self, *, default_script="probe.py", exclude_events=(), script_overrides=(), matchers=()):
        return HookConfig(
            default_script=default_script,
            exclude_events=frozenset(exclude_events),
            script_overrides=tuple(sorted(script_overrides)),
            matchers=tuple(sorted(matchers)),
        )

    def test_hook_entries__no_excludes_no_overrides__all_events_with_default_script(self, tmp_path):
        """All EVENTS are wired when nothing is excluded or overridden."""
        config = self._make_config()
        entries = orch._hook_entries(config, tmp_path, "python3")
        assert len(entries) == len(EVENTS)
        assert all("probe.py" in e.command for e in entries)

    def test_hook_entries__exclude_event__excluded_event_absent(self, tmp_path):
        """An event in exclude_events does not appear in the output."""
        config = self._make_config(exclude_events=["WorktreeCreate"])
        entries = orch._hook_entries(config, tmp_path, "python3")
        assert len(entries) == len(EVENTS) - 1
        assert not any(e.event == "WorktreeCreate" for e in entries)

    def test_hook_entries__script_override__override_event_uses_override_script(self, tmp_path):
        """An event in script_overrides uses the override script, not the default."""
        config = self._make_config(script_overrides=[("WorktreeCreate", "worktree_probe.py")])
        entries = orch._hook_entries(config, tmp_path, "python3")
        wt = next(e for e in entries if e.event == "WorktreeCreate")
        assert wt.command.split()[-1].endswith("worktree_probe.py")

    def test_hook_entries__matcher__matched_event_carries_matcher(self, tmp_path):
        """An event listed in matchers carries the matcher value; others do not."""
        config = self._make_config(matchers=[("FileChanged", "watched.txt")])
        entries = orch._hook_entries(config, tmp_path, "python3")
        fc = next(e for e in entries if e.event == "FileChanged")
        assert fc.matcher == "watched.txt"
        others = [e for e in entries if e.event != "FileChanged"]
        assert all(e.matcher is None for e in others)

    def test_hook_entries__standard_config__29_events_worktree_override(self, tmp_path):
        """Standard config: WorktreeCreate override → 30 entries, all others use probe.py."""
        config = self._make_config(script_overrides=[("WorktreeCreate", "worktree_probe.py")])
        entries = orch._hook_entries(config, tmp_path, "python3")
        assert len(entries) == len(EVENTS)
        wt = next(e for e in entries if e.event == "WorktreeCreate")
        assert "worktree_probe.py" in wt.command

    def test_hook_entries__native_config__worktree_create_absent(self, tmp_path):
        """Native config: WorktreeCreate excluded → one fewer entry, WorktreeCreate absent."""
        config = self._make_config(exclude_events=["WorktreeCreate"])
        entries = orch._hook_entries(config, tmp_path, "python3")
        assert len(entries) == len(EVENTS) - 1
        assert not any(e.event == "WorktreeCreate" for e in entries)


class TestRunScenario:
    def test_run_scenario__prompt_scenario__sends_prompt_and_observes_stop(self, tmp_path, fast_clock):
        tmux = FakeTmux(emit=("Stop", "SessionEnd"))
        scenario = make_scenario(id="read", prompt="Use the Read tool", expect_events=("Stop",))
        result = _run_scenario(scenario, tmp_path, tmux, fast_clock)

        assert ("send_text", "Use the Read tool") in tmux.calls
        assert ("send_key", "Enter") in tmux.calls
        assert any(c[0] == "kill_session" for c in tmux.calls)
        assert "Stop" in result.observed and "SessionEnd" in result.observed
        assert (tmp_path / "sandbox" / "b1" / "read" / "pane.txt").exists()

    def test_run_scenario__scenario_with_sandbox_files__seeds_them_into_sandbox(self, tmp_path, fast_clock):
        scenario = make_scenario(id="read", prompt="go", sandbox_files=(SandboxFile("fixture.txt", "hi"),))
        _run_scenario(scenario, tmp_path, FakeTmux(), fast_clock)
        assert (tmp_path / "sandbox" / "b1" / "read" / "fixture.txt").read_text() == "hi"

    def test_run_scenario__git_init_true__sandbox_is_valid_git_repo(self, tmp_path, fast_clock):
        """git_repo=True seeds the sandbox with a .git and a HEAD commit for git worktree add."""
        import subprocess

        scenario = make_scenario(id="wt", prompt="go", git_repo=True)
        _run_scenario(scenario, tmp_path, FakeTmux(), fast_clock)
        sandbox = tmp_path / "sandbox" / "b1" / "wt"
        assert (sandbox / ".git").exists()
        result = subprocess.run(
            ["git", "-C", str(sandbox), "log", "--oneline"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip()  # at least one commit

    def test_run_scenario__interaction__sends_keys_after_wait(self, tmp_path, fast_clock):
        tmux = FakeTmux(emit=("PermissionRequest", "Stop", "SessionEnd"))
        scenario = make_scenario(
            id="perm",
            prompt="run bash",
            capture_method="interactive",
            interactions=(Interaction(wait_for="PermissionRequest", send_keys=("Enter",)),),
        )
        _run_scenario(scenario, tmp_path, tmux, fast_clock)
        assert ("send_tokens", ("Enter",)) in tmux.calls

    def test_run_scenario__launch_flag_no_prompt__skips_prompt(self, tmp_path, fast_clock):
        tmux = FakeTmux(emit=("SessionEnd",))
        scenario = make_scenario(id="setup", launch_flags=("--init-only",), capture_method="launch-flag")
        _run_scenario(scenario, tmp_path, tmux, fast_clock)
        # no prompt text sent (only the teardown "/exit")
        prompts = [c for c in tmux.calls if c[0] == "send_text" and c[1] != "/exit"]
        assert prompts == []


# ---------------------------------------------------------------------------
# Occurrence-count interaction wait
# ---------------------------------------------------------------------------


class TestSpoolEventCount:
    def test_spool_event_count__multiple_invocations__counts_per_event(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        run_id = "b1:s1"
        # write two Stop files for run_id
        (spool / "stop_1.json").write_text(json.dumps({"event": "Stop", "run_id": run_id}))
        (spool / "stop_2.json").write_text(json.dumps({"event": "Stop", "run_id": run_id}))
        # one Stop for a different run_id — must not be counted
        (spool / "stop_other.json").write_text(json.dumps({"event": "Stop", "run_id": "b1:other"}))
        # one different event for the same run_id
        (spool / "ptu.json").write_text(json.dumps({"event": "PreToolUse", "run_id": run_id}))

        assert orch._spool_event_count(spool, run_id, "Stop") == 2
        assert orch._spool_event_count(spool, run_id, "PreToolUse") == 1
        assert orch._spool_event_count(spool, run_id, "SessionEnd") == 0

    def test_spool_event_count__empty_spool__returns_zero(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        assert orch._spool_event_count(spool, "b1:s1", "Stop") == 0


class _IncrementalFakeTmux(FakeTmux):
    """FakeTmux variant that writes an extra Stop file on each send_tokens call.

    Used to verify occurrence-count serialization: after each step's send_tokens fires, the next step's
    baseline-then-wait sees a new occurrence and unblocks immediately.
    """

    def __init__(self):
        super().__init__(emit=("Stop", "SessionEnd"))
        self._stop_counter = 1  # new_session wrote stop_0

    def new_session(self, name, cwd, command, env=None):
        super().new_session(name, cwd, command, env)
        self._spool = Path(env["FLYRIG_SPOOL_DIR"])
        self._run_id = env["FLYRIG_RUN_ID"]

    def send_tokens(self, name, tokens):
        super().send_tokens(name, tokens)
        self._stop_counter += 1
        (self._spool / f"stop_{self._stop_counter}.json").write_text(
            json.dumps({"event": "Stop", "run_id": self._run_id})
        )


class TestP1Serialization:
    def test_run_scenario__repeated_wait_for__serializes_on_new_occurrence(self, tmp_path, fast_clock):
        """Each interaction step waits for a new occurrence, not a previously-seen one."""
        tmux = _IncrementalFakeTmux()
        scenario = make_scenario(
            id="compact-manual",
            prompt="go",
            timeout_s=5,
            interactions=(
                Interaction(wait_for="Stop", send_keys=("turn2",)),
                Interaction(wait_for="Stop", send_keys=("turn3",)),
            ),
        )
        _run_scenario(scenario, tmp_path, tmux, fast_clock)

        # Both steps must reach send_tokens — the second step must unblock once step 1's
        # send_tokens writes a new Stop (count rises above step 2's baseline).
        assert ("send_tokens", ("turn2",)) in tmux.calls
        assert ("send_tokens", ("turn3",)) in tmux.calls


# ---------------------------------------------------------------------------
# Per-scenario env
# ---------------------------------------------------------------------------


class TestP2Env:
    def test_run_scenario__scenario_env__merged_into_session_env_flyrig_wins(self, tmp_path, fast_clock):
        """Scenario env is forwarded to new_session; FLYRIG_* keys are not overwritten."""
        captured_env: dict = {}

        class _CapturingTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_env.update(env or {})
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(
            id="s",
            prompt="go",
            env=(("ANTHROPIC_API_KEY", "sk-test"), ("FLYRIG_SPOOL_DIR", "should-be-overridden")),
        )
        _run_scenario(scenario, tmp_path, _CapturingTmux(), fast_clock)

        assert captured_env["ANTHROPIC_API_KEY"] == "sk-test"
        # FLYRIG_* must NOT be clobbered by scenario env
        assert captured_env["FLYRIG_SPOOL_DIR"] != "should-be-overridden"
        assert str(tmp_path / "spool") in captured_env["FLYRIG_SPOOL_DIR"]


# ---------------------------------------------------------------------------
# Mid-session write_sandbox_file on Interaction
# ---------------------------------------------------------------------------


class TestP3WriteSandboxFile:
    def test_run_scenario__write_sandbox_file__written_before_send_keys(self, tmp_path, fast_clock):
        """The write happens (with correct content) and send_tokens is still called."""
        write_order: list[str] = []

        class _OrderingTmux(FakeTmux):
            def __init__(self, sandbox):
                super().__init__(emit=("Stop", "SessionEnd"))
                self._sandbox = sandbox

            def send_tokens(self, name, tokens):
                # Record whether the file existed at send_tokens time
                target = self._sandbox / "b1" / "s" / "watched.txt"
                write_order.append("file_exists" if target.exists() else "no_file")
                super().send_tokens(name, tokens)

        sandbox_root = tmp_path / "sandbox"
        tmux = _OrderingTmux(sandbox_root)
        scenario = make_scenario(
            id="s",
            prompt="go",
            interactions=(
                Interaction(
                    wait_for="Stop",
                    send_keys=("done",),
                    write_sandbox_file="watched.txt",
                    content="changed\n",
                ),
            ),
        )
        _run_scenario(scenario, tmp_path, tmux, fast_clock)

        target = sandbox_root / "b1" / "s" / "watched.txt"
        assert target.read_text() == "changed\n"
        assert write_order == ["file_exists"]  # file was written before send_tokens

    def test_run_scenario__no_write_sandbox_file__send_keys_unaffected(self, tmp_path, fast_clock):
        """An Interaction without write_sandbox_file still sends keys normally."""
        tmux = FakeTmux(emit=("Stop", "SessionEnd"))
        scenario = make_scenario(
            id="s",
            prompt="go",
            interactions=(Interaction(wait_for="Stop", send_keys=("hello",)),),
        )
        _run_scenario(scenario, tmp_path, tmux, fast_clock)
        assert ("send_tokens", ("hello",)) in tmux.calls


# ---------------------------------------------------------------------------
# Fixture 429 server
# ---------------------------------------------------------------------------


class TestP4FixtureServer:
    def test_run_scenario__fixture_server__injects_anthropic_base_url(self, tmp_path, fast_clock):
        """When fixture_server='ratelimit-429', ANTHROPIC_BASE_URL is set in the child env."""
        captured_env: dict = {}

        class _CapturingTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_env.update(env or {})
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(
            id="s",
            prompt="go",
            fixture_server="ratelimit-429",
        )
        _run_scenario(scenario, tmp_path, _CapturingTmux(), fast_clock)
        assert "ANTHROPIC_BASE_URL" in captured_env
        assert "127.0.0.1:8472" in captured_env["ANTHROPIC_BASE_URL"]

    def test_run_scenario__no_fixture_server__no_anthropic_base_url(self, tmp_path, fast_clock):
        """Without fixture_server, ANTHROPIC_BASE_URL is not injected."""
        captured_env: dict = {}

        class _CapturingTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_env.update(env or {})
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go")
        _run_scenario(scenario, tmp_path, _CapturingTmux(), fast_clock)
        assert "ANTHROPIC_BASE_URL" not in captured_env


# ---------------------------------------------------------------------------
# Model + effort flags
# ---------------------------------------------------------------------------


class TestP6ModelEffort:
    def test_run_scenario__scenario_model_and_battery_effort__appended_to_argv(self, tmp_path, fast_clock):
        """Scenario model overrides the battery default; effort comes from the battery default."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go", model="sonnet")
        orch.run_scenario(
            scenario,
            environment_plugins=ENVIRONMENT_PLUGINS,
            claude_bin="claude",
            settings_path=tmp_path / "probe-settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=_ArgvTmux(),
            sleep=lambda _: None,
            clock=fast_clock,
            default_model="haiku",
            default_effort="medium",
        )
        assert "--model" in captured_argv
        assert captured_argv[captured_argv.index("--model") + 1] == "sonnet"
        assert "--effort" in captured_argv
        assert captured_argv[captured_argv.index("--effort") + 1] == "medium"  # battery default

    def test_run_scenario__default_model_effort__used_when_scenario_unset(self, tmp_path, fast_clock):
        """Battery defaults apply when the scenario does not set model/effort."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go")
        orch.run_scenario(
            scenario,
            environment_plugins=ENVIRONMENT_PLUGINS,
            claude_bin="claude",
            settings_path=tmp_path / "probe-settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=_ArgvTmux(),
            sleep=lambda _: None,
            clock=fast_clock,
            default_model="haiku",
            default_effort="low",
        )
        assert "--model" in captured_argv
        assert captured_argv[captured_argv.index("--model") + 1] == "haiku"
        assert "--effort" in captured_argv
        assert captured_argv[captured_argv.index("--effort") + 1] == "low"

    def test_run_scenario__no_model_no_effort__no_flags(self, tmp_path, fast_clock):
        """When neither scenario nor defaults set model/effort, no flags are appended."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go")
        _run_scenario(scenario, tmp_path, _ArgvTmux(), fast_clock)
        assert "--model" not in captured_argv
        assert "--effort" not in captured_argv


# ---------------------------------------------------------------------------
# Per-scenario MCP server via --mcp-config
# ---------------------------------------------------------------------------


class TestP8McpServer:
    def test_run_scenario__mcp_server__writes_config_and_adds_flag(self, tmp_path, fast_clock):
        """mcp_server set → mcp-config.json written with server path, argv carries --mcp-config."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go", mcp_server="elicit-probe")
        mcp_root = tmp_path / "capture"
        mcp_root.mkdir()
        (mcp_root / "mcp_elicit_server.py").touch()

        orch.run_scenario(
            scenario,
            environment_plugins=_build_registry(mcp_root),
            claude_bin="claude",
            settings_path=tmp_path / "probe-settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=_ArgvTmux(),
            sleep=lambda _: None,
            clock=fast_clock,
        )

        assert "--mcp-config" in captured_argv
        mcp_cfg_path = captured_argv[captured_argv.index("--mcp-config") + 1]
        assert "--strict-mcp-config" in captured_argv
        import json as _json

        cfg = _json.loads(Path(mcp_cfg_path).read_text())
        assert "elicit-probe" in cfg["mcpServers"]
        assert "mcp_elicit_server.py" in cfg["mcpServers"]["elicit-probe"]["args"][0]

    def test_run_scenario__no_mcp_server__no_flag_no_file(self, tmp_path, fast_clock):
        """Without mcp_server, --mcp-config is absent and no config file is written."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        scenario = make_scenario(id="s", prompt="go")
        _run_scenario(scenario, tmp_path, _ArgvTmux(), fast_clock)

        assert "--mcp-config" not in captured_argv
        assert "--strict-mcp-config" not in captured_argv
        sandbox = tmp_path / "sandbox" / "b1" / "s"
        assert not (sandbox / "mcp-config.json").exists()


# ---------------------------------------------------------------------------
# Native settings selection for git_init scenarios
# ---------------------------------------------------------------------------


class TestP9NativeSettingsSelection:
    def test_run_scenario__git_init__uses_native_settings_no_shim(self, tmp_path, fast_clock):
        """git_repo=True selects native_settings_path (no WorktreeCreate shim) over settings_path."""
        captured_argv: list = []

        class _ArgvTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_argv.extend(command)
                super().new_session(name, cwd, command, env)

        native_settings = tmp_path / "probe-settings-native.json"
        regular_settings = tmp_path / "probe-settings.json"
        scenario = make_scenario(id="wt-remove", prompt="go", git_repo=True)

        orch.run_scenario(
            scenario,
            environment_plugins=ENVIRONMENT_PLUGINS,
            claude_bin="claude",
            settings_path=regular_settings,
            native_settings_path=native_settings,
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=_ArgvTmux(),
            sleep=lambda _: None,
            clock=fast_clock,
        )

        # git_init scenario must use native settings (no WorktreeCreate shim), not the regular path
        assert str(native_settings) in captured_argv
        assert str(regular_settings) not in captured_argv


class TestP10WorktreeRemoveOnExit:
    def test_teardown__worktree_remove_on_exit__sends_2_enter_after_sleep(self, tmp_path, fast_clock):
        """worktree=True sleeps then sends '2'+Enter to select Remove."""
        sleeps: list[float] = []
        fake = FakeTmux(emit=("Stop", "WorktreeRemove", "SessionEnd"))
        scenario = make_scenario(id="wt-remove", prompt="go", worktree=True, git_repo=True)

        orch.run_scenario(
            scenario,
            environment_plugins=ENVIRONMENT_PLUGINS,
            claude_bin="claude",
            settings_path=tmp_path / "settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=fake,
            sleep=lambda s: sleeps.append(s),
            clock=fast_clock,
        )

        # After /exit, there must be a sleep >= 3s for the dialog to render.
        exit_text_idx = next(i for i, c in enumerate(fake.calls) if c == ("send_text", "/exit"))
        assert any(s >= 3.0 for s in sleeps), "must sleep >= 3s after /exit for dialog to render"
        # Then '2' (direct selection) + Enter to confirm Remove.
        post_exit = fake.calls[exit_text_idx:]
        assert ("send_text", "2") in post_exit, "'2' must be sent to select Remove worktree"
        two_idx = next(i for i, c in enumerate(post_exit) if c == ("send_text", "2"))
        enter_after_two = next((i for i, c in enumerate(post_exit) if i > two_idx and c == ("send_key", "Enter")), None)
        assert enter_after_two is not None, "Enter must confirm Remove after '2'"

    def test_teardown__no_worktree_flag__no_remove_keys_sent(self, tmp_path, fast_clock):
        """worktree_remove_on_exit=False (default) does not inject '2'+Enter into teardown."""
        fake = FakeTmux()
        scenario = make_scenario(id="plain", prompt="go")

        orch.run_scenario(
            scenario,
            environment_plugins=ENVIRONMENT_PLUGINS,
            claude_bin="claude",
            settings_path=tmp_path / "settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=fake,
            sleep=lambda _: None,
            clock=fast_clock,
        )

        text_calls = [c for c in fake.calls if c[0] == "send_text"]
        assert ("send_text", "2") not in text_calls

    def test_launch__worktree_remove_on_exit__strips_tmux_env(self, tmp_path, fast_clock):
        """worktree=True prepends env -u TMUX -u TMUX_PANE to the CC argv."""
        fake = FakeTmux(emit=("Stop", "SessionEnd"))
        scenario = make_scenario(id="wt-remove", prompt="go", worktree=True, git_repo=True)

        _run_scenario(scenario, tmp_path, fake, fast_clock)

        new_session_calls = [c for c in fake.calls if c[0] == "new_session"]
        assert len(new_session_calls) == 1
        command = new_session_calls[0][2]  # tuple(command) is index 2
        assert command[:4] == ("env", "-u", "TMUX", "-u"), "env -u TMUX -u ... must prefix the command"
        assert "TMUX_PANE" in command, "TMUX_PANE must be unset"
        claude_idx = next((i for i, t in enumerate(command) if t == "claude"), None)
        assert claude_idx is not None and claude_idx > 4, "claude binary must follow the env prefix"

    def test_launch__no_worktree_flag__no_tmux_strip(self, tmp_path, fast_clock):
        """worktree_remove_on_exit=False (default) does not prepend env -u TMUX."""
        fake = FakeTmux()
        scenario = make_scenario(id="plain", prompt="go")

        _run_scenario(scenario, tmp_path, fake, fast_clock)

        new_session_calls = [c for c in fake.calls if c[0] == "new_session"]
        assert len(new_session_calls) == 1
        command = new_session_calls[0][2]
        assert command[0] == "claude", "command must start directly with claude binary"


class TestEngineDispatch:
    def test_run_scenario__arbitrary_capability__dispatched_by_engine(self, tmp_path, fast_clock):
        """The engine runs whatever registry it is handed — it has no knowledge of any specific
        capability. A capability the orchestrator has never heard of still contributes to the run."""
        from cc_flyrig.capture.environment_plugins.base import EnvironmentPlugin

        marker = EnvironmentPlugin(
            validate=lambda v: v,
            configure=lambda v, ctx, plan: plan.env.update({"FLYRIG_MARKER": str(v)}),
        )
        captured_env: dict = {}

        class _CapturingTmux(FakeTmux):
            def new_session(self, name, cwd, command, env=None):
                captured_env.update(env or {})
                super().new_session(name, cwd, command, env)

        scenario = Scenario(id="s", prompt="go", environment_plugins=EnvironmentPlugins((("marker", "hi"),)))
        orch.run_scenario(
            scenario,
            environment_plugins={"marker": marker},
            claude_bin="claude",
            settings_path=tmp_path / "probe-settings.json",
            spool_dir=tmp_path / "spool",
            sandbox_root=tmp_path / "sandbox",
            cc_version="2.1.168",
            batch_id="b1",
            tmux=_CapturingTmux(),
            sleep=lambda _: None,
            clock=fast_clock,
        )
        assert captured_env["FLYRIG_MARKER"] == "hi"


class TestCheckAssertion:
    def _write_envelope(self, spool_dir: Path, run_id: str, event: str, n: int = 1) -> None:
        for i in range(n):
            (spool_dir / f"{event}_{i}.json").write_text(
                json.dumps({"event": event, "run_id": run_id}), encoding="utf-8"
            )

    def test_check_assertion__spool_absent_event_not_in_spool__returns_pass(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        assert orch.check_assertion("spool-absent", "PostToolUse", spool, "r1") == "pass"

    def test_check_assertion__spool_absent_event_present__returns_fail(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "PostToolUse")
        assert orch.check_assertion("spool-absent", "PostToolUse", spool, "r1") == "fail"

    def test_check_assertion__spool_present_event_present__returns_pass(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "Stop")
        assert orch.check_assertion("spool-present", "Stop", spool, "r1") == "pass"

    def test_check_assertion__filesystem_path_exists__returns_pass(self, tmp_path):
        target = tmp_path / "pane.txt"
        target.write_text("hello", encoding="utf-8")
        spool = tmp_path / "spool"
        spool.mkdir()
        assert orch.check_assertion("filesystem", "Stop", spool, "r1", path=target) == "pass"

    def test_check_assertion__unobservable_type__returns_unobservable(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        assert orch.check_assertion("unobservable", "Stop", spool, "r1") == "unobservable"

    def test_check_assertion__spool_count_gt_count_exceeds_threshold__returns_pass(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "PreToolUse", n=3)
        assert orch.check_assertion("spool-count-gt:1", "PreToolUse", spool, "r1") == "pass"

    def test_check_assertion__spool_count_gt_count_at_threshold__returns_fail(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "PreToolUse", n=1)
        assert orch.check_assertion("spool-count-gt:1", "PreToolUse", spool, "r1") == "fail"

    def test_check_assertion__spool_count_lte_count_at_threshold__returns_pass(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "PreToolUse", n=1)
        assert orch.check_assertion("spool-count-lte:1", "PreToolUse", spool, "r1") == "pass"

    def test_check_assertion__spool_count_lte_count_exceeds_threshold__returns_fail(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        self._write_envelope(spool, "r1", "PreToolUse", n=3)
        assert orch.check_assertion("spool-count-lte:1", "PreToolUse", spool, "r1") == "fail"


# ---------------------------------------------------------------------------
# run_scenarios() family wiring: statusline settings, per-family
# consolidation, and STATUSLINE_COVERAGE.md alongside the unchanged hooks pipeline.
# ---------------------------------------------------------------------------


class _VersionedFakeTmux(FakeTmux):
    """FakeTmux variant that stamps ``cc_version`` on spooled envelopes, as the real probe does.

    ``consolidate()`` filters the spool by ``cc_version``; the plain ``FakeTmux`` used by the
    ``run_scenario`` tests never exercises consolidation, so it has no need to stamp it.
    """

    def __init__(self, emit=("Stop", "SessionEnd"), cc_version="2.1.168"):
        super().__init__(emit=emit)
        self._cc_version = cc_version

    def new_session(self, name, cwd, command, env=None):
        self.calls.append(("new_session", name, tuple(command)))
        spool = Path(env["FLYRIG_SPOOL_DIR"])
        spool.mkdir(parents=True, exist_ok=True)
        for event in self._emit:
            (spool / f"{event}.json").write_text(
                json.dumps({"event": event, "run_id": env["FLYRIG_RUN_ID"], "cc_version": self._cc_version})
            )


class TestRunScenariosFamilyWiring:
    def _make_manifest(self):
        standard = HookConfig(default_script="probe.py")
        native = HookConfig(default_script="probe.py")
        return Manifest(
            meta=Meta(),
            scenarios=(make_scenario(id="s1", prompt="go", expect_events=("Stop",)),),
            run=RunConfig(settings=RunSettings(standard=standard, native=native)),
        )

    def _run(self, tmp_path, monkeypatch, tmux):
        monkeypatch.setattr(orch, "Tmux", lambda: tmux)
        paths = orch.CapturePaths(
            probe=tmp_path / "capture_harness" / "hooks" / "probe.py",
            captures=tmp_path / "captures",
            spool=tmp_path / "spool",
            sandbox=tmp_path / "sandbox",
        )
        return orch.run_scenarios(
            self._make_manifest(),
            ENVIRONMENT_PLUGINS,
            paths,
            claude=orch.ClaudeInstall(bin="claude", version="2.1.168"),
        )

    def test_run_scenarios__mixed_family_events__statusline_wired_into_both_settings_files(self, tmp_path, monkeypatch):
        """Statusline entries land in both probe-settings.json and probe-settings-native.json."""
        tmux = _VersionedFakeTmux(emit=("Stop", "SessionEnd", "StatusLine", "SubagentStatusLine"))
        self._run(tmp_path, monkeypatch, tmux)

        for name in ("probe-settings.json", "probe-settings-native.json"):
            doc = json.loads((tmp_path / "sandbox" / name).read_text())
            assert doc["statusLine"]["type"] == "command"
            assert "probe.py" in doc["statusLine"]["command"]
            assert doc["subagentStatusLine"]["refreshInterval"] == 1
            assert "subagent_probe.py" in doc["subagentStatusLine"]["command"]

    def test_run_scenarios__mixed_family_events__statusline_consolidated_into_own_subtree(self, tmp_path, monkeypatch):
        """Statusline payloads land under captures/cc-<version>/statusline/, not the hooks root."""
        tmux = _VersionedFakeTmux(emit=("Stop", "SessionEnd", "StatusLine", "SubagentStatusLine"))
        self._run(tmp_path, monkeypatch, tmux)

        cov_dir = tmp_path / "captures" / "cc-2.1.168"
        statusline_dir = cov_dir / "statusline"
        assert (statusline_dir / "StatusLine.jsonl").exists()
        assert (statusline_dir / "SubagentStatusLine.jsonl").exists()
        assert (statusline_dir / "STATUSLINE_COVERAGE.md").exists()

        # hooks root must stay clean of statusline payloads
        assert not (cov_dir / "StatusLine.jsonl").exists()
        assert not (cov_dir / "SubagentStatusLine.jsonl").exists()

    def test_run_scenarios__mixed_family_events__hooks_coverage_unaffected(self, tmp_path, monkeypatch):
        """The hooks-family INPUT_COVERAGE.md and Stop.jsonl are written exactly as before."""
        tmux = _VersionedFakeTmux(emit=("Stop", "SessionEnd", "StatusLine", "SubagentStatusLine"))
        self._run(tmp_path, monkeypatch, tmux)

        cov_dir = tmp_path / "captures" / "cc-2.1.168"
        assert (cov_dir / "INPUT_COVERAGE.md").exists()
        assert (cov_dir / "Stop.jsonl").exists()
        assert (cov_dir / "SessionEnd.jsonl").exists()

    def test_run_scenarios__no_statusline_events_emitted__no_statusline_jsonl_written(self, tmp_path, monkeypatch):
        """When no statusline events fire, no StatusLine/SubagentStatusLine.jsonl are written, but
        the statusline subtree still gets its coverage report (all rows not-attempted/missing)."""
        tmux = _VersionedFakeTmux(emit=("Stop", "SessionEnd"))
        self._run(tmp_path, monkeypatch, tmux)

        statusline_dir = tmp_path / "captures" / "cc-2.1.168" / "statusline"
        assert not (statusline_dir / "StatusLine.jsonl").exists()
        assert not (statusline_dir / "SubagentStatusLine.jsonl").exists()
        assert (statusline_dir / "STATUSLINE_COVERAGE.md").exists()


# ---------------------------------------------------------------------------
# summarize_scenario(): pure per-scenario completion summary.
# ---------------------------------------------------------------------------


class TestSummarizeScenario:
    def test_all_expected_observed__renders_check_mark_with_counts(self):
        line = orch.summarize_scenario(("Stop", "SessionEnd"), frozenset({"Stop", "SessionEnd"}), {})
        assert line == "  ✓ hooks 2/2 expected"

    def test_missing_events__renders_warning_with_sorted_missing_list(self):
        line = orch.summarize_scenario(("Stop", "SessionEnd", "PreToolUse"), frozenset({"Stop"}), {})
        assert line == "  ⚠ hooks 1/3 expected (missing: PreToolUse, SessionEnd)"

    def test_zero_expected__renders_check_mark_with_zero_over_zero(self):
        line = orch.summarize_scenario((), frozenset(), {})
        assert line == "  ✓ hooks 0/0 expected"

    def test_statusline_counts__render_in_mapping_order_with_display_labels(self):
        line = orch.summarize_scenario(
            ("Stop",),
            frozenset({"Stop"}),
            {"StatusLine": 5, "SubagentStatusLine": 0},
        )
        assert line == "  ✓ hooks 1/1 expected · statusline ×5 · subagent-statusline ×0"

    def test_statusline_counts__reverse_mapping_order_is_preserved(self):
        line = orch.summarize_scenario(
            ("Stop",),
            frozenset({"Stop"}),
            {"SubagentStatusLine": 0, "StatusLine": 5},
        )
        assert line == "  ✓ hooks 1/1 expected · subagent-statusline ×0 · statusline ×5"

    def test_unknown_family_key__falls_back_to_raw_event_name(self):
        line = orch.summarize_scenario(("Stop",), frozenset({"Stop"}), {"SomeNewFamilyEvent": 3})
        assert line == "  ✓ hooks 1/1 expected · SomeNewFamilyEvent ×3"

    def test_observed_statusline_tags__do_not_contaminate_hooks_ratio(self):
        """intersection is against ``expected``, not a family list — an observed StatusLine tag
        must not count toward the hooks n/m even though it's present in ``observed``."""
        line = orch.summarize_scenario(
            ("Stop", "SessionEnd"),
            frozenset({"Stop", "SessionEnd", "StatusLine"}),
            {"StatusLine": 1},
        )
        assert line == "  ✓ hooks 2/2 expected · statusline ×1"


# ---------------------------------------------------------------------------
# Launch-time dialogs and readiness (cc-2.1.332)
# ---------------------------------------------------------------------------

# Real cc-2.1.332 dialog text (blank lines removed).
_TRUST_HEAD = (
    " Quick safety check: Is this a project you created or one you trust? (Like your own code, a well-known open"
    " source project, or work from your team). If not, take a moment to review what's in this\n"
    " folder first.\n"
    " Claude Code'll be able to read, edit, and execute files here.\n"
    " Security guide"
)
_BYPASS_HEAD = (
    "  WARNING: Claude Code running in Bypass Permissions mode\n"
    "  In Bypass Permissions mode, Claude Code will not ask for your approval before running potentially"
    " dangerous commands.\n"
    "  ..."
)
_DIALOG_FOOTER = " Enter to confirm · Esc to cancel"
_MANUAL_FOOTER = "  ⏸ manual mode on · ? for shortcuts · ← for agents"
_BYPASS_FOOTER = "  ⏵⏵ bypass permissions on (shift+tab to cycle)"


class _DialogTmux:
    """A scripted launch: a queue of dialogs (head, options, accept index, initial focus), then a
    ready footer. Down moves focus (unless ``swallow_down``); Enter on the accept option dismisses the
    dialog, Enter on any other option "exits" the session. Records (key, focused label) per press."""

    def __init__(self, dialogs, *, ready=_MANUAL_FOOTER, swallow_down=False):
        self._dialogs = [list(d) for d in dialogs]
        self._ready = ready
        self._swallow_down = swallow_down
        self.keys: list[tuple[str, str | None]] = []
        self.exited = False

    def _focused(self):
        if not self._dialogs:
            return None
        _, options, _, focus = self._dialogs[0]
        return options[focus]

    def has_session(self, name):
        return not self.exited

    def send_key(self, name, key):
        self.keys.append((key, self._focused()))
        if self.exited or not self._dialogs:
            return
        dialog = self._dialogs[0]
        _, options, accept, focus = dialog
        if key == "Down" and not self._swallow_down:
            dialog[3] = (focus + 1) % len(options)
        elif key == "Enter":
            if focus == accept:
                self._dialogs.pop(0)
            else:
                self.exited = True

    def capture_pane(self, name):
        if self.exited:
            return ""
        if not self._dialogs:
            return "❯ \n" + self._ready
        head, options, _, focus = self._dialogs[0]
        rows = [f" ❯ {o}" if i == focus else f"   {o}" for i, o in enumerate(options)]
        return "\n".join([head, *rows, _DIALOG_FOOTER])


def _trust(focus=0):
    return (_TRUST_HEAD, ["No, exit", "Yes, I trust this folder"], 1, focus)


def _bypass(focus=0):
    return (_BYPASS_HEAD, ["No, exit", "Yes, I accept"], 1, focus)


def _wait(fake, timeout_s=30.0):
    state = {"t": 0.0}

    def sleep(s):
        state["t"] += s

    def clock():
        state["t"] += 0.01
        return state["t"]

    return orch._wait_ready(fake, "s", timeout_s, sleep, clock, poll=1.0)


class TestWaitReady:
    def test_wait_ready__trust_dialog_no_focused_first__moves_down_then_enters(self):
        fake = _DialogTmux([_trust(focus=0)])
        assert _wait(fake) is True
        assert [k for k, _ in fake.keys] == ["Down", "Enter"]
        assert ("Enter", "No, exit") not in fake.keys
        assert not fake.exited

    def test_wait_ready__trust_dialog_yes_focused_first__enters_without_moving(self):
        fake = _DialogTmux([_trust(focus=1)])  # older CC: "Yes" default-highlighted
        assert _wait(fake) is True
        assert [k for k, _ in fake.keys] == ["Enter"]

    def test_wait_ready__bypass_warning_dialog__accepts_yes_i_accept(self):
        fake = _DialogTmux([_bypass(focus=0)], ready=_BYPASS_FOOTER)
        assert _wait(fake) is True
        assert fake.keys == [("Down", "No, exit"), ("Enter", "Yes, I accept")]

    def test_wait_ready__trust_then_bypass__each_accepted_once(self):
        fake = _DialogTmux([_trust(), _bypass()], ready=_BYPASS_FOOTER)
        assert _wait(fake) is True
        assert [label for k, label in fake.keys if k == "Enter"] == ["Yes, I trust this folder", "Yes, I accept"]
        assert not fake.exited

    def test_wait_ready__accept_option_never_focused__never_sends_enter_and_returns_false(self):
        fake = _DialogTmux([_trust(focus=0)], swallow_down=True)
        assert _wait(fake, timeout_s=10.0) is False
        assert "Enter" not in [k for k, _ in fake.keys]
        assert not fake.exited

    def test_wait_ready__bypass_mode_footer__returns_true(self):
        fake = _DialogTmux([], ready=_BYPASS_FOOTER)
        assert _wait(fake) is True
        assert fake.keys == []

    def test_wait_ready__manual_mode_footer__returns_true(self):
        fake = _DialogTmux([], ready=_MANUAL_FOOTER)
        assert _wait(fake) is True
        assert fake.keys == []

    def test_wait_ready__manual_mode_footer_with_statusline__returns_true(self):
        # cc-2.1.332 with a statusline configured (every capture scenario) drops "? for shortcuts".
        fake = _DialogTmux([], ready="  ⏸ manual mode on · ← for agents")
        assert _wait(fake) is True

    def test_wait_ready__no_ready_marker__times_out_false(self):
        fake = _DialogTmux([], ready="  Loading…")
        assert _wait(fake, timeout_s=5.0) is False


# ---------------------------------------------------------------------------
# Battery-wide default permission mode
# ---------------------------------------------------------------------------


def _argv_for(scenario, tmp_path, fast_clock, **kwargs) -> list[str]:
    captured: list[str] = []

    class _ArgvTmux(FakeTmux):
        def new_session(self, name, cwd, command, env=None):
            captured.extend(command)
            super().new_session(name, cwd, command, env)

    orch.run_scenario(
        scenario,
        environment_plugins=ENVIRONMENT_PLUGINS,
        claude_bin="claude",
        settings_path=tmp_path / "probe-settings.json",
        spool_dir=tmp_path / "spool",
        sandbox_root=tmp_path / "sandbox",
        cc_version="2.1.332",
        batch_id="b1",
        tmux=_ArgvTmux(),
        sleep=lambda _: None,
        clock=fast_clock,
        **kwargs,
    )
    return captured


class TestDefaultPermissionMode:
    def test_run_scenario__no_scenario_mode_meta_default_set__argv_uses_meta_default(self, tmp_path, fast_clock):
        argv = _argv_for(
            make_scenario(id="s", prompt="go"), tmp_path, fast_clock, default_permission_mode="bypassPermissions"
        )
        assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"

    def test_run_scenario__scenario_mode_set__overrides_meta_default(self, tmp_path, fast_clock):
        argv = _argv_for(
            make_scenario(id="s", prompt="go", permission_mode="default"),
            tmp_path,
            fast_clock,
            default_permission_mode="bypassPermissions",
        )
        assert argv.count("--permission-mode") == 1
        assert argv[argv.index("--permission-mode") + 1] == "default"

    def test_run_scenario__neither_set__no_permission_mode_flag(self, tmp_path, fast_clock):
        argv = _argv_for(make_scenario(id="s", prompt="go"), tmp_path, fast_clock)
        assert "--permission-mode" not in argv

    def test_run_scenarios__meta_default_permission_mode__reaches_scenario_argv(self, tmp_path, monkeypatch):
        """Wiring: run_scenarios passes manifest.meta.default_permission_mode through to run_scenario."""
        tmux = _VersionedFakeTmux()
        manifest = replace(TestRunScenariosFamilyWiring._make_manifest(None), meta=Meta(default_permission_mode="plan"))
        monkeypatch.setattr(orch, "Tmux", lambda: tmux)
        orch.run_scenarios(
            manifest,
            ENVIRONMENT_PLUGINS,
            orch.CapturePaths(
                probe=tmp_path / "capture_harness" / "hooks" / "probe.py",
                captures=tmp_path / "captures",
                spool=tmp_path / "spool",
                sandbox=tmp_path / "sandbox",
            ),
            claude=orch.ClaudeInstall(bin="claude", version="2.1.168"),
        )
        (command,) = [c[2] for c in tmux.calls if c[0] == "new_session"]
        assert command[command.index("--permission-mode") + 1] == "plan"
