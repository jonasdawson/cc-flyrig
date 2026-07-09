"""Validation tests for the canonical IR schema (hooks.schema.json)."""

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

_SCHEMAS_ROOT = Path(__file__).parent.parent.parent.parent / "schemas"
SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / "schemas" / "cc-2.1.168" / "hooks.schema.json"


def _validate(schema: dict, def_name: str, instance: dict) -> None:
    sub_schema = {"$ref": f"#/$defs/{def_name}"}
    resolver_schema = dict(schema)
    resolver_schema.update(sub_schema)
    Draft202012Validator(resolver_schema).validate(instance)


def _expect_invalid(schema: dict, def_name: str, instance: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, def_name, instance)


class TestHooksSchema:
    def test_hooks_schema__loaded__is_valid_json(self):
        assert SCHEMA_PATH.exists()
        data = json.loads(SCHEMA_PATH.read_text())
        assert isinstance(data, dict)

    def test_hooks_schema__validated_against_draft_2020_12_meta_schema__passes(self, schema):
        meta_validator = Draft202012Validator(Draft202012Validator.META_SCHEMA)
        meta_validator.validate(schema)

    def test_hooks_schema__top_level_annotations__present(self, schema):
        assert schema["x-cc-version"] == "2.1.168"
        assert schema["x-schema-date"] == "2026-06-06"
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_hooks_schema__all_30_events_have_input_and_output_defs__present(self, schema):
        events = [
            "SessionStart",
            "Setup",
            "InstructionsLoaded",
            "UserPromptSubmit",
            "UserPromptExpansion",
            "MessageDisplay",
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "PostToolUseFailure",
            "PostToolBatch",
            "PermissionDenied",
            "Notification",
            "SubagentStart",
            "SubagentStop",
            "TaskCreated",
            "TaskCompleted",
            "Stop",
            "StopFailure",
            "TeammateIdle",
            "ConfigChange",
            "CwdChanged",
            "FileChanged",
            "WorktreeCreate",
            "WorktreeRemove",
            "PreCompact",
            "PostCompact",
            "SessionEnd",
            "Elicitation",
            "ElicitationResult",
        ]
        defs = schema["$defs"]
        for event in events:
            assert f"{event}Input" in defs, f"Missing {event}Input"
            assert f"{event}Output" in defs, f"Missing {event}Output"


class TestPreToolUseInput:
    def test_pre_tool_use_input__minimal_required_payload__validates(self, schema):
        _validate(
            schema,
            "PreToolUseInput",
            {
                "session_id": "abc123",
                "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
                "cwd": "/home/user/project",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm test"},
                "tool_use_id": "toolu_01ABC",
            },
        )

    def test_pre_tool_use_input__payload_missing_tool_name__fails_validation(self, schema):
        _expect_invalid(
            schema,
            "PreToolUseInput",
            {
                "session_id": "abc123",
                "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
                "cwd": "/home/user/project",
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": "npm test"},
                "tool_use_id": "toolu_01ABC",
            },
        )

    def test_pre_tool_use_input__payload_with_effort__validates(self, schema):
        _validate(
            schema,
            "PreToolUseInput",
            {
                "session_id": "abc123",
                "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
                "cwd": "/home/user/project",
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "/tmp/out.txt", "content": "hello"},
                "tool_use_id": "toolu_02DEF",
                "permission_mode": "default",
                "effort": {"level": "high"},
            },
        )


class TestPostToolUseInput:
    def test_post_tool_use_input__full_payload_with_duration_ms__validates(self, schema):
        _validate(
            schema,
            "PostToolUseInput",
            {
                "session_id": "abc123",
                "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
                "cwd": "/home/user/project",
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "/path/to/file.txt", "content": "file content"},
                "tool_response": {"filePath": "/path/to/file.txt", "success": True},
                "tool_use_id": "toolu_01ABC123",
                "duration_ms": 12,
            },
        )


class TestUserPromptSubmitInput:
    def test_user_prompt_submit_input__payload_with_prompt__validates(self, schema):
        _validate(
            schema,
            "UserPromptSubmitInput",
            {
                "session_id": "abc123",
                "transcript_path": "/home/user/.claude/projects/abc123.jsonl",
                "cwd": "/home/user",
                "hook_event_name": "UserPromptSubmit",
                "permission_mode": "default",
                "prompt": "Write a function to calculate the factorial of a number",
            },
        )


class TestStopInput:
    def test_stop_input__payload_with_background_tasks__validates(self, schema):
        _validate(
            schema,
            "StopInput",
            {
                "session_id": "abc123",
                "transcript_path": "~/.claude/projects/abc123.jsonl",
                "cwd": "/home/user",
                "hook_event_name": "Stop",
                "permission_mode": "default",
                "stop_hook_active": True,
                "last_assistant_message": "I've completed the refactoring.",
                "background_tasks": [
                    {
                        "id": "task-001",
                        "type": "shell",
                        "status": "running",
                        "description": "tail logs",
                        "command": "tail -f /var/log/syslog",
                    }
                ],
                "session_crons": [],
            },
        )

    def test_stop_input__missing_stop_hook_active__fails_validation(self, schema):
        _expect_invalid(
            schema,
            "StopInput",
            {
                "session_id": "abc123",
                "transcript_path": "~/.claude/projects/abc123.jsonl",
                "cwd": "/home/user",
                "hook_event_name": "Stop",
                "last_assistant_message": "Done.",
            },
        )


class TestSessionStartInput:
    def test_session_start_input__payload_with_model_and_source__validates(self, schema):
        _validate(
            schema,
            "SessionStartInput",
            {
                "session_id": "abc123",
                "transcript_path": "/Users/.../abc123.jsonl",
                "cwd": "/Users/...",
                "hook_event_name": "SessionStart",
                "source": "startup",
                "model": "claude-sonnet-4-6",
            },
        )

    def test_session_start_input__payload_with_session_title__validates(self, schema):
        _validate(
            schema,
            "SessionStartInput",
            {
                "session_id": "abc123",
                "transcript_path": "/Users/.../abc123.jsonl",
                "cwd": "/Users/...",
                "hook_event_name": "SessionStart",
                "source": "resume",
                "model": "claude-sonnet-4-6",
                "session_title": "auth-refactor",
            },
        )


class TestSessionEndInput:
    def test_session_end_input__payload_with_reason__validates(self, schema):
        _validate(
            schema,
            "SessionEndInput",
            {
                "session_id": "abc123",
                "transcript_path": "/Users/.../abc123.jsonl",
                "cwd": "/Users/...",
                "hook_event_name": "SessionEnd",
                "reason": "other",
            },
        )

    def test_session_end_input__invalid_reason_value__fails_validation(self, schema):
        _expect_invalid(
            schema,
            "SessionEndInput",
            {
                "session_id": "abc123",
                "transcript_path": "/Users/.../abc123.jsonl",
                "cwd": "/Users/...",
                "hook_event_name": "SessionEnd",
                "reason": "unknown_reason",
            },
        )


class TestCommonOutput:
    def test_common_output__continue_false_with_stop_reason__validates(self, schema):
        _validate(
            schema,
            "CommonOutput",
            {
                "continue": False,
                "stopReason": "Build failed, fix errors before continuing",
            },
        )

    def test_common_output__empty_object__validates(self, schema):
        _validate(schema, "CommonOutput", {})


class TestPreToolUseOutput:
    def test_pre_tool_use_output__permission_decision_deny__validates(self, schema):
        _validate(
            schema,
            "PreToolUseOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Database writes are not allowed",
                }
            },
        )

    def test_pre_tool_use_output__permission_decision_allow_with_updated_input__validates(self, schema):
        _validate(
            schema,
            "PreToolUseOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "Approved by policy",
                    "updatedInput": {"command": "npm run lint"},
                    "additionalContext": "Running in production environment.",
                }
            },
        )


class TestPermissionRequestOutput:
    def test_permission_request_output__decision_behavior_allow__validates(self, schema):
        _validate(
            schema,
            "PermissionRequestOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "allow",
                        "updatedInput": {"command": "npm run lint"},
                    },
                }
            },
        )

    def test_permission_request_output__decision_behavior_deny__validates(self, schema):
        _validate(
            schema,
            "PermissionRequestOutput",
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": "This operation is not permitted.",
                        "interrupt": True,
                    },
                }
            },
        )


class TestReconciledShapes:
    """Shapes corrected against real captured payloads (ADR 0007)."""

    def test_session_start_input__init_only_without_model__validates(self, schema):
        # The --init-only launch emits a SessionStart with no `model`; `model` is therefore optional.
        _validate(
            schema,
            "SessionStartInput",
            {
                "session_id": "abc123",
                "transcript_path": "/x.jsonl",
                "cwd": "/proj",
                "hook_event_name": "SessionStart",
                "source": "startup",
            },
        )

    def test_pre_compact_input__custom_instructions_null__validates(self, schema):
        # Manual /compact with no instructions sends null, not an empty string.
        _validate(
            schema,
            "PreCompactInput",
            {
                "session_id": "abc123",
                "transcript_path": "/x.jsonl",
                "cwd": "/proj",
                "hook_event_name": "PreCompact",
                "trigger": "manual",
                "custom_instructions": None,
            },
        )


class TestPythonLangRuntimeProfile:
    """Each schema version must ship a lang/python.json runtime profile covering all $defs.

    ``load_runtime_profile`` is family-agnostic — one shared ``lang/<runtime>.json`` per version
    serves every family whose schema lives in that dir (hooks and statusline both read it). So the
    profile's ``class_names`` must cover the *union* of every ``*.schema.json``'s ``$defs`` in the
    version dir, and carry no key outside that union.
    """

    @pytest.fixture(params=sorted(_SCHEMAS_ROOT.glob("cc-*/lang/python.json")))
    def version_defs_and_profile(self, request):
        runtime_profile_path = request.param
        version_dir = runtime_profile_path.parent.parent
        all_defs: set[str] = set()
        for schema_path in version_dir.glob("*.schema.json"):
            all_defs |= set(json.loads(schema_path.read_text())["$defs"].keys())
        return all_defs, runtime_profile_path

    @pytest.mark.parametrize(
        "version_dir",
        sorted({p.parent for p in _SCHEMAS_ROOT.glob("cc-*/*.schema.json")}),
        ids=lambda p: p.name,
    )
    def test_python_runtime_profile__exists_beside_every_schema_version__present(self, version_dir):
        assert (version_dir / "lang" / "python.json").exists(), f"Missing {version_dir}/lang/python.json"

    def test_python_runtime_profile__language_field__is_python(self, version_defs_and_profile):
        _, runtime_profile_path = version_defs_and_profile
        runtime_profile = json.loads(runtime_profile_path.read_text())
        assert runtime_profile.get("language") == "python"

    def test_python_runtime_profile__class_names__covers_all_schema_defs(self, version_defs_and_profile):
        all_defs, runtime_profile_path = version_defs_and_profile
        runtime_profile = json.loads(runtime_profile_path.read_text())
        runtime_profile_keys = set(runtime_profile.get("class_names", {}).keys())
        missing = all_defs - runtime_profile_keys
        extra = runtime_profile_keys - all_defs
        assert not missing, f"Runtime profile missing entries for: {sorted(missing)}"
        assert not extra, f"Runtime profile has entries not in any family schema: {sorted(extra)}"

    def test_python_runtime_profile__required_toolchain_keys__all_present(self, version_defs_and_profile):
        _, runtime_profile_path = version_defs_and_profile
        runtime_profile = json.loads(runtime_profile_path.read_text())
        for key in ("extension", "stub_name", "formatter", "checker"):
            assert key in runtime_profile, f"{runtime_profile_path} is missing required key {key!r}"
