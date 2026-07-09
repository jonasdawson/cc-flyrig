"""Pure core of ``schema seed``: patch a schema's version metadata for a new CC version.

No filesystem access — the composition root (``schema/__main__.py``) resolves source/target paths,
reads/writes files, and copies ``lang/``; this module only produces the patched dict.
"""


def reseed(schema: dict, source_version: str, new_version: str, today: str) -> dict:
    """Return a NEW schema dict with ``$id``/``description``/``x-cc-version``/``x-schema-date``
    patched to ``new_version``, leaving ``schema`` untouched."""
    patched = dict(schema)
    patched["$id"] = schema["$id"].replace(source_version, new_version)
    patched["description"] = schema["description"].replace(source_version, new_version)
    patched["x-cc-version"] = new_version
    patched["x-schema-date"] = today
    return patched
