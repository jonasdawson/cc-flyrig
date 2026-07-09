"""Unit tests for the tmux CLI wrapper (cli.tmux)."""

import subprocess

from cc_flyrig.cli.tmux import NAMED_KEYS, Tmux


def _make_tmux(returncode: int = 0, stdout: str = "") -> tuple[Tmux, list[list[str]]]:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return Tmux(runner=runner), calls


class TestNewSession:
    def test_new_session__minimal__builds_detached_session_argv(self):
        tmux, calls = _make_tmux()
        tmux.new_session("s1", "/cwd", ["claude"])
        assert calls[0][:6] == ["tmux", "new-session", "-d", "-s", "s1", "-c"]
        assert "/cwd" in calls[0]
        assert "claude" in calls[0]

    def test_new_session__env__interleaves_e_flags(self):
        tmux, calls = _make_tmux()
        tmux.new_session("s1", "/cwd", ["claude"], env={"FOO": "bar", "BAZ": "qux"})
        argv = calls[0]
        env_pairs = {argv[i + 1] for i, v in enumerate(argv) if v == "-e"}
        assert env_pairs == {"FOO=bar", "BAZ=qux"}

    def test_new_session__no_env__no_e_flags(self):
        tmux, calls = _make_tmux()
        tmux.new_session("s1", "/cwd", ["claude"])
        assert "-e" not in calls[0]

    def test_new_session__command__appended_last(self):
        tmux, calls = _make_tmux()
        tmux.new_session("s1", "/cwd", ["claude", "--dangerously-skip-permissions"])
        assert calls[0][-2:] == ["claude", "--dangerously-skip-permissions"]


class TestHasSession:
    def test_has_session__returncode_zero__returns_true(self):
        tmux, _ = _make_tmux(returncode=0)
        assert tmux.has_session("s1") is True

    def test_has_session__nonzero_returncode__returns_false(self):
        tmux, _ = _make_tmux(returncode=1)
        assert tmux.has_session("s1") is False

    def test_has_session__any_name__builds_has_session_argv(self):
        tmux, calls = _make_tmux()
        tmux.has_session("s1")
        assert calls[0] == ["tmux", "has-session", "-t", "s1"]


class TestSendText:
    def test_send_text__plain_text__builds_literal_send_keys_argv(self):
        tmux, calls = _make_tmux()
        tmux.send_text("s1", "hello")
        assert calls[0] == ["tmux", "send-keys", "-t", "s1", "-l", "hello"]

    def test_send_text__key_named_text__still_sent_literally(self):
        tmux, calls = _make_tmux()
        tmux.send_text("s1", "Enter")  # "Enter" sent as text must not be interpreted as a key
        assert "-l" in calls[0]


class TestSendKey:
    def test_send_key__named_key__builds_send_keys_argv(self):
        tmux, calls = _make_tmux()
        tmux.send_key("s1", "Enter")
        assert calls[0] == ["tmux", "send-keys", "-t", "s1", "Enter"]

    def test_send_key__named_key__omits_literal_flag(self):
        tmux, calls = _make_tmux()
        tmux.send_key("s1", "Enter")
        assert "-l" not in calls[0]


class TestSendTokens:
    def test_send_tokens__named_key__dispatches_as_key(self):
        tmux, calls = _make_tmux()
        tmux.send_tokens("s1", ["Enter"])
        assert calls[0] == ["tmux", "send-keys", "-t", "s1", "Enter"]

    def test_send_tokens__plain_text__dispatches_as_literal(self):
        tmux, calls = _make_tmux()
        tmux.send_tokens("s1", ["hello"])
        assert "-l" in calls[0]

    def test_send_tokens__mixed_sequence__interleaves_key_and_text_calls(self):
        tmux, calls = _make_tmux()
        tmux.send_tokens("s1", ["hello", "Enter", "world"])
        assert len(calls) == 3
        assert "-l" in calls[0]  # "hello" → send_text
        assert "-l" not in calls[1]  # "Enter" → send_key
        assert "-l" in calls[2]  # "world" → send_text

    def test_send_tokens__every_named_key__routed_as_key_not_literal(self):
        tmux, calls = _make_tmux()
        for key in sorted(NAMED_KEYS):
            calls.clear()
            tmux.send_tokens("s1", [key])
            assert "-l" not in calls[0], f"{key!r} should be sent as a key, not literal text"


class TestCapturePane:
    def test_capture_pane__any_session__builds_capture_pane_argv(self):
        tmux, calls = _make_tmux()
        tmux.capture_pane("s1")
        assert calls[0] == ["tmux", "capture-pane", "-p", "-t", "s1"]

    def test_capture_pane__nonempty_pane__returns_stdout(self):
        tmux, _ = _make_tmux(stdout="❯ \n")
        assert tmux.capture_pane("s1") == "❯ \n"

    def test_capture_pane__empty_stdout__returns_empty_string(self):
        tmux, _ = _make_tmux(stdout="")
        assert tmux.capture_pane("s1") == ""


class TestKillSession:
    def test_kill_session__any_session__builds_kill_session_argv(self):
        tmux, calls = _make_tmux()
        tmux.kill_session("s1")
        assert calls[0] == ["tmux", "kill-session", "-t", "s1"]
