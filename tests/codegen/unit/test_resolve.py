"""Tests for the IR walker core: load.IntermediateRepresentationLoader, translate.TypeNodeBuilder, resolve.Resolver."""

from pathlib import Path

import pytest

from cc_flyrig.codegen.load import IntermediateRepresentationLoader
from cc_flyrig.codegen.resolve import EnumSpec, RecordSpec, Resolver
from cc_flyrig.codegen.settings import Settings
from cc_flyrig.codegen.toolchain import load_runtime_profile
from cc_flyrig.codegen.translate import TypeNodeBuilder, snake_case
from cc_flyrig.codegen.type_ast import ArrayNode, OpenObjectNode, RefNode, ScalarNode, UnionNode

SCHEMAS_DIR = Path(__file__).parent.parent.parent.parent / "schemas"
CC_VERSION = "2.1.177"


@pytest.fixture(scope="module")
def ir():
    settings = Settings(event="PreToolUse", cc_version=CC_VERSION, schemas_dir=SCHEMAS_DIR)
    return IntermediateRepresentationLoader(settings).load()


@pytest.fixture(scope="module")
def profile():
    return load_runtime_profile(SCHEMAS_DIR / f"cc-{CC_VERSION}", "python")


@pytest.fixture(scope="module")
def resolver(ir, profile):
    return Resolver(ir, TypeNodeBuilder(ir, profile), profile)


class TestDefKind:
    def test_def_kind__string_enum_def__returns_enum(self, ir):
        assert ir.def_kind("PermissionMode") == "enum"

    def test_def_kind__ref_only_def__returns_alias(self, ir):
        assert ir.def_kind("PermissionSuggestion") == "alias"

    def test_def_kind__object_def__returns_record(self, ir):
        assert ir.def_kind("PreToolUseInput") == "record"


class TestLoad:
    def test_load__committed_schema__stamps_cc_version(self, ir):
        assert ir.cc_version == CC_VERSION

    def test_class_name__no_runtime_profile_override__defaults_to_def_key(self, profile):
        assert profile.class_name("PreToolUseInput") == "PreToolUseInput"


class TestBuildType:
    def test_build__open_object_ref__maps_to_open_object_node(self, ir, profile):
        built = TypeNodeBuilder(ir, profile).build({"$ref": "#/$defs/OpenObject"})
        assert built.node == OpenObjectNode()
        assert built.deps == frozenset()

    def test_build__oneof_string_or_array__maps_to_union_node(self, ir, profile):
        node = {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "object"}}]}
        built = TypeNodeBuilder(ir, profile).build(node)
        assert built.node == UnionNode((ScalarNode("string"), ArrayNode(OpenObjectNode())))

    def test_build__oneof_ref_or_null__collapses_to_bare_ref_not_union(self, ir, profile):
        node = {"oneOf": [{"$ref": "#/$defs/PermissionMode"}, {"type": "null"}]}
        built = TypeNodeBuilder(ir, profile).build(node)
        assert built.node == RefNode("PermissionMode")
        assert built.deps == frozenset({"PermissionMode"})

    def test_build__oneof_scalar_or_null__collapses_to_bare_scalar(self, ir, profile):
        node = {"oneOf": [{"type": "string"}, {"type": "null"}]}
        built = TypeNodeBuilder(ir, profile).build(node)
        assert built.node == ScalarNode("string")

    def test_build__oneof_two_non_null_branches__unaffected_by_null_filtering(self, ir, profile):
        # Regression guard: existing multi-branch oneOf (no null) must keep building a real union.
        node = {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "object"}}]}
        built = TypeNodeBuilder(ir, profile).build(node)
        assert isinstance(built.node, UnionNode)
        assert len(built.node.members) == 2

    def test_build__enum_ref__yields_ref_node_and_dep(self, ir, profile):
        built = TypeNodeBuilder(ir, profile).build({"$ref": "#/$defs/PermissionMode"})
        assert built.node == RefNode("PermissionMode")
        assert built.deps == frozenset({"PermissionMode"})

    def test_snake_case__camelcase__splits_on_word_boundary(self):
        assert snake_case("permissionDecisionReason") == "permission_decision_reason"

    def test_snake_case__acronym_run__splits_correctly(self):
        assert snake_case("updatedMCPToolOutput") == "updated_mcp_tool_output"

    def test_snake_case__already_snake__unchanged(self):
        assert snake_case("agent_id") == "agent_id"


class TestFlatten:
    def test_flatten__pre_tool_use_input__merges_common_fields(self, resolver):
        required, props = resolver.flatten("PreToolUseInput")
        # Common fields (via allOf $ref) and event specifics both present.
        assert {"session_id", "cwd", "hook_event_name"} <= props.keys()
        assert {"tool_name", "tool_input", "tool_use_id"} <= props.keys()
        assert {"tool_name", "tool_use_id"} <= required


class TestResolve:
    def test_resolve__pre_tool_use__orders_dependencies_before_dependents(self, resolver):
        specs = resolver.resolve(["PreToolUseInput"])
        names = [s.class_name for s in specs]
        # EffortLevel (enum) before EffortObject (uses it) before PreToolUseInput (uses EffortObject).
        assert names.index("EffortLevel") < names.index("EffortObject")
        assert names.index("EffortObject") < names.index("PreToolUseInput")

    def test_resolve__pre_tool_use_input__yields_dataclass_spec_with_common_fields(self, resolver):
        spec = _by_name(resolver.resolve(["PreToolUseInput"]), "PreToolUseInput")
        assert isinstance(spec, RecordSpec)
        json_names = {f.json_name for f in spec.fields}
        assert {"session_id", "tool_name", "tool_input", "tool_use_id"} <= json_names

    def test_resolve__dataclass_spec__required_before_optional(self, resolver):
        spec = _by_name(resolver.resolve(["PreToolUseInput"]), "PreToolUseInput")
        required_flags = [f.required for f in spec.fields]
        # No optional field precedes a required one (the dataclass default-ordering rule).
        assert required_flags == sorted(required_flags, reverse=True)

    def test_resolve__permission_mode__emits_str_enum_spec(self, resolver):
        spec = _by_name(resolver.resolve(["PreToolUseInput"]), "PermissionMode")
        assert isinstance(spec, EnumSpec)
        assert {"default", "acceptEdits", "bypassPermissions"} <= set(spec.wire_values)

    def test_resolve__enum_spec__preserves_wire_values_verbatim(self, resolver):
        spec = _by_name(resolver.resolve(["PreToolUseInput"]), "PermissionMode")
        # Member-identifier derivation (acceptEdits -> ACCEPT_EDITS) is the macro's job now; the spec
        # carries only the wire values, preserved verbatim.
        assert "acceptEdits" in spec.wire_values

    def test_resolve__pre_tool_use_output__synthesizes_hook_specific_output_spec(self, resolver):
        specs = resolver.resolve(["PreToolUseOutput"])
        synth = _by_name(specs, "PreToolUseHookSpecificOutput")
        assert isinstance(synth, RecordSpec)
        # Synthesized class is emitted before its owner.
        names = [s.class_name for s in specs]
        assert names.index("PreToolUseHookSpecificOutput") < names.index("PreToolUseOutput")
        # hookSpecificOutput on the owner points at the synthesized class, not an open object.
        owner = _by_name(specs, "PreToolUseOutput")
        hso = next(f for f in owner.fields if f.json_name == "hookSpecificOutput")
        assert hso.type_node == RefNode("PreToolUseHookSpecificOutput")

    def test_resolve__continue_field__wire_name_preserved(self, resolver):
        # The reserved-word identifier (continue -> continue_) is derived by the Python macro; the
        # spec preserves the wire name verbatim.
        owner = _by_name(resolver.resolve(["PreToolUseOutput"]), "PreToolUseOutput")
        assert any(f.json_name == "continue" for f in owner.fields)

    def test_resolve__version_gated_field__forced_optional(self, resolver):
        synth = _by_name(resolver.resolve(["PreToolUseOutput"]), "PreToolUseHookSpecificOutput")
        # permissionDecision carries x-version-gated-defer -> optional despite the shape.
        pd = next(f for f in synth.fields if f.json_name == "permissionDecision")
        assert pd.required is False


def _by_name(specs, class_name):
    return next(s for s in specs if s.class_name == class_name)
