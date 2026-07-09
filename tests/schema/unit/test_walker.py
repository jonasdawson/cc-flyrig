"""Tests for the IR property walker (schema.walker)."""

import pytest

from cc_flyrig.schema import walker


class TestKnownProps:
    def test_walk_props__pre_tool_use_input__includes_common_and_event_keys(self, schema):
        props = walker.walk_event_props(schema, "PreToolUse")
        # CommonInput keys (via allOf + $ref) and event-specific keys are both present.
        assert {"session_id", "transcript_path", "cwd", "hook_event_name"} <= props
        assert {"tool_name", "tool_input", "tool_use_id"} <= props

    def test_walk_props__open_object_payload__nested_keys_not_expanded(self, schema):
        # tool_input is a known top-level key, but its open-object contents (e.g. "command") are not
        # treated as schema-known keys — that is what keeps OpenObject payloads unconstrained.
        props = walker.walk_event_props(schema, "PreToolUse")
        assert "tool_input" in props
        assert "command" not in props

    def test_walk_props__session_start_input__includes_source_and_model(self, schema):
        props = walker.walk_event_props(schema, "SessionStart")
        assert {"source", "model"} <= props
        assert "session_id" in props  # inherited from CommonInput

    def test_walk_props__post_tool_use_input__includes_tool_response_and_duration(self, schema):
        props = walker.walk_event_props(schema, "PostToolUse")
        assert {"tool_response", "duration_ms"} <= props

    def test_walk_props__unknown_def_name__raises(self, schema):
        with pytest.raises(KeyError):
            walker.walk_props(schema, "NoSuchInput")
