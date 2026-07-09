"""Tests for capture utility modules (capture.util.payload_scrubber, schema.keys)."""

from cc_flyrig.capture.util.payload_scrubber import scrub
from cc_flyrig.schema.keys import input_def_name


class TestPayloadScrubber:
    def test_scrub__home_path_in_string__replaced_with_placeholder(self):
        out = scrub({"cwd": "/home/alice/project"}, home="/home/alice")
        assert out == {"cwd": "<HOME>/project"}

    def test_scrub__sensitive_keys__redacted(self):
        out = scrub(
            {"session_id": "abc", "transcript_path": "/home/alice/.claude/t.jsonl", "keep": "v"},
            home="/home/alice",
        )
        assert out["session_id"] == "<SESSION_ID>"
        assert out["transcript_path"] == "<TRANSCRIPT_PATH>"
        assert out["keep"] == "v"

    def test_scrub__nested_structures__scrubbed_recursively(self):
        out = scrub({"a": [{"session_id": "x"}], "b": {"cwd": "/home/alice/p"}}, home="/home/alice")
        assert out["a"][0]["session_id"] == "<SESSION_ID>"
        assert out["b"]["cwd"] == "<HOME>/p"


class TestSchemaKeys:
    def test_input_def_name__event__appends_input_suffix(self):
        assert input_def_name("Stop") == "StopInput"
