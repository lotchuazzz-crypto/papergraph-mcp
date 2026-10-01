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
        timeout=10,
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
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
        "dependency_capabilities": {
            "statement_graph": {
                "basis": DEPENDENCY_EXTRACTION_BASIS,
                "tools": ["get_dependencies", "workspace_get_dependencies"],
            },
            "proof_local": {
                "basis": "source_backed_explicit_proof_local_evidence",
                "tools": ["workspace_get_proof_dependencies",
                          "workspace_get_result_reading_path",
                          "workspace_get_dependency_reading",
                          "workspace_export_result_reading_context"],
                "complete_mathematical_dependencies": False,
                "author_declared_correspondence": {
                    "relation": "author_declared_correspondence",
                    "proof_entry": "bounded_source_backed_navigation",
                    "hop_limit": 8,
                    "mathematical_equivalence_verified": False,
                },
                "limitations": [
                    "Only explicit source evidence is extracted; implicit reasoning is not inferred.",
                    "Coverage depends on available source and proof association; empty output is not independence.",
                ],
            },
        },
        "paper_input_capabilities": {
            "importable_sources": ["local_latex", "arxiv_source", "local_pdf"],
            "doi_is_fulltext": False,
            "doi_role": "metadata_identity_not_fulltext",
            "doi_discovery": {
                "tool": "discover_doi_paper",
                "identity_basis": "exact_provider_doi",
                "downloads": False,
                "providers": ["crossref", "openalex"],
            },
            "doi_candidate_import": {
                "tool": "workspace_import_doi_candidate",
                "requires_selected_candidate_confirmation": True,
                "external_references_auto_download": False,
            },
            "doi_root_import": {
                "tool": "workspace_add_doi_paper",
                "requires_unique_eligible_public_pdf": True,
                "scope": "user_requested_root_only",
                "external_references_auto_download": False,
            },
            "pdf_limitations": "Born-digital text; scanned PDFs need external OCR.",
        },
        "git": git,
        "warnings": warnings,
    }
