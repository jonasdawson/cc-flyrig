"""Generation settings — the config DTO the composition root builds and injects.

This is configuration data, not behavior, so it is a plain frozen dataclass rather than one of the
verb-named pipeline modules. ``__main__`` constructs exactly one ``Settings`` from the validated CLI
inputs and passes it into the collaborators that need it (``IntermediateRepresentationLoader`` for
paths/version/family selection, ``EntrypointRenderer`` for rendering). The runtime's output
shape/tooling is not here — that is ``profile.RuntimeProfile``, resolved separately and injected
alongside ``Settings``. Nothing reaches for it as a module global, which keeps ``Generator.run()``
testable without argv.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable inputs for one generation run."""

    event: str
    """Event to scaffold (e.g. ``PreToolUse``, ``StatusLine``); validated against the IR's known events."""

    cc_version: str
    """Claude Code schema version to read and stamp (e.g. ``2.1.177``)."""

    family: str = "hooks"
    """Which event family to scaffold: ``hooks`` (default) or ``statusline``.

    An event family is a named set of related events sharing one schema file and one Claude Code
    settings-key wiring. Selects which schema file ``IntermediateRepresentationLoader`` reads from
    ``version_dir`` — families version independently under the same ``schemas/cc-<version>/``
    directory.
    """

    schemas_dir: Path = Path("schemas")
    """Root of the committed ``schemas/cc-<version>/`` tree."""

    out_dir: Path = Path(".")
    """Directory the generated entrypoint is written to."""

    @property
    def version_dir(self) -> Path:
        """The ``schemas/cc-<version>/`` directory this run reads from."""
        return self.schemas_dir / f"cc-{self.cc_version}"

    @property
    def schema_filename(self) -> str:
        """The IR file this run's family reads (sibling namespaces under the same ``version_dir``)."""
        return FAMILY_SCHEMA_FILENAMES[self.family]


FAMILY_SCHEMA_FILENAMES = {"hooks": "hooks.schema.json", "statusline": "statusline.schema.json"}
"""Registry of event family -> schema filename. The one seam a new family adds."""
