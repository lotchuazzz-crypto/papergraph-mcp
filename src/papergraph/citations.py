"""Extract citation evidence from a loaded LaTeX project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pybtex.database import Entry, parse_file

from papergraph.arxiv import InvalidArxivIdError, normalize_arxiv_id
from papergraph.loader import _is_commented
from papergraph.models import CitationRecord
from papergraph.project import LoadedProject


_COMMAND_START = r"(?<!\\)\\"
_CITATION_RE = re.compile(
    _COMMAND_START
    + r"(?P<command>cite|citep|citet|autocite|parencite|textcite)\s*"
    r"\{(?P<keys>[^}]*)\}"
)
_ARXIV_IDENTIFIER = (
    r"(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})"
    r"(?:v[1-9]\d*)?"
)
_ARXIV_URL_RE = re.compile(
    r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/"
    rf"(?P<identifier>{_ARXIV_IDENTIFIER})(?:\.pdf)?",
    re.IGNORECASE,
)
_ARXIV_NOTE_RE = re.compile(
    rf"\barxiv:\s*(?P<identifier>{_ARXIV_IDENTIFIER})",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"^(?P<identifier>.+?)(?P<version>v[1-9]\d*)$")


@dataclass(frozen=True, slots=True)
class CitationUse:
    key: str
    command: str
    source_file: str
    position: int


def extract_citation_uses(project: LoadedProject) -> tuple[CitationUse, ...]:
    """Return supported, uncommented citation commands in document order."""

    uses: list[CitationUse] = []
    for span in project.spans:
        fragment = project.text[span.start:span.end]
        source_file = _relative_path(span.path, project.project_root)
        for match in _CITATION_RE.finditer(fragment):
            if _is_commented(fragment, match.start()):
                continue
            for key in match.group("keys").split(","):
                normalized_key = key.strip()
                if normalized_key:
                    uses.append(
                        CitationUse(
                            key=normalized_key,
                            command=match.group("command"),
                            source_file=source_file,
                            position=span.start + match.start(),
                        )
                    )
    return tuple(uses)


def build_citation_records(
    project: LoadedProject,
) -> tuple[CitationRecord, ...]:
    """Resolve each citation use against the project's bibliography files."""

    entries = _load_bibliography_entries(project)
    return tuple(
        _citation_record(use, entries.get(use.key), project)
        for use in extract_citation_uses(project)
    )


def _load_bibliography_entries(
    project: LoadedProject,
) -> dict[str, tuple[Entry, Path]]:
    entries: dict[str, tuple[Entry, Path]] = {}
    for bibliography_file in project.bibliography_files:
        bibliography = parse_file(str(bibliography_file), bib_format="bibtex")
        for key, entry in bibliography.entries.items():
            previous = entries.get(key)
            if previous is None:
                entries[key] = (entry, bibliography_file)
                continue
            if not _same_entry(previous[0], entry):
                raise ValueError(f"Conflicting bibliography entries for key: {key}")
    return entries


def _citation_record(
    use: CitationUse,
    resolved: tuple[Entry, Path] | None,
    project: LoadedProject,
) -> CitationRecord:
    if resolved is None:
        return CitationRecord(
            citation_key=use.key,
            command=use.command,
            source_file=use.source_file,
            bib_file=None,
            bib_entry_type=None,
            cited_arxiv_id=None,
            cited_version=None,
            resolution_status="missing_bib_entry",
        )

    entry, bibliography_file = resolved
    identifier = _resolve_arxiv_identifier(entry)
    cited_arxiv_id, cited_version = _normalize_identifier(identifier)
    return CitationRecord(
        citation_key=use.key,
        command=use.command,
        source_file=use.source_file,
        bib_file=_relative_path(bibliography_file, project.project_root),
        bib_entry_type=entry.type,
        cited_arxiv_id=cited_arxiv_id,
        cited_version=cited_version,
        resolution_status=(
            "resolved_candidate" if cited_arxiv_id else "unsupported_identifier"
        ),
    )


def _resolve_arxiv_identifier(entry: Entry) -> str | None:
    fields = {name.lower(): value for name, value in entry.fields.items()}
    candidates: list[str] = []
    if fields.get("archiveprefix", "").lower() == "arxiv":
        candidates.append(fields.get("eprint", ""))
    candidates.append(fields.get("arxiv", ""))

    url_match = _ARXIV_URL_RE.search(fields.get("url", ""))
    if url_match is not None:
        candidates.append(url_match.group("identifier"))

    note_match = _ARXIV_NOTE_RE.search(fields.get("note", ""))
    if note_match is not None:
        candidates.append(note_match.group("identifier"))

    for candidate in candidates:
        if candidate:
            try:
                normalize_arxiv_id(candidate)
            except InvalidArxivIdError:
                continue
            return candidate
    return None


def _normalize_identifier(identifier: str | None) -> tuple[str | None, str | None]:
    if identifier is None:
        return None, None
    normalized = normalize_arxiv_id(identifier)
    match = _VERSION_RE.fullmatch(normalized)
    if match is None:
        return normalized, None
    return match.group("identifier"), match.group("version")


def _same_entry(first: Entry, second: Entry) -> bool:
    return (
        first.type == second.type
        and dict(first.fields) == dict(second.fields)
        and dict(first.persons) == dict(second.persons)
    )


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
