"""Restore the maintainer's own Claude Code ``settings.json`` after a driven capture run.

Some driven commands persist state into the *user* settings file even under
``--setting-sources project``. cc-2.1.332's ``/model <name>`` saves ``"model"`` as the default for new
sessions. The harness must never leave a maintainer's own config changed. The restore is whole-file
and byte-for-byte, so an edit the maintainer makes to that file *during* a run is reverted too.
"""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def user_settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "settings.json"


@contextmanager
def preserve_user_settings(path: Path | None = None) -> Iterator[None]:
    target = path or user_settings_path()
    original = target.read_bytes() if target.exists() else None
    try:
        yield
    finally:
        current = target.read_bytes() if target.exists() else None
        if current != original:
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
            print(f"restored {target} (a driven session modified it)", file=sys.stderr)
