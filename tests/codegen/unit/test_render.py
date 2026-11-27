"""Tests for the render macros on synthetic specs (render.EntrypointRenderer, no IR on disk).

Pins shapes no committed IR def exercises end-to-end yet: a *required* nullable field whose type
needs a conversion (enum / nested record) must guard that conversion on ``None`` / ``null``, and an
enum ``hookEventName`` (``PreSkillShellCommandOutput``) must render as a literal union, not a const.
"""

import importlib.util
import json
import sys

import pytest

from cc_flyrig.codegen.render import EntrypointContext, EntrypointRenderer
from cc_flyrig.codegen.resolve import EnumSpec, FieldSpec, RecordSpec
from cc_flyrig.codegen.type_ast import LiteralNode, RefNode, ScalarNode

_SPECS = [
    EnumSpec("Color", ("red", "blue")),
    RecordSpec("Thing", (FieldSpec("x", ScalarNode("string"), True),)),
    RecordSpec(
        "ProbeInput",
        (
            FieldSpec("name", ScalarNode("string"), True, nullable=True),
            FieldSpec("color", RefNode("Color"), True, nullable=True),
            FieldSpec("thing", RefNode("Thing"), True, nullable=True),
            FieldSpec("hookEventName", LiteralNode(("PreSkillShellCommand", "PreToolUse")), True),
            FieldSpec("opt", ScalarNode("string"), False, nullable=True),
        ),
    ),
]


def _render(runtime: str) -> str:
    ctx = EntrypointContext(
        cc_version="9.9.9",
        schema_date="2026-11-27",
        event="Probe",
        event_snake="probe",
        input_class="ProbeInput",
        output_class=None,
        decision_pattern="none",
        runtime=runtime,
        specs=_SPECS,
    )
    return EntrypointRenderer().render_harness(ctx)


@pytest.fixture(scope="module")
def python_source():
    return _render("python")


@pytest.fixture(scope="module")
def typescript_source():
    return _render("typescript")


@pytest.fixture(scope="module")
def probe_module(python_source, tmp_path_factory):
    path = tmp_path_factory.mktemp("probe") / "_harness.py"
    path.write_text(python_source)
    spec = importlib.util.spec_from_file_location("probe_render_harness", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass(slots=True) resolves annotations via sys.modules
    spec.loader.exec_module(module)
    return module


class TestRequiredNullablePython:
    def test_render__required_nullable_scalar__annotated_optional_without_default(self, python_source):
        assert "    name: str | None\n" in python_source

    def test_render__optional_nullable_field__unchanged_default_none(self, python_source):
        assert "    opt: str | None = None\n" in python_source

    def test_render__required_nullable_enum_and_record__guard_conversions(self, python_source):
        assert 'color=Color(data["color"]) if data["color"] is not None else None,' in python_source
        assert 'thing=Thing.from_dict(data["thing"]) if data["thing"] is not None else None,' in python_source
        assert 'result["color"] = self.color.value if self.color is not None else None' in python_source
        assert 'result["thing"] = self.thing.to_dict() if self.thing is not None else None' in python_source

    @pytest.mark.parametrize(
        "wire",
        [
            {"name": None, "color": None, "thing": None, "hookEventName": "PreToolUse"},
            {"name": "n", "color": "blue", "thing": {"x": "y"}, "hookEventName": "PreSkillShellCommand"},
        ],
    )
    def test_from_dict__required_nullable_fields__round_trip_null_and_value(self, probe_module, wire):
        # A required nullable key stays on the wire as null (unlike an optional, which is dropped).
        assert probe_module.ProbeInput.from_dict(wire).to_dict() == wire


class TestRequiredNullableTypeScript:
    def test_render__required_nullable_scalar__union_with_null(self, typescript_source):
        assert "  name: string | null;\n" in typescript_source

    def test_render__optional_nullable_field__unchanged_question_mark(self, typescript_source):
        assert "  opt?: string;\n" in typescript_source

    def test_render__required_nullable_record__guards_parse_and_serialize(self, typescript_source):
        assert 'thing: data["thing"] != null ? parseThing(data["thing"]) : null,' in typescript_source
        assert 'result["thing"] = obj.thing != null ? serializeThing(obj.thing) : null;' in typescript_source

    def test_render__required_nullable_enum__passes_through(self, typescript_source):
        # A TS string-literal union needs no conversion, so null passes through unchanged.
        assert 'color: data["color"],' in typescript_source
        assert 'result["color"] = obj.color;' in typescript_source


class TestHookEventNameEnum:
    def test_render__hook_event_name_enum__renders_literal_union(self, python_source, typescript_source):
        assert 'hook_event_name: Literal["PreSkillShellCommand", "PreToolUse"]' in python_source
        assert 'hookEventName: "PreSkillShellCommand" | "PreToolUse";' in typescript_source

    def test_from_dict__hook_event_name_enum__passes_through(self, probe_module):
        wire = {"name": "n", "color": "red", "thing": {"x": "y"}, "hookEventName": "PreToolUse"}
        assert json.loads(json.dumps(probe_module.ProbeInput.from_dict(wire).to_dict())) == wire
