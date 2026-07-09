"""Version-pinned, isolated Claude Code provisioner.

Installs a specific Claude Code release into an isolated prefix so the capture
harness can exercise any historical CC version deterministically.

**Auth is not provisioned.**  A real authenticated session and API budget are
required for capture runs.  The caller must supply ``ANTHROPIC_API_KEY`` or
mount OAuth credentials into ``CLAUDE_CONFIG_DIR`` before invoking the capture
battery.  ``provision`` never fabricates or caches credentials.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .orchestrator.scenario_runner import CaptureError, ClaudeInstall
from .util.cc_version import detect_cc_version


def provision(
    version: str,
    *,
    root: Path,
    method: str = "npm",
    config_dir: Path | None = None,
    run=subprocess.run,
) -> ClaudeInstall:
    """Install a pinned Claude Code into *root/<version>* and return the install.

    Parameters
    ----------
    version:
        Exact CC version to install (e.g. ``"2.1.183"``).
    root:
        Directory under which each version gets its own sub-directory
        (``root/<version>/``).  Each version is retained independently so any
        historical release can be re-captured without reinstalling.
    method:
        Installation method.

        ``"npm"`` (default)
            ``npm install -g @anthropic-ai/claude-code@<version>
            --prefix <root>/<version>``; bin resolves to
            ``<root>/<version>/bin/claude``.  All historical releases are on
            the npm registry.

        ``"native"``
            ``curl -fsSL https://claude.ai/install.sh | bash -s <version>``.
            Forward path for releases past npm's deprecation horizon.

    config_dir:
        Override the ``CLAUDE_CONFIG_DIR`` for the isolated install.  Defaults
        to ``root/<version>/.config`` so each version's state is fully
        isolated.  Pass the same value to :func:`isolation_env` to keep the
        two consistent.
    run:
        Injectable ``subprocess.run`` replacement used in tests to avoid real
        network calls.

    Returns
    -------
    ClaudeInstall
        Resolved bin path and the pinned version.  Call :func:`isolation_env`
        with the same *version*, *root*, and *config_dir* to obtain the env
        vars (``CLAUDE_CONFIG_DIR``, ``DISABLE_AUTOUPDATER``,
        ``DISABLE_UPDATES``) that suppress auto-updates and isolate config
        state.

    Raises
    ------
    CaptureError
        If the install command fails, or if the installed binary reports a
        version that does not match *version* (pin-assertion guard).

    Notes
    -----
    **Auth is not provisioned.**  Capture needs a real authenticated session
    and API budget; the caller must supply ``ANTHROPIC_API_KEY`` or mount
    OAuth credentials into ``CLAUDE_CONFIG_DIR`` before running the scenario
    battery.  ``provision`` never fabricates or caches credentials.
    """
    if method == "npm":
        prefix = root / version
        _install_npm(version, prefix=prefix, run=run)
        bin_path = prefix / "bin" / "claude"
    elif method == "native":
        bin_path = _install_native(version, run=run)
    else:
        raise CaptureError(f"unknown provision method: {method!r}; expected 'npm' or 'native'")

    install = ClaudeInstall(bin=str(bin_path), version=version)

    # U3 — pin assertion: guard against silent auto-updates, wrong-prefix
    # resolutions, or registry surprises before the expensive battery runs.
    detected = detect_cc_version(install.bin)
    if detected != version:
        raise CaptureError(f"provisioned {detected!r}, expected {version!r}")

    return install


def isolation_env(
    version: str,
    *,
    root: Path,
    config_dir: Path | None = None,
) -> dict[str, str]:
    """Return the isolation environment variables for a provisioned install.

    Merge the returned dict into the child-process environment (or the
    orchestrator's session env) before running the capture battery so that
    auto-updates and config-state bleed are suppressed.

    Parameters
    ----------
    version:
        The CC version that was (or will be) provisioned.
    root:
        The same *root* that was passed to :func:`provision`.
    config_dir:
        Override the ``CLAUDE_CONFIG_DIR`` (same semantics as in
        :func:`provision`).  Must match the value used in :func:`provision` to
        ensure the env points at the correct isolated config directory.

    Returns
    -------
    dict[str, str]
        ``CLAUDE_CONFIG_DIR``, ``DISABLE_AUTOUPDATER``, and ``DISABLE_UPDATES``
        ready to merge into ``os.environ`` or a child-process ``env`` dict.
    """
    prefix = root / version
    cfg_dir = config_dir if config_dir is not None else (prefix / ".config")
    return {
        "CLAUDE_CONFIG_DIR": str(cfg_dir),
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_UPDATES": "1",
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _install_npm(version: str, *, prefix: Path, run) -> None:
    """Run ``npm install -g @anthropic-ai/claude-code@<version> --prefix <prefix>``."""
    prefix.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            "npm",
            "install",
            "-g",
            f"@anthropic-ai/claude-code@{version}",
            "--prefix",
            str(prefix),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CaptureError(f"npm install failed (exit {result.returncode}):\n{result.stderr}")


def _install_native(version: str, *, run) -> Path:
    """Run the official install script and return the launcher path."""
    result = run(
        ["bash", "-c", f"curl -fsSL https://claude.ai/install.sh | bash -s {version}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CaptureError(f"native install failed (exit {result.returncode}):\n{result.stderr}")
    # The install script typically reports the installed path on stdout/stderr.
    # Scan for the first absolute path that mentions "claude" and exists on disk.
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in combined.splitlines():
        line = line.strip()
        if line.startswith("/") and "claude" in line:
            candidate = Path(line)
            if candidate.exists():
                return candidate
    # Conventional fallback location used by the official installer.
    return Path("/usr/local/bin/claude")
