"""Shared fixtures for unit and integration tests."""

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads((_ROOT / "schemas" / "cc-2.1.168" / "hooks.schema.json").read_text())


@pytest.fixture(scope="module")
def statusline_schema() -> dict:
    return json.loads((_ROOT / "schemas" / "cc-2.1.198" / "statusline.schema.json").read_text())
