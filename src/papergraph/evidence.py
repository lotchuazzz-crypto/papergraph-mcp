"""Source-agnostic evidence records for PaperGraph extraction."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

from papergraph.identity import global_theorem_id


EVIDENCE_EMPTY_DEPENDENCY_WARNING = (
    "No proof-local dependencies were detected from explicit evidence. "
    "This is not evidence that the proof has no mathematical dependencies."
)


class EvidenceError(ValueError):
    """Raised when evidence records cannot be constructed."""


def confidence(value: float) -> float:
    """Validate and normalize an evidence confidence score."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise EvidenceError(f"Invalid confidence value: {value!r}")
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        raise EvidenceError(f"Invalid confidence value: {value!r}")
    return normalized


def bounded_excerpt(text: str, limit: int = 240) -> str:
    """Return a whitespace-normalized excerpt bounded to ``limit`` characters."""

    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def slug_fragment(value: str) -> str:
    """Return a stable ASCII slug fragment for evidence-local identifiers."""

    fragments: list[str] = []
    previous_was_separator = False
    for character in value.lower():
        if character.isascii() and (character.isalnum() or character in "._-"):
            fragments.append(character)
            previous_was_separator = False
        elif not previous_was_separator:
            fragments.append("-")
            previous_was_separator = True
    slug = "".join(fragments).strip("-")
    return slug or "item"


def evidence_result_id(paper_id: str, local_id: str) -> str:
    """Construct a globally unique evidence result identifier."""

    return global_theorem_id(paper_id, local_id)


def evidence_pdf_result_local_id(
    kind: str, visible_number: str | None, ordinal: int
) -> str:
    """Construct a stable local result ID for PDF-extracted results."""

    normalized_kind = slug_fragment(kind)
    suffix = visible_number if visible_number else str(ordinal)
    return f"pdf:{normalized_kind}:{suffix}"


@dataclass(frozen=True, slots=True)
class SourceSpanEvidence:
    paper_id: str
    source_type: str
    source_ref: str
    page: int | None
    block_index: int | None
    start_offset: int | None
    end_offset: int | None
    bbox: tuple[float, float, float, float] | None
    text: str
    method: str
    confidence: float
    span_id: str | None = None

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class ResultEvidence:
    result_id: str
    paper_id: str
    local_id: str
    kind: str
    raw_kind: str
    display_kind: str
    normalized_kind: str
    label: str | None
    visible_number: str | None
    title: str | None
    statement: str
    span_indices: tuple[int, ...]
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class ProofEvidence:
    proof_id: str
    paper_id: str
    result_id: str | None
    text: str
    span_indices: tuple[int, ...]
    association_basis: str
    association_confidence: float
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.association_confidence)
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class BibliographyEntryEvidence:
    entry_id: str
    paper_id: str
    raw_label: str
    raw_text: str
    entry_type: str
    title: str | None
    authors: tuple[str, ...]
    year: int | None
    arxiv_id: str | None
    arxiv_version: str | None
    doi: str | None
    url: str | None
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class LocalResultMentionEvidence:
    mention_id: str
    paper_id: str
    proof_id: str | None
    raw_text: str
    kind: str
    visible_number: str | None
    target_result_id: str | None
    resolution_status: str
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class CitationMentionEvidence:
    mention_id: str
    paper_id: str
    proof_id: str | None
    raw_text: str
    raw_key: str
    entry_id: str | None
    resolution_status: str
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class ExternalResultMentionEvidence:
    mention_id: str
    paper_id: str
    proof_id: str | None
    citation_mention_id: str | None
    raw_text: str
    external_kind: str
    external_number: str | None
    entry_id: str | None
    target_paper_id: str | None
    resolution_status: str
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class EvidenceEdge:
    edge_id: str
    paper_id: str
    source_id: str
    target_id: str
    relation: str
    evidence_ids: tuple[str, ...]
    method: str
    confidence: float

    def __post_init__(self) -> None:
        confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    paper_id: str
    source_type: str
    source_ref: str
    source_version: str | None
    title: str | None
    authors: tuple[str, ...]
    main_file: str
    spans: tuple[SourceSpanEvidence, ...]
    results: tuple[ResultEvidence, ...]
    proofs: tuple[ProofEvidence, ...]
    bibliography_entries: tuple[BibliographyEntryEvidence, ...]
    local_result_mentions: tuple[LocalResultMentionEvidence, ...]
    citation_mentions: tuple[CitationMentionEvidence, ...]
    external_result_mentions: tuple[ExternalResultMentionEvidence, ...]
    edges: tuple[EvidenceEdge, ...]
    warnings: tuple[str, ...]


def source_span_payload(span: SourceSpanEvidence) -> dict:
    """Serialize a source span for graph/tool payloads."""

    return {
        "span_id": span.span_id,
        "paper_id": span.paper_id,
        "source_type": span.source_type,
        "source_ref": span.source_ref,
        "page": span.page,
        "block_index": span.block_index,
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
        "bbox": list(span.bbox) if span.bbox is not None else None,
        "excerpt": bounded_excerpt(span.text),
        "method": span.method,
        "confidence": confidence(span.confidence),
    }
