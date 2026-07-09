"""Coverage report: build the model and render it to Markdown."""

from .input_builder import (
    MISSING,
    NOT_ATTEMPTED,
    OBSERVED,
    CoverageReport,
    EventCoverage,
    build_input_report,
)
from .output_builder import (
    FAIL,
    NOT_TESTED,
    PASS,
    UNOBSERVABLE,
    FieldResult,
    OutputCoverageReport,
    build_output_report,
)
from .documented_hooks_builder import DocumentedHooksReport, build_documented_hooks_report
from .statusline_builder import (
    StatuslineCoverageReport,
    StatuslineEventCoverage,
    build_statusline_report,
)
from .rendering import (
    render_documented_hooks,
    render_input_coverage,
    render_output_coverage,
    render_statusline_coverage,
)

__all__ = [
    # input side
    "MISSING",
    "NOT_ATTEMPTED",
    "OBSERVED",
    "CoverageReport",
    "EventCoverage",
    "build_input_report",
    "render_input_coverage",
    # output side
    "FAIL",
    "NOT_TESTED",
    "PASS",
    "UNOBSERVABLE",
    "FieldResult",
    "OutputCoverageReport",
    "build_output_report",
    "render_output_coverage",
    # documented-hooks (/hooks menu)
    "DocumentedHooksReport",
    "build_documented_hooks_report",
    "render_documented_hooks",
    # statusline event family
    "StatuslineCoverageReport",
    "StatuslineEventCoverage",
    "build_statusline_report",
    "render_statusline_coverage",
]
