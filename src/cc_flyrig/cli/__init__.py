"""Thin wrappers over external command-line tools the toolkit shells out to.

Shared across subsystems: the codegen factory uses ``ruff`` (format generated source); the capture
harness uses ``tmux`` (drive an interactive ``claude`` session). Each wrapper isolates subprocess
invocation behind small, testable functions so callers use a Python API and can inject fakes instead
of assembling argv inline.
"""
