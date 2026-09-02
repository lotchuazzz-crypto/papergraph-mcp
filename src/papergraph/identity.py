"""Stable identifiers for papers and theorems."""

from __future__ import annotations

import re

from papergraph.arxiv import normalize_arxiv_id


_LOCAL_RE = re.compile(r"local:[a-z0-9]+(?:[._-][a-z0-9]+)*")
_ARXIV_PAPER_RE = re.compile(
    r"arxiv:(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})", re.I
)
_VERSION_RE = re.compile(r"(?P<base>.+?)(?P<version>v[1-9]\d*)?$")


def normalize_paper_id(value: str) -> str:
    """Validate and normalize a stable paper identifier."""

    normalized = value.strip()
    if _LOCAL_RE.fullmatch(normalized) or _ARXIV_PAPER_RE.fullmatch(normalized):
        return normalized.lower()
    raise ValueError(f"Invalid paper id: {value!r}")


def paper_id_from_arxiv(arxiv_id: str) -> tuple[str, str | None]:
    """Return the version-independent paper ID and optional arXiv version."""

    normalized = normalize_arxiv_id(arxiv_id)
    match = _VERSION_RE.fullmatch(normalized)
    assert match is not None
    base = match.group("base")
    version = match.group("version")
    return normalize_paper_id(f"arxiv:{base}"), version


def global_theorem_id(paper_id: str, local_id: str) -> str:
    """Construct a globally unique theorem ID from paper and local IDs."""

    paper_id = normalize_paper_id(paper_id)
    if not local_id or "::" in local_id:
        raise ValueError(f"Invalid local theorem id: {local_id!r}")
    return f"{paper_id}::{local_id}"


def split_global_theorem_id(value: str) -> tuple[str, str]:
    """Split and validate a globally qualified theorem ID."""

    try:
        paper_id, local_id = value.split("::", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid global theorem id: {value!r}") from exc
    global_theorem_id(paper_id, local_id)
    return normalize_paper_id(paper_id), local_id
