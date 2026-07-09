"""Tests for the statusline event family (ADR 0010) on the TypeScript runtime — Group 4.

Mirrors ``test_generate_typescript.py``'s committed-scaffold-as-reference pattern (hooks TS), scoped
to the two statusline-family events, the same way ``test_generate_statusline.py`` scopes the Python
pattern. Also covers the ``--runtime typescript --event StatusLine`` CLI combination (the family is
derived from the event) and the two hard regression bars: plain hooks TS generation is unaffected,
and the Copier ``VERSION`` file does not advance on a statusline-only cut.
"""

import shutil
from pathlib import Path

import pytest

from cc_flyrig.codegen import __main__ as cli
from cc_flyrig.codegen import toolchain
from cc_flyrig.codegen.generate import Generator
from cc_flyrig.codegen.load import IntermediateRepresentationLoader
from cc_flyrig.codegen.render import EntrypointRenderer
from cc_flyrig.codegen.settings import Settings
from cc_flyrig.codegen.translate import snake_case

ROOT = Path(__file__).parent.parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas"
_LOCAL_ESBUILD = ROOT / "node_modules" / ".bin" / "esbuild"
CC_VERSION = "2.1.198"
SCAFFOLDS_TS = ROOT / "scaffolds" / "typescript" / f"cc-{CC_VERSION}"
HOOKS_CC_VERSION = "2.1.185"  # pin for the hooks-TS regression check (unrelated to statusline)

STATUSLINE_EVENTS = ["StatusLine", "SubagentStatusLine"]
_PACKAGE_FILES = ("_harness.ts", "index.ts")


def _generate(event: str, out_dir: Path, cc_version: str = CC_VERSION) -> Path:
    settings = Settings(
        event=event,
        cc_version=cc_version,
        family="statusline",
        schemas_dir=SCHEMAS_DIR,
        out_dir=out_dir,
    )
    profile = toolchain.load_runtime_profile(SCHEMAS_DIR / f"cc-{cc_version}", "typescript")
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
class TestGenerateStatuslineTypeScript:
    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__writes_ts_package(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        assert out_dir == tmp_path / snake_case(event)
        for fname in _PACKAGE_FILES:
            assert (out_dir / fname).exists()

    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__matches_committed_scaffold(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        scaffold = _scaffold(event)
        for fname in _PACKAGE_FILES:
            assert (out_dir / fname).read_text() == (scaffold / fname).read_text()

    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__stamps_cc_version_and_event(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        text = (out_dir / "_harness.ts").read_text()
        assert f"cc-{CC_VERSION}" in text
        assert f"Event: {event}" in text


class TestTypeScriptStatuslineShape:
    """Pin the load-bearing macro outputs the two statusline decision patterns need."""

    @pytest.fixture(scope="class")
    @classmethod
    def status_line(cls):
        return (_scaffold("StatusLine") / "_harness.ts").read_text()

    @pytest.fixture(scope="class")
    @classmethod
    def status_line_stub(cls):
        return (_scaffold("StatusLine") / "index.ts").read_text()

    @pytest.fixture(scope="class")
    @classmethod
    def subagent_status_line(cls):
        return (_scaffold("SubagentStatusLine") / "_harness.ts").read_text()

    @pytest.fixture(scope="class")
    @classmethod
    def subagent_status_line_stub(cls):
        return (_scaffold("SubagentStatusLine") / "index.ts").read_text()

    # -- surface-aware header comment -------------------------------------------------------

    def test_shape__statusline_header__names_statusline_ir_not_hooks_ir(self, status_line):
        assert "Claude Code statusline IR" in status_line
        assert "Claude Code hooks IR" not in status_line

    # -- text-return: no output model, bare console.log --------------------------------------

    def test_shape__text_return__run_signature_has_no_null_union(self, status_line):
        assert "export function run(handle: (event: StatusLineData) => string): void {" in status_line

    def test_shape__text_return__prints_handle_result_directly(self, status_line):
        assert "console.log(handle(event));" in status_line

    def test_shape__text_return__has_no_output_interface(self, status_line):
        assert "StatusLineOutput" not in status_line

    # -- jsonlines-rows: authored output row, one JSON object per line -----------------------

    def test_shape__jsonlines_rows__run_signature_returns_output_array(self, subagent_status_line):
        assert (
            "export function run(handle: (event: SubagentStatusLineInput) => SubagentStatusLineOutput[]): void {"
            in subagent_status_line
        )

    def test_shape__jsonlines_rows__iterates_and_serializes_each_row(self, subagent_status_line):
        assert "for (const row of handle(event)) {" in subagent_status_line
        assert "console.log(JSON.stringify(serializeSubagentStatusLineOutput(row)));" in subagent_status_line

    # -- enum with a space in its wire value: string-literal passthrough, no mangling --------

    def test_shape__vim_mode__renders_space_containing_literal_unbroken(self, status_line):
        assert 'export type VimMode = "NORMAL" | "INSERT" | "VISUAL" | "VISUAL LINE";' in status_line

    # -- settings-wiring comment: singular command, not a hook array -------------------------

    def test_shape__statusline_stub__wiring_comment_uses_singular_command_shape(self, status_line_stub):
        assert '{ "statusLine": { "type": "command", "command": "npx tsx <path>/index.ts" } }' in status_line_stub
        assert "hook array" in status_line_stub  # the comment names what it is NOT, per Python's fix

    def test_shape__subagent_statusline_stub__wiring_comment_uses_singular_command_shape(
        self, subagent_status_line_stub
    ):
        assert (
            '{ "subagentStatusLine": { "type": "command", "command": "npx tsx <path>/index.ts" } }'
            in subagent_status_line_stub
        )

    def test_shape__text_return_stub__handle_returns_string(self, status_line_stub):
        assert "function handle(event: StatusLineData): string {" in status_line_stub

    def test_shape__jsonlines_rows_stub__handle_returns_output_array(self, subagent_status_line_stub):
        assert (
            "function handle(event: SubagentStatusLineInput): SubagentStatusLineOutput[] {" in subagent_status_line_stub
        )


class TestCliEventDerivedFamilyRuntimeCombination:
    def test_main__runtime_typescript_event_status_line__generates_status_line_event(self, tmp_path):
        argv = [
            "generate",
            "--runtime",
            "typescript",
            "--event",
            "StatusLine",
            "--cc-version",
            CC_VERSION,
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        # --out-dir is the scaffolds-root replacement: typescript/cc-<version>/ nests inside it.
        base = tmp_path / "typescript" / f"cc-{CC_VERSION}"
        assert (base / "status_line" / "_harness.ts").exists()
        assert (base / "status_line" / "index.ts").exists()

    def test_main__runtime_typescript_event_status_line__does_not_bump_copier_version(self, tmp_path):
        # scaffolds/typescript/VERSION lives one level above <runtime>/cc-<version> -- i.e. at
        # <out-dir root>/typescript/VERSION; a statusline-only cut must not advance it past the
        # hooks-pinned version (mirrors the Python CLI test).
        version_file = tmp_path / "typescript" / "VERSION"
        version_file.parent.mkdir(parents=True)
        version_file.write_text(f"{HOOKS_CC_VERSION}\n")
        argv = [
            "generate",
            "--runtime",
            "typescript",
            "--event",
            "StatusLine",
            "--cc-version",
            CC_VERSION,
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        assert version_file.read_text().strip() == HOOKS_CC_VERSION


class TestHooksTypeScriptRegressionUnaffected:
    """The hard regression bar (handoff invariant): adding statusline to TS must not change hooks TS."""

    def test_main__runtime_typescript_hooks_event__byte_identical_to_hooks_scaffold(self, tmp_path):
        argv = [
            "generate",
            "--runtime",
            "typescript",
            "--event",
            "PreToolUse",
            "--cc-version",
            HOOKS_CC_VERSION,
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        scaffold = ROOT / "scaffolds" / "typescript" / f"cc-{HOOKS_CC_VERSION}" / "pre_tool_use"
        base = tmp_path / "typescript" / f"cc-{HOOKS_CC_VERSION}"
        for fname in _PACKAGE_FILES:
            assert (base / "pre_tool_use" / fname).read_text() == (scaffold / fname).read_text()
