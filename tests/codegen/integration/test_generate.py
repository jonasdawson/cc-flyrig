"""Tests for the entrypoint generator (generate.Generator + render + __main__ CLI).

Generation is exercised end-to-end: the Generator writes a formatted entrypoint that ast-parses and
matches a committed golden, and the generated module's handle()/main() behave as documented. The CLI
composition root is covered for the happy path and the unknown-event boundary error.

Group 2 adds parametrized tests over all 30 events (generation + golden match + round-trip) and
pattern-specific behavior tests for the structurally distinct patterns (none, worktree-path-return,
top-level-decision).
"""

import ast
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from cc_flyrig.codegen import __main__ as cli
from cc_flyrig.codegen import toolchain
from cc_flyrig.codegen.generate import Generator
from cc_flyrig.codegen.load import IntermediateRepresentationLoader
from cc_flyrig.codegen.render import EntrypointRenderer, template_runtimes
from cc_flyrig.codegen.settings import Settings
from cc_flyrig.codegen.translate import snake_case

ROOT = Path(__file__).parent.parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas"
GOLDEN_DIR = Path(__file__).parent.parent / "golden"
CAPTURES_DIR = ROOT / "captures" / "cc-2.1.177"
CC_VERSION = "2.1.177"

# All 30 hook events (excluding CommonOutput which is a shared base, not an event).
ALL_EVENTS = [
    "ConfigChange",
    "CwdChanged",
    "Elicitation",
    "ElicitationResult",
    "FileChanged",
    "InstructionsLoaded",
    "MessageDisplay",
    "Notification",
    "PermissionDenied",
    "PermissionRequest",
    "PostCompact",
    "PostToolBatch",
    "PostToolUse",
    "PostToolUseFailure",
    "PreCompact",
    "PreToolUse",
    "SessionEnd",
    "SessionStart",
    "Setup",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "TaskCompleted",
    "TaskCreated",
    "TeammateIdle",
    "UserPromptExpansion",
    "UserPromptSubmit",
    "WorktreeCreate",
    "WorktreeRemove",
]

# WorktreeRemove has no captured payload (confirmed CC bug in the capture harness as of cc-2.1.177);
# generation is tested but the round-trip is skipped.
_NO_CAPTURE = {"WorktreeRemove"}

# Events whose capture file has at least one payload, collected lazily to avoid I/O at import.
_CAPTURE_PAYLOADS: dict[str, list[dict]] = {}


def _strip_nulls(payload: dict) -> dict:
    """Remove top-level explicit JSON null values from an Input payload dict.

    ``to_dict()`` omits ``None`` optional fields; a payload with explicit nulls at the top level
    (e.g. PreCompact's ``custom_instructions: null``) must be normalized before comparing with the
    round-trip result. Stripping is *not* recursive: pass-through ``dict`` fields (like
    ``tool_response``) are returned by ``to_dict()`` unchanged, so their nested nulls must not be
    touched.
    """
    return {k: v for k, v in payload.items() if v is not None}


def _capture_payloads(event: str) -> list[dict]:
    if event not in _CAPTURE_PAYLOADS:
        path = CAPTURES_DIR / f"{event}.jsonl"
        _CAPTURE_PAYLOADS[event] = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return _CAPTURE_PAYLOADS[event]


def _generate(event: str, out_dir: Path) -> Path:
    settings = Settings(event=event, cc_version=CC_VERSION, schemas_dir=SCHEMAS_DIR, out_dir=out_dir)
    profile = toolchain.load_runtime_profile(SCHEMAS_DIR / f"cc-{CC_VERSION}", "python")
    generator = Generator(
        settings=settings,
        profile=profile,
        loader=IntermediateRepresentationLoader(settings),
        renderer=EntrypointRenderer(),
    )
    return generator.run()


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass(slots=True) resolves annotations via sys.modules
    spec.loader.exec_module(module)
    return module


def _golden(event: str) -> Path:
    return GOLDEN_DIR / snake_case(event)


# ---------------------------------------------------------------------------
# Group 1: PreToolUse golden-path tests (kept for regression)
# ---------------------------------------------------------------------------

GOLDEN_PRE_TOOL_USE_DIR = GOLDEN_DIR / "pre_tool_use"
CAPTURE_PRE_TOOL_USE = CAPTURES_DIR / "PreToolUse.jsonl"


@pytest.fixture(scope="module")
def harness_module():
    return _load_module(GOLDEN_PRE_TOOL_USE_DIR / "_harness.py", "pre_tool_use_harness")


class TestGenerate:
    def test_run__pre_tool_use__writes_package(self, tmp_path):
        out_dir = _generate("PreToolUse", tmp_path)
        assert out_dir == tmp_path / "pre_tool_use"
        assert (out_dir / "_harness.py").exists()
        assert (out_dir / "__main__.py").exists()
        ast.parse((out_dir / "_harness.py").read_text())
        ast.parse((out_dir / "__main__.py").read_text())

    def test_run__pre_tool_use__matches_golden_fixture(self, tmp_path):
        out_dir = _generate("PreToolUse", tmp_path)
        for fname in ("_harness.py", "__main__.py"):
            assert (out_dir / fname).read_text() == (GOLDEN_PRE_TOOL_USE_DIR / fname).read_text()

    def test_run__pre_tool_use__stamps_cc_version_and_event(self, tmp_path):
        out_dir = _generate("PreToolUse", tmp_path)
        text = (out_dir / "_harness.py").read_text()
        assert "cc-2.1.177" in text
        assert "Event: PreToolUse" in text

    def test_run__python_codegen_config__no_checker_invoked(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", calls.append)

        _generate("PreToolUse", tmp_path)

        assert calls == []


class TestGeneratedBehavior:
    def test_handle__stub__contains_not_implemented(self):
        stub_text = (GOLDEN_PRE_TOOL_USE_DIR / "__main__.py").read_text()
        assert "raise NotImplementedError" in stub_text

    def test_run__handle_returns_deny__prints_decision_and_exits_zero(self, harness_module, monkeypatch, capsys):
        deny = harness_module.PreToolUseOutput(
            hook_specific_output=harness_module.PreToolUseHookSpecificOutput(
                hook_event_name="PreToolUse", permission_decision="deny"
            )
        )
        monkeypatch.setattr(harness_module.sys, "stdin", io.StringIO(CAPTURE_PRE_TOOL_USE.read_text().splitlines()[0]))
        assert harness_module.run(lambda event: deny) == 0
        emitted = json.loads(capsys.readouterr().out)
        assert emitted["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_run__handle_returns_none__emits_nothing(self, harness_module, monkeypatch, capsys):
        monkeypatch.setattr(harness_module.sys, "stdin", io.StringIO(CAPTURE_PRE_TOOL_USE.read_text().splitlines()[0]))
        assert harness_module.run(lambda event: None) == 0
        assert capsys.readouterr().out == ""


class TestCli:
    def test_main__generate_pre_tool_use__writes_package_and_returns_zero(self, tmp_path):
        argv = ["generate", "--event", "PreToolUse", "--schemas-dir", str(SCHEMAS_DIR), "--out-dir", str(tmp_path)]
        assert cli.main(argv) == 0
        # --out-dir is the scaffolds-root replacement: the <runtime>/cc-<version>/ tree nests inside.
        base = tmp_path / "python" / f"cc-{cli._latest_cc_version(SCHEMAS_DIR, 'hooks')}"
        assert (base / "pre_tool_use" / "_harness.py").exists()
        assert (base / "pre_tool_use" / "__main__.py").exists()

    def test_main__unknown_event__returns_nonzero(self, tmp_path, capsys):
        argv = ["generate", "--event", "NoSuchEvent", "--schemas-dir", str(SCHEMAS_DIR), "--out-dir", str(tmp_path)]
        assert cli.main(argv) == 2
        assert "unknown event" in capsys.readouterr().err

    def test_main__no_event__generates_all_events(self, tmp_path):
        # No --cc-version pin either: families resolve independently (ADR 0010) to their own latest.
        # Both resolve to cc-2.1.200 today (a full version shipping both hooks.schema.json and
        # statusline.schema.json), and every family nests under python/cc-<version>/ in one run.
        hooks_version = cli._latest_cc_version(SCHEMAS_DIR, "hooks")
        statusline_version = cli._latest_cc_version(SCHEMAS_DIR, "statusline")
        assert (SCHEMAS_DIR / f"cc-{statusline_version}" / "statusline.schema.json").is_file()

        argv = ["generate", "--schemas-dir", str(SCHEMAS_DIR), "--out-dir", str(tmp_path)]
        assert cli.main(argv) == 0
        # Each family nests under python/cc-<its own resolved version>/ inside the --out-dir root.
        hooks_base = tmp_path / "python" / f"cc-{hooks_version}"
        statusline_base = tmp_path / "python" / f"cc-{statusline_version}"
        for event in ALL_EVENTS:
            assert (hooks_base / snake_case(event) / "_harness.py").exists()
            assert (hooks_base / snake_case(event) / "__main__.py").exists()
        assert f"cc-{hooks_version}" in (hooks_base / "pre_tool_use" / "_harness.py").read_text()

        for event in ("StatusLine", "SubagentStatusLine"):
            harness_text = (statusline_base / snake_case(event) / "_harness.py").read_text()
            assert (statusline_base / snake_case(event) / "__main__.py").exists()
            assert f"cc-{statusline_version}" in harness_text

    def test_main__checker_binary_missing__returns_nonzero_clean_error(self, tmp_path, capsys, monkeypatch):
        def fake(source):
            raise FileNotFoundError("esbuild not found — run `npm install`")

        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", fake)
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "typescript",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--cc-version",
            "2.1.185",
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 1
        assert "esbuild not found" in capsys.readouterr().err
        assert not (tmp_path / "typescript" / "cc-2.1.185" / "pre_tool_use").exists()

    def test_main__runtime_with_no_templates__exits_two_with_clean_message(self, tmp_path, capsys):
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "no-such-runtime",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        with pytest.raises(SystemExit) as exc_info:
            cli.main(argv)
        assert exc_info.value.code == 2
        assert "no templates for runtime" in capsys.readouterr().err

    def test_main__runtime_profile_missing_required_key__returns_nonzero_clean_error(self, tmp_path, capsys):
        schemas_dir = tmp_path / "schemas"
        version_dir = schemas_dir / f"cc-{CC_VERSION}"
        lang_dir = version_dir / "lang"
        lang_dir.mkdir(parents=True)
        (lang_dir / "python.json").write_text(
            json.dumps(
                {
                    "language": "python",
                    "extension": "py",
                    "stub_name": "__main__",
                    # "formatter" deliberately omitted
                    "checker": None,
                }
            )
        )
        source_schema = SCHEMAS_DIR / f"cc-{CC_VERSION}" / "hooks.schema.json"
        (version_dir / "hooks.schema.json").write_text(source_schema.read_text())

        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "python",
            "--schemas-dir",
            str(schemas_dir),
            "--cc-version",
            CC_VERSION,
            "--out-dir",
            str(tmp_path / "out"),
        ]
        assert cli.main(argv) == 2
        assert "formatter" in capsys.readouterr().err


class TestRuntimeAll:
    """`--runtime all` fans out over every runtime with a template set, each nesting under its own
    <runtime>/cc-<version>/ subtree of --out-dir. A runtime that cannot be generated (missing profile
    or absent toolchain) is skipped-and-reported with a nonzero exit, never aborting the others."""

    _TS_VERSION = "2.1.185"  # ships both python and typescript lang profiles

    def test_template_runtimes__lists_runtimes_with_full_template_set(self):
        assert template_runtimes() == ["python", "typescript"]

    def test_main__runtime_all__writes_every_runtime_under_its_own_subtree(self, tmp_path, monkeypatch):
        # No-op the esbuild checker so TypeScript generation doesn't require the real binary here.
        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", lambda source: None)
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "all",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--cc-version",
            self._TS_VERSION,
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        # Both runtimes generated into disjoint subtrees -- no collision despite the shared --out-dir.
        assert (tmp_path / "python" / f"cc-{self._TS_VERSION}" / "pre_tool_use" / "__main__.py").exists()
        assert (tmp_path / "typescript" / f"cc-{self._TS_VERSION}" / "pre_tool_use" / "index.ts").exists()

    def test_main__runtime_all__absent_toolchain_skips_runtime_and_exits_nonzero(self, tmp_path, capsys, monkeypatch):
        def fake(source):
            raise FileNotFoundError("esbuild not found — run `npm install`")

        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", fake)
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "all",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--cc-version",
            self._TS_VERSION,
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 1
        err = capsys.readouterr().err
        assert "skipping typescript" in err
        assert "esbuild not found" in err
        # Python still generated; the probe fires before any TypeScript file is written (no partial tree).
        assert (tmp_path / "python" / f"cc-{self._TS_VERSION}" / "pre_tool_use" / "__main__.py").exists()
        assert not (tmp_path / "typescript" / f"cc-{self._TS_VERSION}").exists()

    def test_main__runtime_all__missing_profile_skips_runtime_and_exits_nonzero(self, tmp_path, capsys):
        # Synthesize a schemas dir that ships a python profile but no typescript profile for the version.
        schemas_dir = tmp_path / "schemas"
        version_dir = schemas_dir / f"cc-{self._TS_VERSION}"
        (version_dir / "lang").mkdir(parents=True)
        source = SCHEMAS_DIR / f"cc-{self._TS_VERSION}"
        (version_dir / "lang" / "python.json").write_text((source / "lang" / "python.json").read_text())
        (version_dir / "hooks.schema.json").write_text((source / "hooks.schema.json").read_text())
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--runtime",
            "all",
            "--schemas-dir",
            str(schemas_dir),
            "--cc-version",
            self._TS_VERSION,
            "--out-dir",
            str(tmp_path / "out"),
        ]
        assert cli.main(argv) == 1
        assert "skipping typescript" in capsys.readouterr().err
        assert (tmp_path / "out" / "python" / f"cc-{self._TS_VERSION}" / "pre_tool_use" / "__main__.py").exists()
        assert not (tmp_path / "out" / "typescript").exists()


class TestBumpCopierDefault:
    def _make_version_file(self, parent: Path, version: str) -> Path:
        p = parent / "VERSION"
        p.write_text(version + "\n")
        return p

    def test_bump__newer_version__updates_version_file(self, tmp_path):
        out_dir = tmp_path / "cc-9.9.9"
        out_dir.mkdir()
        version_file = self._make_version_file(tmp_path, "1.0.0")
        cli._bump_copier_default(out_dir, "9.9.9")
        assert version_file.read_text().strip() == "9.9.9"

    def test_bump__older_version__no_change(self, tmp_path):
        out_dir = tmp_path / "cc-1.0.0"
        out_dir.mkdir()
        version_file = self._make_version_file(tmp_path, "9.9.9")
        cli._bump_copier_default(out_dir, "1.0.0")
        assert version_file.read_text().strip() == "9.9.9"

    def test_bump__same_version__no_change(self, tmp_path):
        out_dir = tmp_path / "cc-1.0.0"
        out_dir.mkdir()
        version_file = self._make_version_file(tmp_path, "1.0.0")
        cli._bump_copier_default(out_dir, "1.0.0")
        assert version_file.read_text().strip() == "1.0.0"

    def test_bump__no_version_file__no_error(self, tmp_path):
        out_dir = tmp_path / "cc-9.9.9"
        out_dir.mkdir()
        cli._bump_copier_default(out_dir, "9.9.9")  # must not raise


# ---------------------------------------------------------------------------
# Group 2: all 30 events — generation + golden match
# ---------------------------------------------------------------------------


class TestGenerateAllEvents:
    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__output_ast_parses(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        ast.parse((out_dir / "_harness.py").read_text())
        ast.parse((out_dir / "__main__.py").read_text())

    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__matches_golden_fixture(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        golden = _golden(event)
        for fname in ("_harness.py", "__main__.py"):
            assert (out_dir / fname).read_text() == (golden / fname).read_text()

    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__stamps_cc_version_and_event_name(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        text = (out_dir / "_harness.py").read_text()
        assert "cc-2.1.177" in text
        assert f"Event: {event}" in text


# ---------------------------------------------------------------------------
# Group 2: round-trip over every captured payload (all events with captures)
# ---------------------------------------------------------------------------

# Build the parametrize list: (event, payload_index) for every captured line.
_ROUND_TRIP_PARAMS: list[tuple[str, int]] = []
for _ev in ALL_EVENTS:
    if _ev in _NO_CAPTURE:
        continue
    for _i in range(len(_capture_payloads(_ev))):
        _ROUND_TRIP_PARAMS.append((_ev, _i))


class TestRoundTripAllEvents:
    """Round-trip every captured payload through the committed golden module's from_dict/to_dict."""

    @pytest.mark.parametrize(
        "event,payload_index",
        _ROUND_TRIP_PARAMS,
        ids=[f"{ev}[{i}]" for ev, i in _ROUND_TRIP_PARAMS],
    )
    def test_from_dict__captured_payload__round_trips(self, event, payload_index):
        module = _load_module(_golden(event) / "_harness.py", f"{snake_case(event)}_harness_rt_{payload_index}")
        payload = _capture_payloads(event)[payload_index]
        input_class = getattr(module, f"{event}Input")
        restored = input_class.from_dict(payload).to_dict()
        # to_dict() omits None optionals; normalize the payload to match (e.g. PreCompact's
        # custom_instructions: null appears explicitly in captured data but is omitted on output).
        assert restored == _strip_nulls(payload)

    @pytest.mark.skip(
        reason=(
            "no captured payload: WorktreeRemove has no captures (confirmed CC bug in capture harness as of cc-2.1.177)"
        )
    )
    def test_from_dict__worktree_remove__no_capture_placeholder(self):
        pass


# ---------------------------------------------------------------------------
# Group 2: pattern-specific behavior tests
# ---------------------------------------------------------------------------


class TestPatternBehavior:
    """Verify the structurally distinct run() patterns behave as specified."""

    # -- none pattern ---------------------------------------------------------

    def test_run__none_pattern__handle_called_and_no_output(self, monkeypatch, capsys):
        # InstructionsLoaded uses the "none" pattern: handle() -> None, no JSON output.
        harness = _load_module(_golden("InstructionsLoaded") / "_harness.py", "instructions_loaded_harness_pat")
        payload = _capture_payloads("InstructionsLoaded")[0]
        called = []
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        ret = harness.run(lambda event: called.append(event))
        assert ret == 0
        assert len(called) == 1
        assert capsys.readouterr().out == ""

    def test_run__none_pattern__cwd_changed_handle_called(self, monkeypatch, capsys):
        # CwdChanged also uses "none"; spot-check a second event.
        harness = _load_module(_golden("CwdChanged") / "_harness.py", "cwd_changed_harness_pat")
        payload = _capture_payloads("CwdChanged")[0]
        called = []
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: called.append(True)) == 0
        assert called
        assert capsys.readouterr().out == ""

    # -- worktree-path-return pattern -----------------------------------------

    def test_run__worktree_path_return__prints_bare_path(self, monkeypatch, capsys):
        harness = _load_module(_golden("WorktreeCreate") / "_harness.py", "worktree_create_harness_pat")
        payload = _capture_payloads("WorktreeCreate")[0]
        hso = harness.WorktreeCreateHookSpecificOutput(
            hook_event_name="WorktreeCreate", worktree_path="/tmp/my-worktree"
        )
        decision = harness.WorktreeCreateOutput(hook_specific_output=hso)
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        ret = harness.run(lambda event: decision)
        assert ret == 0
        out = capsys.readouterr().out
        # Bare string, not JSON.
        assert out.strip() == "/tmp/my-worktree"
        # Must not be JSON-encoded.
        with pytest.raises(json.JSONDecodeError):
            json.loads(out.strip().strip('"'))

    def test_run__worktree_path_return__none_decision_emits_nothing(self, monkeypatch, capsys):
        harness = _load_module(_golden("WorktreeCreate") / "_harness.py", "worktree_create_harness_none")
        payload = _capture_payloads("WorktreeCreate")[0]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: None) == 0
        assert capsys.readouterr().out == ""

    # -- top-level-decision pattern -------------------------------------------

    def test_run__top_level_decision__prints_json_on_block(self, monkeypatch, capsys):
        # PostToolUse uses top-level-decision.
        harness = _load_module(_golden("PostToolUse") / "_harness.py", "post_tool_use_harness_pat")
        payload = _capture_payloads("PostToolUse")[0]
        block = harness.PostToolUseOutput(decision="block", reason="blocked by policy")
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: block) == 0
        emitted = json.loads(capsys.readouterr().out)
        assert emitted["decision"] == "block"
        assert emitted["reason"] == "blocked by policy"

    def test_run__top_level_decision__none_decision_emits_nothing(self, monkeypatch, capsys):
        harness = _load_module(_golden("PostToolUse") / "_harness.py", "post_tool_use_harness_none")
        payload = _capture_payloads("PostToolUse")[0]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: None) == 0
        assert capsys.readouterr().out == ""

    # -- context-only pattern -------------------------------------------------

    def test_run__context_only__prints_json_with_hook_specific_output(self, monkeypatch, capsys):
        harness = _load_module(_golden("SessionStart") / "_harness.py", "session_start_harness_pat")
        payload = _capture_payloads("SessionStart")[0]
        hso = harness.SessionStartHookSpecificOutput(hook_event_name="SessionStart", additional_context="extra context")
        decision = harness.SessionStartOutput(hook_specific_output=hso)
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: decision) == 0
        emitted = json.loads(capsys.readouterr().out)
        assert emitted["hookSpecificOutput"]["additionalContext"] == "extra context"


# ---------------------------------------------------------------------------
# Shape coverage — type shapes PreToolUse does not exercise
# (relocated from the deleted test_emit.py; these load the committed golden
# modules, so they need no ModelEmitter — they exercise the rendered output.)
# ---------------------------------------------------------------------------


class TestNewShapes:
    """End-to-end coverage for ``list[<dataclass>]``, ``oneOf`` passthrough, and alias collapse."""

    @pytest.fixture(scope="class")
    @classmethod
    def ptb_module(cls):
        return _load_module(GOLDEN_DIR / "post_tool_batch" / "_harness.py", "post_tool_batch_ns")

    @pytest.fixture(scope="class")
    @classmethod
    def pr_module(cls):
        return _load_module(GOLDEN_DIR / "permission_request" / "_harness.py", "permission_request_ns")

    # -- list[dataclass]: ToolCallEntry (synthetic, all captures have empty tool_calls) ----------

    def test_post_tool_batch_input__synthetic_list_dataclass_entry__round_trips(self, ptb_module):
        entry = ptb_module.ToolCallEntry(
            tool_name="Write",
            tool_input={"file_path": "/tmp/f.txt", "content": "hello"},
            tool_use_id="tu_001",
            tool_response="OK",
        )
        input_obj = ptb_module.PostToolBatchInput(
            session_id="s1",
            transcript_path="/tmp/t.jsonl",
            cwd="/tmp",
            hook_event_name="PostToolBatch",
            tool_calls=[entry],
        )
        wire = input_obj.to_dict()
        assert len(wire["tool_calls"]) == 1
        assert wire["tool_calls"][0]["tool_name"] == "Write"
        assert wire["tool_calls"][0]["tool_response"] == "OK"
        # Round-trip: from_dict should reconstruct the same object.
        restored = ptb_module.PostToolBatchInput.from_dict(wire)
        assert restored.tool_calls[0].tool_name == "Write"
        assert restored.to_dict() == wire

    def test_post_tool_batch_input__empty_tool_calls_capture__round_trips(self, ptb_module):
        # All captured PostToolBatch payloads have empty tool_calls; verify round-trip.
        payload = json.loads((CAPTURES_DIR / "PostToolBatch.jsonl").read_text().splitlines()[0])
        restored = ptb_module.PostToolBatchInput.from_dict(payload).to_dict()
        assert restored == payload

    # -- oneOf passthrough: ToolCallEntry.tool_response (str | list[dict]) -------------------

    def test_tool_call_entry__oneof_str_response__passes_through(self, ptb_module):
        entry = ptb_module.ToolCallEntry(
            tool_name="Read", tool_input={}, tool_use_id="tu_002", tool_response="file contents"
        )
        wire = entry.to_dict()
        assert wire["tool_response"] == "file contents"
        assert ptb_module.ToolCallEntry.from_dict(wire).tool_response == "file contents"

    def test_tool_call_entry__oneof_list_dict_response__passes_through(self, ptb_module):
        content_blocks = [{"type": "text", "text": "hello"}, {"type": "image"}]
        entry = ptb_module.ToolCallEntry(
            tool_name="Read", tool_input={}, tool_use_id="tu_003", tool_response=content_blocks
        )
        wire = entry.to_dict()
        assert wire["tool_response"] == content_blocks
        assert ptb_module.ToolCallEntry.from_dict(wire).tool_response == content_blocks

    # -- alias collapse + list[dataclass]: PermissionSuggestion -> PermissionUpdateEntry ------

    def test_permission_request_input__alias_list_dataclass_capture__round_trips(self, pr_module):
        # The single PermissionRequest capture has permission_suggestions: [PermissionUpdateEntry].
        # This exercises alias collapse (PermissionSuggestion -> PermissionUpdateEntry) and
        # list[dataclass] from_dict/to_dict end-to-end.
        payload = json.loads((CAPTURES_DIR / "PermissionRequest.jsonl").read_text().splitlines()[0])
        restored = pr_module.PermissionRequestInput.from_dict(payload).to_dict()
        assert restored == payload

    def test_permission_request_input__captured_payload__deserializes_permission_update_entry(self, pr_module):
        payload = json.loads((CAPTURES_DIR / "PermissionRequest.jsonl").read_text().splitlines()[0])
        event = pr_module.PermissionRequestInput.from_dict(payload)
        assert event.permission_suggestions is not None
        assert len(event.permission_suggestions) == 1
        entry = event.permission_suggestions[0]
        assert isinstance(entry, pr_module.PermissionUpdateEntry)
        assert entry.type == "setMode"
        assert entry.destination == "session"
        assert entry.mode == "acceptEdits"

    # -- nested-nested dataclass: PermissionRequestHookSpecificDecision -------------------

    def test_permission_request_output__nested_decision__round_trips(self, pr_module):
        decision = pr_module.PermissionRequestHookSpecificDecision(
            behavior="allow",
            updated_permissions=[
                pr_module.PermissionUpdateEntry(type="setMode", destination="session", mode="acceptEdits")
            ],
        )
        hso = pr_module.PermissionRequestHookSpecificOutput(hook_event_name="PermissionRequest", decision=decision)
        output = pr_module.PermissionRequestOutput(hook_specific_output=hso)
        wire = output.to_dict()
        assert wire["hookSpecificOutput"]["decision"]["behavior"] == "allow"
        assert wire["hookSpecificOutput"]["decision"]["updatedPermissions"][0]["mode"] == "acceptEdits"
        restored = pr_module.PermissionRequestOutput.from_dict(wire)
        assert restored.hook_specific_output.decision.behavior == "allow"
        assert restored.to_dict() == wire
