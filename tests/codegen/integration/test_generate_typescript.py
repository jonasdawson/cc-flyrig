"""Tests for the TypeScript runtime (generate.Generator with runtime="typescript").

Generation is exercised against the committed scaffolds tree as the byte-for-byte reference: each
event regenerates identically to scaffolds/typescript/cc-2.1.185/<event>/. Validation is layered:
esbuild syntax-gates every event at generation time (TestGenerateTypeScript skips cleanly without
it); tsc batch-typechecks the output in test_typecheck_typescript.py and at release; tsx executes
the round-trip and stub in test_roundtrip_typescript.py. TestTypeScriptShape pins the load-bearing
macro outputs structurally, independent of any of that tooling.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from cc_flyrig.codegen import toolchain
from cc_flyrig.codegen.generate import Generator
from cc_flyrig.codegen.load import IntermediateRepresentationLoader
from cc_flyrig.codegen.render import EntrypointRenderer
from cc_flyrig.codegen.settings import Settings
from cc_flyrig.codegen.translate import snake_case

ROOT = Path(__file__).parent.parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas"
_LOCAL_ESBUILD = ROOT / "node_modules" / ".bin" / "esbuild"
CC_VERSION = "2.1.185"
SCAFFOLDS_TS = ROOT / "scaffolds" / "typescript" / f"cc-{CC_VERSION}"

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

_PACKAGE_FILES = ("_harness.ts", "index.ts")


def _generate(event: str, out_dir: Path) -> Path:
    settings = Settings(event=event, cc_version=CC_VERSION, schemas_dir=SCHEMAS_DIR, out_dir=out_dir)
    profile = toolchain.load_runtime_profile(SCHEMAS_DIR / f"cc-{CC_VERSION}", "typescript")
    generator = Generator(
        settings=settings,
        profile=profile,
        loader=IntermediateRepresentationLoader(settings),
        renderer=EntrypointRenderer(),
    )
    return generator.run()


def _scaffold(event: str) -> Path:
    return SCAFFOLDS_TS / snake_case(event)


@pytest.mark.skipif(
    not (_LOCAL_ESBUILD.exists() or shutil.which("esbuild")),
    reason="esbuild not installed (run `npm install`) — TypeScript generation is now gated on it",
)
class TestGenerateTypeScript:
    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__writes_ts_package(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        assert out_dir == tmp_path / snake_case(event)
        for fname in _PACKAGE_FILES:
            assert (out_dir / fname).exists()

    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__matches_committed_scaffold(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        scaffold = _scaffold(event)
        for fname in _PACKAGE_FILES:
            assert (out_dir / fname).read_text() == (scaffold / fname).read_text()

    @pytest.mark.parametrize("event", ALL_EVENTS)
    def test_run__event__stamps_cc_version_and_event(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        text = (out_dir / "_harness.ts").read_text()
        assert f"cc-{CC_VERSION}" in text
        assert f"Event: {event}" in text


class TestTypeScriptShape:
    """Pin the load-bearing macro outputs via structural string assertions, independent of tsc."""

    @pytest.fixture(scope="class")
    @classmethod
    def pre_tool_use(cls):
        return (_scaffold("PreToolUse") / "_harness.ts").read_text()

    @pytest.fixture(scope="class")
    @classmethod
    def post_tool_batch(cls):
        return (_scaffold("PostToolBatch") / "_harness.ts").read_text()

    @pytest.fixture(scope="class")
    @classmethod
    def session_end(cls):
        return (_scaffold("SessionEnd") / "_harness.ts").read_text()

    # -- naming: camelCase field, verbatim wire key ----------------------------------------

    def test_shape__interface_field__is_camel_case(self, pre_tool_use):
        assert "  toolUseId: string;" in pre_tool_use

    def test_shape__parse__maps_camel_field_from_snake_wire_key(self, pre_tool_use):
        assert 'sessionId: data["session_id"],' in pre_tool_use

    def test_shape__serialize__writes_snake_wire_key_from_camel_field(self, pre_tool_use):
        assert 'result["session_id"] = obj.sessionId;' in pre_tool_use

    # -- enums: string-literal type alias, passthrough (no conversion) ---------------------

    def test_shape__enum__emits_string_literal_type_alias(self, pre_tool_use):
        assert 'export type PermissionMode = "default" | "plan" | "acceptEdits"' in pre_tool_use

    def test_shape__enum_field__passes_through_without_conversion(self, pre_tool_use):
        # A string-literal union is a string at runtime; no parse*/serialize* call (just the
        # optional null-coalesce on parse and a direct assignment on serialize).
        assert 'permissionMode: data["permission_mode"] ?? undefined,' in pre_tool_use
        assert "parsePermissionMode" not in pre_tool_use
        assert 'result["permission_mode"] = obj.permissionMode;' in pre_tool_use

    # -- optionals: ?: in interface, skip-undefined on serialize ---------------------------

    def test_shape__optional_field__uses_question_mark(self, pre_tool_use):
        assert "  permissionMode?: PermissionMode;" in pre_tool_use

    def test_shape__optional_serialize__guards_on_undefined(self, pre_tool_use):
        assert "if (obj.effort !== undefined) {" in pre_tool_use

    # -- nested dataclass: conditional parse, serialize call -------------------------------

    def test_shape__optional_nested_dataclass__parses_conditionally(self, pre_tool_use):
        assert 'effort: data["effort"] != null ? parseEffortObject(data["effort"]) : undefined,' in pre_tool_use

    def test_shape__nested_dataclass__serializes_via_helper(self, pre_tool_use):
        assert 'result["effort"] = serializeEffortObject(obj.effort);' in pre_tool_use

    # -- reserved word: no mangling (TS allows `continue` as a property) -------------------

    def test_shape__reserved_word_field__not_mangled(self, pre_tool_use):
        assert "  continue?: boolean;" in pre_tool_use
        assert 'result["continue"] = obj.continue;' in pre_tool_use

    # -- list[dataclass]: T[] type, .map(parse/serialize) ----------------------------------

    def test_shape__list_dataclass__uses_array_type(self, post_tool_batch):
        assert "  toolCalls: ToolCallEntry[];" in post_tool_batch

    def test_shape__list_dataclass__parses_with_map(self, post_tool_batch):
        assert 'toolCalls: data["tool_calls"].map(parseToolCallEntry),' in post_tool_batch

    def test_shape__list_dataclass__serializes_with_map(self, post_tool_batch):
        assert 'result["tool_calls"] = obj.toolCalls.map(serializeToolCallEntry);' in post_tool_batch

    # -- open object: Record<string, unknown> ----------------------------------------------

    def test_shape__open_object__maps_to_record(self, pre_tool_use):
        assert "  toolInput: Record<string, unknown>;" in pre_tool_use

    # -- run(): pattern-specific plumbing --------------------------------------------------

    def test_shape__permission_decision_pattern__serializes_json_output(self, pre_tool_use):
        assert "console.log(JSON.stringify(serializePreToolUseOutput(decision)));" in pre_tool_use

    def test_shape__none_pattern__handle_returns_void_no_output(self, session_end):
        assert "export function run(handle: (event: SessionEndInput) => void): void {" in session_end
        assert "  handle(event);" in session_end
        assert "console.log" not in session_end


class TestCheckerDispatch:
    """The runtime profile resolves its checker from ``toolchain.CHECKERS`` when built (``_generate``
    constructs the profile fresh per call), so a ``monkeypatch.setitem`` fake applied before
    ``_generate`` exercises the dispatch/gated-write wiring without a real esbuild."""

    def test_run__typescript_event__invokes_registered_checker_per_file(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", calls.append)

        out_dir = _generate("PreToolUse", tmp_path)

        harness_text = (out_dir / "_harness.ts").read_text()
        stub_text = (out_dir / "index.ts").read_text()
        assert calls == [harness_text, stub_text]

    def test_run__checker_rejects_source__propagates_and_writes_nothing(self, tmp_path, monkeypatch):
        def fake(source):
            raise subprocess.CalledProcessError(1, ["esbuild"])

        monkeypatch.setitem(toolchain.CHECKERS, "esbuild", fake)

        with pytest.raises(subprocess.CalledProcessError):
            _generate("PreToolUse", tmp_path)

        assert not (tmp_path / "pre_tool_use").exists()
