"""Tests for toolchain.py: resolve_toolchain and load_runtime_profile."""

import json
from pathlib import Path

import pytest

from cc_flyrig.codegen.profile import Toolchain
from cc_flyrig.codegen.toolchain import CHECKERS, FORMATTERS, load_runtime_profile, resolve_toolchain

SCHEMAS_DIR = Path(__file__).parent.parent.parent.parent / "schemas"
CC_VERSION = "2.1.198"

_VALID_PROFILE = {
    "language": "python",
    "extension": "py",
    "stub_name": "__main__",
    "formatter": "ruff",
    "checker": None,
}

_REQUIRED_KEYS = ("extension", "stub_name", "formatter", "checker")


class TestLoadRuntimeProfile:
    @pytest.mark.parametrize("missing_key", _REQUIRED_KEYS)
    def test_load_runtime_profile__missing_required_key__raises_naming_key_and_path(self, tmp_path, missing_key):
        version_dir = tmp_path / "cc-9.9.9"
        lang_dir = version_dir / "lang"
        lang_dir.mkdir(parents=True)
        data = {k: v for k, v in _VALID_PROFILE.items() if k != missing_key}
        profile_path = lang_dir / "python.json"
        profile_path.write_text(json.dumps(data))

        with pytest.raises(ValueError) as exc_info:
            load_runtime_profile(version_dir, "python")

        message = str(exc_info.value)
        assert missing_key in message
        assert str(profile_path) in message

    def test_load_runtime_profile__committed_python_profile__resolves_real_profile(self):
        profile = load_runtime_profile(SCHEMAS_DIR / f"cc-{CC_VERSION}", "python")
        assert profile.runtime == "python"
        assert profile.extension == "py"
        assert profile.stub_name == "__main__"


class TestResolveToolchain:
    def test_resolve_toolchain__unknown_formatter__raises_listing_registered_formatters(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_toolchain("no-such-formatter", None)

        message = str(exc_info.value)
        assert "no-such-formatter" in message
        for name in FORMATTERS:
            assert name in message

    def test_resolve_toolchain__unknown_checker__raises_listing_registered_checkers(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_toolchain(None, "no-such-checker")

        message = str(exc_info.value)
        assert "no-such-checker" in message
        for name in CHECKERS:
            assert name in message

    def test_resolve_toolchain__both_none__returns_identity_format_and_no_op_check(self):
        toolchain = resolve_toolchain(None, None)
        assert toolchain.format is Toolchain.identity
        assert toolchain.format("unchanged") == "unchanged"
        toolchain.check("anything")  # must not raise
