"""Tests for the statusline event family (ADR 0010): CLI event-derived family selection, both
codegen paths, and the additive regression check that plain hook generation is unaffected.

Mirrors ``test_generate.py``'s golden-file + round-trip pattern, scoped to the two statusline-family
events (``StatusLine``, ``SubagentStatusLine``) instead of the 30 hook events.
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
from cc_flyrig.codegen.render import EntrypointRenderer
from cc_flyrig.codegen.settings import Settings
from cc_flyrig.codegen.translate import snake_case

ROOT = Path(__file__).parent.parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas"
GOLDEN_DIR = Path(__file__).parent.parent / "golden"
CAPTURES_DIR = ROOT / "captures" / "cc-2.1.198" / "statusline"
CC_VERSION = "2.1.198"

STATUSLINE_EVENTS = ["StatusLine", "SubagentStatusLine"]


def _strip_nulls(payload):
    """Recursively drop explicit JSON nulls, matching what to_dict() omits for optional fields.

    Unlike the hooks round-trip helper (test_generate.py's _strip_nulls, top-level only), the
    statusline captures carry explicit nulls *nested* inside typed objects (e.g.
    ``context_window.current_usage: null``), so this strips at every level.
    """
    if isinstance(payload, dict):
        return {k: _strip_nulls(v) for k, v in payload.items() if v is not None}
    if isinstance(payload, list):
        return [_strip_nulls(v) for v in payload]
    return payload


def _capture_payloads(event: str) -> list[dict]:
    path = CAPTURES_DIR / f"{event}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _generate(event: str, out_dir: Path) -> Path:
    settings = Settings(
        event=event, cc_version=CC_VERSION, family="statusline", schemas_dir=SCHEMAS_DIR, out_dir=out_dir
    )
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
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _golden(event: str) -> Path:
    return GOLDEN_DIR / snake_case(event)


class TestGenerateStatusline:
    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__output_ast_parses(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        ast.parse((out_dir / "_harness.py").read_text())
        ast.parse((out_dir / "__main__.py").read_text())

    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__matches_golden_fixture(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        golden = _golden(event)
        for fname in ("_harness.py", "__main__.py"):
            assert (out_dir / fname).read_text() == (golden / fname).read_text()

    @pytest.mark.parametrize("event", STATUSLINE_EVENTS)
    def test_run__event__stamps_cc_version_and_event_name(self, event, tmp_path):
        out_dir = _generate(event, tmp_path)
        text = (out_dir / "_harness.py").read_text()
        assert f"cc-{CC_VERSION}" in text
        assert f"Event: {event}" in text

    def test_run__status_line__writes_into_status_line_dir(self, tmp_path):
        out_dir = _generate("StatusLine", tmp_path)
        assert out_dir == tmp_path / "status_line"

    def test_run__subagent_status_line__writes_into_subagent_status_line_dir(self, tmp_path):
        out_dir = _generate("SubagentStatusLine", tmp_path)
        assert out_dir == tmp_path / "subagent_status_line"


class TestStatusLineNoOutputModel:
    """D3: statusLine is inputs-only — no output model, no decision, just text out."""

    @pytest.fixture(scope="class")
    @classmethod
    def harness(cls):
        return _load_module(_golden("StatusLine") / "_harness.py", "status_line_harness_pat")

    def test_harness__input_class_named_status_line_data(self, harness):
        # The golden statusline_types.py names the model StatusLineData; the runtime profile overrides the
        # default StatusLineInput class name to match (feature doc's dogfood target).
        assert harness.StatusLineData is not None

    def test_harness__has_no_output_class(self, harness):
        assert not hasattr(harness, "StatusLineOutput")

    def test_run__handle_returns_text__prints_bare_line(self, harness, monkeypatch, capsys):
        payload = _capture_payloads("StatusLine")[0]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: "my status text") == 0
        assert capsys.readouterr().out == "my status text\n"

    def test_run__handle_receives_typed_event(self, harness, monkeypatch):
        payload = _capture_payloads("StatusLine")[0]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        received = []
        harness.run(lambda event: received.append(event) or "x")
        assert isinstance(received[0], harness.StatusLineData)
        assert received[0].cwd == payload["cwd"]


class TestSubagentStatusLineJsonLinesRows:
    """subagentStatusLine emits a typed output-row model, one JSON object per line (D5)."""

    @pytest.fixture(scope="class")
    @classmethod
    def harness(cls):
        return _load_module(_golden("SubagentStatusLine") / "_harness.py", "subagent_status_line_harness_pat")

    def test_run__handle_returns_rows__prints_one_json_object_per_line(self, harness, monkeypatch, capsys):
        payload = _capture_payloads("SubagentStatusLine")[0]
        rows = [
            harness.SubagentStatusLineOutput(id="t1", content="running..."),
            harness.SubagentStatusLineOutput(id="t2", content="done"),
        ]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: rows) == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": "t1", "content": "running..."}
        assert json.loads(lines[1]) == {"id": "t2", "content": "done"}

    def test_run__handle_returns_empty_list__prints_nothing(self, harness, monkeypatch, capsys):
        payload = _capture_payloads("SubagentStatusLine")[0]
        monkeypatch.setattr(harness.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert harness.run(lambda event: []) == 0
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Round-trip every captured statusline payload through the committed golden module
# ---------------------------------------------------------------------------

_ROUND_TRIP_PARAMS: list[tuple[str, int]] = []
for _ev in STATUSLINE_EVENTS:
    for _i in range(len(_capture_payloads(_ev))):
        _ROUND_TRIP_PARAMS.append((_ev, _i))

_INPUT_CLASS_NAME = {"StatusLine": "StatusLineData", "SubagentStatusLine": "SubagentStatusLineInput"}


class TestRoundTripStatuslineEvents:
    @pytest.mark.parametrize(
        "event,payload_index",
        _ROUND_TRIP_PARAMS,
        ids=[f"{ev}[{i}]" for ev, i in _ROUND_TRIP_PARAMS],
    )
    def test_from_dict__captured_payload__round_trips(self, event, payload_index):
        module = _load_module(_golden(event) / "_harness.py", f"{snake_case(event)}_harness_rt_{payload_index}")
        payload = _capture_payloads(event)[payload_index]
        input_class = getattr(module, _INPUT_CLASS_NAME[event])
        restored = input_class.from_dict(payload).to_dict()
        assert restored == _strip_nulls(payload)


# ---------------------------------------------------------------------------
# CLI: family derived from --event (no --surface flag anymore), additive regression check
# ---------------------------------------------------------------------------


class TestCliEventDerivedFamily:
    def test_main__event_status_line__generates_status_line_event(self, tmp_path):
        argv = [
            "generate",
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
        # --out-dir is the scaffolds-root replacement: python/cc-<version>/ nests inside it.
        base = tmp_path / "python" / f"cc-{CC_VERSION}"
        assert (base / "status_line" / "_harness.py").exists()
        assert (base / "status_line" / "__main__.py").exists()

    def test_main__no_event_full_version__generates_hooks_and_statusline(self, tmp_path):
        # cc-2.1.198 is a full version: it ships both hooks.schema.json and statusline.schema.json,
        # so an explicit --cc-version pinned there generates every family -- the hooks events and
        # both statusline events -- into the same python/cc-<version>/ subtree.
        argv = [
            "generate",
            "--cc-version",
            CC_VERSION,
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        base = tmp_path / "python" / f"cc-{CC_VERSION}"
        assert (base / "status_line" / "_harness.py").exists()
        assert (base / "subagent_status_line" / "_harness.py").exists()
        assert (base / "pre_tool_use" / "_harness.py").exists()

    def test_main__event_status_line__does_not_bump_copier_version(self, tmp_path):
        # scaffolds/<runtime>/VERSION sits one level above <runtime>/cc-<version> -- i.e. at
        # <out-dir root>/python/VERSION. Generating a statusline event must not advance the hooks
        # copier version line (only the hooks family bumps it).
        version_file = tmp_path / "python" / "VERSION"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("2.1.185\n")
        argv = [
            "generate",
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
        assert version_file.read_text().strip() == "2.1.185"

    def test_main__event_status_line_no_schema_for_version__errors(self, tmp_path, capsys):
        argv = [
            "generate",
            "--event",
            "StatusLine",
            "--cc-version",
            "2.1.177",  # has hooks.schema.json but no statusline.schema.json -- no family defines StatusLine here
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 2
        assert "unknown event" in capsys.readouterr().err

    def test_main__event_status_line_no_schema_for_version__error_mentions_all_families(self, tmp_path, capsys):
        # The event search spans every registered family (ADR 0010), not just one -- the error
        # message must reflect that, not read as if only "hooks" (or only "statusline") was tried.
        argv = [
            "generate",
            "--event",
            "StatusLine",
            "--cc-version",
            "2.1.177",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 2
        assert "unknown event 'StatusLine': not found in any registered family" in capsys.readouterr().err

    def test_main__cc_version_lacking_statusline_schema__skips_statusline_but_generates_hooks(self, tmp_path, capsys):
        # cc-2.1.185 ships hooks.schema.json but no statusline.schema.json; a pinned --cc-version
        # there must skip the statusline family with a stderr note while hooks still generates.
        argv = [
            "generate",
            "--cc-version",
            "2.1.185",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        assert cli.main(argv) == 0
        base = tmp_path / "python" / "cc-2.1.185"
        assert (base / "pre_tool_use" / "_harness.py").exists()
        assert not (base / "status_line").exists()
        assert not (base / "subagent_status_line").exists()
        assert "skipping statusline: no schema for cc-2.1.185" in capsys.readouterr().err


class TestCliHooksRegressionUnaffectedByStatuslineFamily:
    """The one hard regression bar: plain hook generation must be unchanged by the statusline family."""

    def test_main__hooks_event__still_generates_pre_tool_use(self, tmp_path):
        argv = ["generate", "--event", "PreToolUse", "--schemas-dir", str(SCHEMAS_DIR), "--out-dir", str(tmp_path)]
        assert cli.main(argv) == 0
        base = tmp_path / "python" / f"cc-{cli._latest_cc_version(SCHEMAS_DIR, 'hooks')}"
        assert (base / "pre_tool_use" / "_harness.py").exists()

    def test_main__hooks_event__byte_identical_to_hooks_golden(self, tmp_path):
        argv = [
            "generate",
            "--event",
            "PreToolUse",
            "--cc-version",
            "2.1.177",
            "--schemas-dir",
            str(SCHEMAS_DIR),
            "--out-dir",
            str(tmp_path),
        ]
        cli.main(argv)
        golden = GOLDEN_DIR / "pre_tool_use"
        base = tmp_path / "python" / "cc-2.1.177"
        for fname in ("_harness.py", "__main__.py"):
            assert (base / "pre_tool_use" / fname).read_text() == (golden / fname).read_text()
