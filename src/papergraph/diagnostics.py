"""Runtime diagnostics for first-use PaperGraph setup."""

from __future__ import annotations

import subprocess
from importlib.metadata import version as distribution_version
from pathlib import Path

from papergraph.models import DEPENDENCY_EXTRACTION_BASIS


PACKAGE_NAME = "papergraph-mcp"
REPOSITORY_SOURCE = "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git"


def _git_output(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_context(cwd: Path) -> dict | None:
    try:
        top_level = _git_output(["rev-parse", "--show-toplevel"], cwd)
        commit = _git_output(["rev-parse", "--short=12", "HEAD"], cwd)
        branch = _git_output(["branch", "--show-current"], cwd)
        return {
            "top_level": top_level,
            "commit": commit,
            "branch": branch or None,
        }
    except (OSError, subprocess.CalledProcessError):
        return None


def environment_diagnostics(cwd: Path | None = None) -> dict:
    """Return deterministic setup information for agents and users."""

    version = distribution_version(PACKAGE_NAME)
    release_tag = f"v{version}"
    git = _git_context((cwd or Path.cwd()).resolve())
    warnings: list[str] = []

    if git is None:
        warnings.append(
            "Git context unavailable; use the release-pinned uvx source for "
            "reproducible first use."
        )

    return {
        "package_name": PACKAGE_NAME,
        "version": version,
        "release_tag": release_tag,
        "recommended_source": f"{REPOSITORY_SOURCE}@{release_tag}",
        "dependency_extraction_basis": DEPENDENCY_EXTRACTION_BASIS,
        "git": git,
        "warnings": warnings,
    }
