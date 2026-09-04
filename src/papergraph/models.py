from dataclasses import dataclass


DEPENDENCY_EXTRACTION_BASIS = "statement_explicit_latex_refs_only"
EMPTY_DEPENDENCY_WARNING = (
    "No explicit theorem-label dependencies were detected in the theorem statement. "
    "This is not evidence that the theorem has no mathematical dependencies."
)


@dataclass(slots=True)
class TheoremNode:
    id: str
    kind: str
    title: str | None
    label: str | None
    content: str
    refs: tuple[str, ...]
    position: int
    raw_kind: str | None = None
    display_kind: str | None = None
    normalized_kind: str | None = None
    source_file: str | None = None

    def __post_init__(self) -> None:
        if self.raw_kind is None:
            self.raw_kind = self.kind
        if self.display_kind is None:
            self.display_kind = self.raw_kind
        if self.normalized_kind is None:
            self.normalized_kind = self.raw_kind.lower()

    def summary(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "raw_kind": self.raw_kind,
            "display_kind": self.display_kind,
            "normalized_kind": self.normalized_kind,
            "title": self.title,
            "label": self.label,
            "refs": list(self.refs),
        }

    def full(self) -> dict:
        return {
            **self.summary(),
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class PaperRecord:
    paper_id: str
    source_type: str
    source_ref: str
    source_version: str | None
    title: str | None
    authors: tuple[str, ...]
    main_file: str
    imported_at: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class CitationRecord:
    citation_key: str
    command: str
    source_file: str
    bib_file: str | None
    bib_entry_type: str | None
    cited_arxiv_id: str | None
    cited_version: str | None
    resolution_status: str


@dataclass(frozen=True, slots=True)
class WorkspaceImportResult:
    paper_id: str
    theorem_count: int
    citation_count: int
    unresolved_citation_count: int
    result_count: int = 0
    proof_count: int = 0
    bibliography_entry_count: int = 0
    local_mention_count: int = 0
    external_mention_count: int = 0
    unresolved_count: int = 0
    warnings: tuple[str, ...] = ()

    def evidence_import_summary(self) -> dict:
        payload = {
            "result_count": self.result_count,
            "proof_count": self.proof_count,
            "bibliography_entry_count": self.bibliography_entry_count,
            "local_mention_count": self.local_mention_count,
            "external_mention_count": self.external_mention_count,
            "unresolved_count": self.unresolved_count,
        }
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload
