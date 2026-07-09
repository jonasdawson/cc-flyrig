"""Render coverage report models to Markdown."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .input_builder import CoverageReport
from .statusline_builder import StatuslineCoverageReport

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
    autoescape=False,
)


def render_input_coverage(report: CoverageReport) -> str:
    """Render the coverage report model as Markdown (``INPUT_COVERAGE.md``)."""
    return _ENV.get_template("input_coverage.md.j2").render(report=report)


def render_output_coverage(report) -> str:
    """Render the output coverage report model as Markdown (``OUTPUT_COVERAGE.md``)."""
    return _ENV.get_template("output_coverage.md.j2").render(report=report)


def render_documented_hooks(report) -> str:
    """Render the documented-hooks report model as Markdown (``HOOKS_MENU.md``)."""
    return _ENV.get_template("hooks_menu.md.j2").render(report=report)


def render_statusline_coverage(report: StatuslineCoverageReport) -> str:
    """Render the statusline event family coverage report model as Markdown (``STATUSLINE_COVERAGE.md``)."""
    return _ENV.get_template("statusline_coverage.md.j2").render(report=report)
