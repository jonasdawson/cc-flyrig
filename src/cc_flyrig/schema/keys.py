"""Naming conventions for addressing definitions in the canonical IR JSON Schema."""


def input_def_name(event: str) -> str:
    """Return the ``$defs`` key holding the input shape for ``event`` (e.g. ``PreToolUseInput``)."""
    return f"{event}Input"


def output_def_name(event: str) -> str:
    """Return the ``$defs`` key holding the output shape for ``event`` (e.g. ``PreToolUseOutput``)."""
    return f"{event}Output"
