"""Behavioral round-trip tests for the generated TypeScript harness, executed with ``tsx``.

The byte-for-byte generation tests (test_generate_typescript.py) prove the output is stable and
structurally shaped right, but not that ``parseX``/``serializeX`` map the wire contract correctly —
a camelCase ↔ snake_case mistake would still pass them. This module closes that gap the same way the
Python suite does: it runs every captured payload through the committed harness's
``parse<Event>Input`` → ``serialize<Event>Input`` and asserts the result equals the input (modulo
omitted ``null`` optionals, matching ``to_dict``/serialize semantics).

Execution uses the dev-dependency ``tsx`` (``node_modules/.bin/tsx``); the whole module skips cleanly
when it is not installed, so the suite stays green in a Python-only environment.
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent.parent
SCAFFOLDS_TS = ROOT / "scaffolds" / "typescript" / "cc-2.1.185"
CAPTURES_DIR = ROOT / "captures" / "cc-2.1.185"
TSX = ROOT / "node_modules" / ".bin" / "tsx"

SCAFFOLDS_TS_STATUSLINE = ROOT / "scaffolds" / "typescript" / "cc-2.1.198"
CAPTURES_DIR_STATUSLINE = ROOT / "captures" / "cc-2.1.198" / "statusline"
_STATUSLINE_INPUT_CLASS = {"StatusLine": "StatusLineData", "SubagentStatusLine": "SubagentStatusLineInput"}

pytestmark = pytest.mark.skipif(not TSX.exists(), reason="tsx not installed (run `npm install`)")

# tsx driver: dynamically import the committed harness by absolute path and round-trip a JSON array of
# payloads through parse<Event>Input -> serialize<Event>Input. An async IIFE avoids top-level await
# (tsx transpiles .ts to CJS by default, where top-level await is unsupported).
_DRIVER = """\
import { readFileSync } from "node:fs";
(async () => {
  const [harnessPath, event, payloadsPath] = process.argv.slice(2);
  const mod: any = await import(harnessPath);
  const payloads = JSON.parse(readFileSync(payloadsPath, "utf-8"));
  const out = payloads.map((p: any) => mod["serialize" + event + "Input"](mod["parse" + event + "Input"](p)));
  process.stdout.write(JSON.stringify(out));
})();
"""

# Statusline variant: takes the input class name directly (StatusLine's is StatusLineData, not
# StatusLineInput, per the runtime profile's dogfood-naming override — the hooks driver's "<Event>Input"
# convention does not hold here).
_STATUSLINE_DRIVER = """\
import { readFileSync } from "node:fs";
(async () => {
  const [harnessPath, className, payloadsPath] = process.argv.slice(2);
  const mod: any = await import(harnessPath);
  const payloads = JSON.parse(readFileSync(payloadsPath, "utf-8"));
  const out = payloads.map((p: any) => mod["serialize" + className](mod["parse" + className](p)));
  process.stdout.write(JSON.stringify(out));
})();
"""


def _capture_payloads(event: str) -> list[dict]:
    path = CAPTURES_DIR / f"{event}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# Events with at least one captured payload (WorktreeRemove has none — same gap as the Python suite).
_EVENTS_WITH_CAPTURES = sorted(
    p.stem for p in CAPTURES_DIR.glob("*.jsonl") if any(line.strip() for line in p.read_text().splitlines())
)


def _strip_nulls(payload: dict) -> dict:
    """Drop top-level ``null`` values — serialize omits ``undefined``/``null`` optionals (e.g.

    PreCompact's ``custom_instructions: null``). Non-recursive: opaque passthrough objects (e.g.
    ``tool_input``) are copied verbatim, so their nested nulls must survive, exactly as in the Python
    round-trip test.
    """
    return {k: v for k, v in payload.items() if v is not None}


def _strip_nulls_recursive(payload):
    """Recursive variant for statusline: its captures nest explicit nulls inside typed objects (e.g.

    ``context_window.current_usage``), unlike the hooks captures (Group 3 finding).
    """
    if isinstance(payload, dict):
        return {k: _strip_nulls_recursive(v) for k, v in payload.items() if v is not None}
    if isinstance(payload, list):
        return [_strip_nulls_recursive(v) for v in payload]
    return payload


def _statusline_capture_payloads(event: str) -> list[dict]:
    path = CAPTURES_DIR_STATUSLINE / f"{event}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture(scope="module")
def driver(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("ts_driver") / "driver.ts"
    path.write_text(_DRIVER)
    return path


@pytest.fixture(scope="module")
def statusline_driver(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("ts_statusline_driver") / "driver.ts"
    path.write_text(_STATUSLINE_DRIVER)
    return path


def _round_trip(driver: Path, event: str, payloads: list[dict], tmp_path: Path) -> list[dict]:
    payloads_file = tmp_path / "payloads.json"
    payloads_file.write_text(json.dumps(payloads))
    harness = SCAFFOLDS_TS / _snake(event) / "_harness.ts"
    result = subprocess.run(
        [str(TSX), str(driver), str(harness), event, str(payloads_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tsx failed for {event}:\n{result.stderr}"
    return json.loads(result.stdout)


def _snake(event: str) -> str:
    # Local copy to avoid importing the package just for naming (mirrors translate.snake_case).
    from cc_flyrig.codegen.translate import snake_case

    return snake_case(event)


def _round_trip_statusline(driver: Path, event: str, payloads: list[dict], tmp_path: Path) -> list[dict]:
    payloads_file = tmp_path / "payloads.json"
    payloads_file.write_text(json.dumps(payloads))
    harness = SCAFFOLDS_TS_STATUSLINE / _snake(event) / "_harness.ts"
    class_name = _STATUSLINE_INPUT_CLASS[event]
    result = subprocess.run(
        [str(TSX), str(driver), str(harness), class_name, str(payloads_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tsx failed for {event}:\n{result.stderr}"
    return json.loads(result.stdout)


class TestRoundTripTypeScript:
    @pytest.mark.parametrize("event", _EVENTS_WITH_CAPTURES)
    def test_parse_serialize__captured_payloads__round_trip(self, event, driver, tmp_path):
        payloads = _capture_payloads(event)
        restored = _round_trip(driver, event, payloads, tmp_path)
        assert restored == [_strip_nulls(p) for p in payloads]


class TestRoundTripStatuslineTypeScript:
    @pytest.mark.parametrize("event", ["StatusLine", "SubagentStatusLine"])
    def test_parse_serialize__captured_payloads__round_trip(self, event, statusline_driver, tmp_path):
        payloads = _statusline_capture_payloads(event)
        assert payloads, f"no captured payloads for {event}"
        restored = _round_trip_statusline(statusline_driver, event, payloads, tmp_path)
        assert restored == [_strip_nulls_recursive(p) for p in payloads]


class TestStubExecution:
    """Executes the committed index.ts end-to-end (tsx subprocess, stdin fed) — proves the stub's
    parse -> dispatch wiring. Never import index.ts: it calls run(handle) at top level, which reads
    stdin and throws."""

    @pytest.mark.parametrize("event", ["PreToolUse", "SessionEnd"])  # decision + none pattern
    def test_index__unimplemented_handle__exits_nonzero_with_not_implemented(self, event):
        payload = _capture_payloads(event)[0]
        index = SCAFFOLDS_TS / _snake(event) / "index.ts"
        result = subprocess.run(
            [str(TSX), str(index)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Not implemented" in result.stderr

    @pytest.mark.parametrize("event", ["StatusLine", "SubagentStatusLine"])  # text-return + jsonlines-rows
    def test_index__statusline_unimplemented_handle__exits_nonzero_with_not_implemented(self, event):
        payload = _statusline_capture_payloads(event)[0]
        index = SCAFFOLDS_TS_STATUSLINE / _snake(event) / "index.ts"
        result = subprocess.run(
            [str(TSX), str(index)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Not implemented" in result.stderr
