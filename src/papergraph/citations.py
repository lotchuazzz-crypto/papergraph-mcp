"""Extract citation evidence from a loaded LaTeX project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pybtex.database import Entry, parse_file
from pybtex.database.input.bibtex import LowLevelParser, Parser, SkipEntry
from pybtex.exceptions import PybtexError

from papergraph.arxiv import InvalidArxivIdError, normalize_arxiv_id
from papergraph.identity import paper_id_from_arxiv
from papergraph.loader import _is_commented
from papergraph.models import CitationRecord
from papergraph.project import LoadedProject


_COMMAND_START = r"(?<!\\)\\"
_CITATION_RE = re.compile(
    _COMMAND_START
    + r"(?P<command>(?:autocite|parencite|textcite|citep|citet|cite)\*?)\s*"
    r"(?:\[[^]]*\]\s*){0,2}"
    r"\{(?P<keys>[^}]*)\}"
)
_ARXIV_IDENTIFIER = (
    r"(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})"
    r"(?:v[1-9]\d*)?"
)
_ARXIV_URL_RE = re.compile(
    r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/"
    rf"(?P<identifier>{_ARXIV_IDENTIFIER})(?:\.pdf)?(?=$|[?#])",
    re.IGNORECASE,
)
_ARXIV_NOTE_RE = re.compile(
    rf"\barxiv:\s*(?P<identifier>{_ARXIV_IDENTIFIER})"
    r"(?=$|[\s,;:)\]}]|\.(?=\s|$))",
    re.IGNORECASE,
)


class CitationError(ValueError):
    """Base class for invalid citation or bibliography input."""


class BibliographyParseError(CitationError):
    """Raised when a project's bibliography is malformed."""


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
        relative_path = _relative_path(bibliography_file, project.project_root)
        try:
            bibliography = parse_file(str(bibliography_file), bib_format="bibtex")
        except PybtexError as exc:
            raise BibliographyParseError(
                f"Could not parse bibliography: {relative_path}"
            ) from exc
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
    paper_id, version = paper_id_from_arxiv(identifier)
    return paper_id.removeprefix("arxiv:"), version


def _same_entry(first: Entry, second: Entry) -> bool:
    return (
        first.type == second.type
        and dict(first.fields) == dict(second.fields)
        and dict(first.persons) == dict(second.persons)
    )


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_bibliography_evidence(paper_id: str, project: LoadedProject):
    """Reuse validated BibTeX identity fields and retain their local source text."""
    from papergraph.evidence import BibliographyEntryEvidence, SourceSpanEvidence

    entries, spans = [], []
    source_entries = {}
    for key, (entry, path) in _load_bibliography_entries(project).items():
        text = path.read_text(encoding='utf-8')
        if path not in source_entries:
            source_entries[path] = _bibliography_source_entries(text)
        matches = [item for item in source_entries[path].get(key.casefold(), [])
                   if _same_entry(item[0], entry)]
        if len(matches) != 1:
            raise BibliographyParseError(f"No unique original source for bibliography key: {key}")
        _, start, end = matches[0]
        raw = text[start:end]
        fields = {name.lower(): value for name, value in entry.fields.items()}
        arxiv_id, version = _normalize_identifier(_resolve_arxiv_identifier(entry))
        entry_id = f'{paper_id}::bib:{key}'
        entries.append(BibliographyEntryEvidence(
            entry_id=entry_id, paper_id=paper_id, raw_label=key, raw_text=raw,
            entry_type=entry.type, title=fields.get('title'),
            authors=tuple(str(person) for person in entry.persons.get('author', [])),
            year=int(fields['year']) if fields.get('year', '').isdigit() else None,
            arxiv_id=arxiv_id, arxiv_version=version, doi=fields.get('doi'),
            url=fields.get('url'), method='bibtex_entry', confidence=1.0,
        ))
        spans.append(SourceSpanEvidence(
            paper_id=paper_id, source_type='tex', source_ref=_relative_path(path, project.project_root),
            page=None, block_index=None, start_offset=start, end_offset=end,
            bbox=None, text=raw, method='bibtex_entry', confidence=1.0, span_id=entry_id,
        ))
    return tuple(entries), tuple(spans)


class _SourceBibtexParser(LowLevelParser):
    """Use BibTeX grammar for entries and consume comment bodies completely."""

    def parse_command(self):
        try:
            return super().parse_command()
        except SkipEntry:
            opening = self.text[self.pos - 1]
            if opening == "{":
                list(self.parse_string(self.RBRACE))
            else:
                depth, braces, quoted = 1, 0, False
                while self.pos < len(self.text) and depth:
                    char = self.text[self.pos]
                    self.pos += 1
                    if char == "\\":
                        self.pos += 1
                        continue
                    if char == '"' and braces == 0:
                        quoted = not quoted
                    if not quoted:
                        if char == "{":
                            braces += 1
                        elif char == "}":
                            braces -= 1
                        elif braces == 0 and char == "(":
                            depth += 1
                        elif braces == 0 and char == ")":
                            depth -= 1
                if depth:
                    raise BibliographyParseError("Unclosed bibliography comment")
            raise


def _bibliography_source_entries(text):
    parser = Parser()
    parser.unnamed_entry_counter = 1
    scanner = _SourceBibtexParser(text, macros=parser.macros,
                                  handle_error=parser.handle_error)
    entries = {}
    for entry_type, data in scanner:
        if entry_type.lower() in {"string", "preamble"}:
            continue
        parser.process_entry(entry_type, *data)
        key = data[0]
        if key is None:
            raise BibliographyParseError("Cannot locate unnamed bibliography entry")
        entries.setdefault(key.casefold(), []).append(
            (parser.data.entries[key], scanner.command_start, scanner.pos))
    return entries
