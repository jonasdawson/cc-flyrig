"""The Transform stage: read the canonical IR and generate typed Python hook entrypoints.

The package composes as a pipeline named by verb — ``load`` → ``resolve`` → ``translate`` →
``emit`` → ``render`` — wired by the ``__main__`` composition root and coordinated by
``generate.Generator``.
"""
