"""Validation tests for the statusline IR schema (statusline.schema.json, Group 2 U3)."""

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / "schemas" / "cc-2.1.198" / "statusline.schema.json"

_REAL_STATUS_LINE_PAYLOAD = {
    "cwd": "/tmp/flyrig_statusline_sandbox_nn_exyrt",
    "session_id": "<SESSION_ID>",
    "transcript_path": "<TRANSCRIPT_PATH>",
    "version": "2.1.198",
    "exceeds_200k_tokens": False,
    "fast_mode": False,
    "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
    "workspace": {"current_dir": "/tmp/x", "project_dir": "/tmp/x", "added_dirs": []},
    "output_style": {"name": "default"},
    "cost": {
        "total_cost_usd": 0.0545041,
        "total_duration_ms": 3967,
        "total_api_duration_ms": 2698,
        "total_lines_added": 0,
        "total_lines_removed": 0,
    },
    "context_window": {
        "total_input_tokens": 35448,
        "total_output_tokens": 3,
        "context_window_size": 1000000,
        "used_percentage": 4,
        "remaining_percentage": 96,
        "current_usage": {
            "input_tokens": 3354,
            "output_tokens": 3,
            "cache_creation_input_tokens": 5997,
            "cache_read_input_tokens": 26097,
        },
    },
    "thinking": {"enabled": True},
    "prompt_id": "ed976ccb-1c97-43cd-8a6e-72373a86cafd",
    "effort": {"level": "high"},
    "session_name": "Simple arithmetic calculation",
    "rate_limits": {
        "five_hour": {"used_percentage": 15, "resets_at": 1783021800},
        "seven_day": {"used_percentage": 4, "resets_at": 1783296000},
    },
}

_REAL_SUBAGENT_STATUS_LINE_PAYLOAD = {
    "session_id": "<SESSION_ID>",
    "transcript_path": "<TRANSCRIPT_PATH>",
    "cwd": "/tmp/flyrig_statusline_sandbox_nn_exyrt",
    "prompt_id": "f43fef22-82a1-431d-8778-b85f35c3dd39",
    "columns": 76,
    "tasks": [
        {
            "id": "a1a9b697ac6040bd4",
            "type": "local_agent",
            "status": "running",
            "description": "Find fixture.txt file",
            "label": "Find fixture.txt file",
            "startTime": 1783008905848,
            "tokenCount": 0,
            "tokenSamples": [0],
            "cwd": "/tmp/flyrig_statusline_sandbox_nn_exyrt",
        }
    ],
}


def _validate(schema: dict, def_name: str, instance: dict) -> None:
    sub_schema = {"$ref": f"#/$defs/{def_name}"}
    resolver_schema = dict(schema)
    resolver_schema.update(sub_schema)
    Draft202012Validator(resolver_schema).validate(instance)


def _expect_invalid(schema: dict, def_name: str, instance: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, def_name, instance)


class TestStatuslineSchema:
    def test_statusline_schema__loaded__is_valid_json(self):
        assert SCHEMA_PATH.exists()
        data = json.loads(SCHEMA_PATH.read_text())
        assert isinstance(data, dict)

    def test_statusline_schema__validated_against_draft_2020_12_meta_schema__passes(self, statusline_schema):
        meta_validator = Draft202012Validator(Draft202012Validator.META_SCHEMA)
        meta_validator.validate(statusline_schema)

    def test_statusline_schema__top_level_annotations__present(self, statusline_schema):
        assert statusline_schema["x-cc-version"] == "2.1.198"
        assert statusline_schema["x-schema-date"] == "2026-07-02"
        assert statusline_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_statusline_schema__no_hook_common_input_fields__not_a_hook_event(self, statusline_schema):
        # Invariant: statusline is its own namespace, never a 31st hook event (ADR 0010).
        assert "CommonInput" not in statusline_schema["$defs"]
        assert "hook_event_name" not in statusline_schema["$defs"]["StatusLineInput"]["properties"]

    def test_statusline_schema__expected_defs__all_present(self, statusline_schema):
        for def_name in ("StatusLineInput", "SubagentStatusLineInput", "SubagentStatusLineOutput", "TaskInfo"):
            assert def_name in statusline_schema["$defs"], f"Missing {def_name}"


class TestStatusLineInput:
    def test_status_line_input__real_captured_payload__validates(self, statusline_schema):
        _validate(statusline_schema, "StatusLineInput", _REAL_STATUS_LINE_PAYLOAD)

    def test_status_line_input__minimal_required_fields_only__validates(self, statusline_schema):
        required = statusline_schema["$defs"]["StatusLineInput"]["required"]
        minimal = {k: v for k, v in _REAL_STATUS_LINE_PAYLOAD.items() if k in required}
        _validate(statusline_schema, "StatusLineInput", minimal)

    def test_status_line_input__missing_fast_mode__fails_validation(self, statusline_schema):
        bad = {k: v for k, v in _REAL_STATUS_LINE_PAYLOAD.items() if k != "fast_mode"}
        _expect_invalid(statusline_schema, "StatusLineInput", bad)

    def test_status_line_input__context_window_current_usage_null__validates(self, statusline_schema):
        # Observed on the wire before the first API response — the U1 spike's first StatusLine sample.
        payload = {
            **_REAL_STATUS_LINE_PAYLOAD,
            "context_window": {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "context_window_size": 1000000,
                "used_percentage": None,
                "remaining_percentage": None,
                "current_usage": None,
            },
        }
        del payload["prompt_id"]
        del payload["effort"]
        del payload["session_name"]
        del payload["rate_limits"]
        _validate(statusline_schema, "StatusLineInput", payload)

    def test_status_line_input__extra_hook_event_name_key__still_validates(self, statusline_schema):
        # statusLine has no hook_event_name property at all; presence of an unrelated extra key is
        # permitted by the IR (no additionalProperties: false), matching hooks.schema.json's convention.
        payload = {**_REAL_STATUS_LINE_PAYLOAD, "hook_event_name": "StatusLine"}
        _validate(statusline_schema, "StatusLineInput", payload)


class TestSubagentStatusLineInput:
    def test_subagent_status_line_input__real_captured_payload__validates(self, statusline_schema):
        _validate(statusline_schema, "SubagentStatusLineInput", _REAL_SUBAGENT_STATUS_LINE_PAYLOAD)

    def test_subagent_status_line_input__missing_columns__fails_validation(self, statusline_schema):
        bad = {k: v for k, v in _REAL_SUBAGENT_STATUS_LINE_PAYLOAD.items() if k != "columns"}
        _expect_invalid(statusline_schema, "SubagentStatusLineInput", bad)

    def test_subagent_status_line_input__task_info_name_field_optional__validates_without_it(self, statusline_schema):
        # `name` is documented by the reference but was never observed by the U1 spike.
        _validate(statusline_schema, "SubagentStatusLineInput", _REAL_SUBAGENT_STATUS_LINE_PAYLOAD)

    def test_subagent_status_line_input__task_info_with_name__validates(self, statusline_schema):
        payload = {
            **_REAL_SUBAGENT_STATUS_LINE_PAYLOAD,
            "tasks": [{**_REAL_SUBAGENT_STATUS_LINE_PAYLOAD["tasks"][0], "name": "explore"}],
        }
        _validate(statusline_schema, "SubagentStatusLineInput", payload)


class TestSubagentStatusLineOutput:
    def test_subagent_status_line_output__id_and_content__validates(self, statusline_schema):
        _validate(statusline_schema, "SubagentStatusLineOutput", {"id": "task-1", "content": "  building..."})

    def test_subagent_status_line_output__missing_content__fails_validation(self, statusline_schema):
        _expect_invalid(statusline_schema, "SubagentStatusLineOutput", {"id": "task-1"})
