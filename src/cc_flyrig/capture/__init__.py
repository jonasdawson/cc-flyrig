"""Capture harness: build-time validation of the canonical IR against real CC hook payloads.

Maintainer-run live capture (the probe + tmux-driven scenario battery + consolidation) produces a
versioned ``captures/`` tree; the per-PR CI gate only diffs that committed tree against the committed
IR.
"""
