"""Family-keyed schema resolution: find the right ``<family>.schema.json`` for a CC version.

Generalizes the former hooks-only ``_find_schema`` and the statusline-only
``_find_statusline_schema`` (``capture/__main__.py``) into a single family-keyed resolver. Both
surfaces now get the same strict behavior: once an explicit ``--cc-version`` is given, a missing
schema for that family is a hard error (not a silent fallthrough to "specify --cc-version"),
because the caller already specified one.

May glob the schemas directory to *discover* candidate paths, but decides nothing beyond which
path to return or which error to raise — no file reads, no writes, no printing.
"""

from pathlib import Path


def find(family: str, cc_version: str | None, schemas_dir: Path) -> Path:
    """Resolve ``schemas/cc-<version>/<family>.schema.json``.

    - No ``cc_version`` + exactly one schema of that family exists -> return it.
    - No ``cc_version`` + zero or more than one -> raise, telling the caller to specify
      ``--cc-version`` (and listing what was found).
    - Explicit ``cc_version`` + the file exists -> return it.
    - Explicit ``cc_version`` + the file is missing -> raise, telling the caller to
      ``schema seed <version>`` first, then re-run ``check``.
    """
    filename = f"{family}.schema.json"
    schemas = sorted(schemas_dir.glob(f"cc-*/{filename}"))

    if cc_version:
        match = schemas_dir / f"cc-{cc_version}" / filename
        if match.exists():
            return match
        raise SystemExit(
            f"no {filename} for cc-{cc_version} — run: python -m cc_flyrig.schema seed "
            f"{cc_version}, then re-run check; found schemas: {[str(s) for s in schemas]}"
        )

    if len(schemas) == 1:
        return schemas[0]
    raise SystemExit(f"specify --cc-version; found {family} schemas: {[str(s) for s in schemas]}")
