"""Deterministic evidence extraction over PDF text spans."""

from __future__ import annotations

import re

from papergraph.arxiv import InvalidArxivIdError, normalize_arxiv_id
from papergraph.evidence import (
    BibliographyEntryEvidence,
    CitationMentionEvidence,
    EvidenceDocument,
    ExternalResultMentionEvidence,
    LocalResultMentionEvidence,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
    evidence_pdf_result_local_id,
    evidence_result_id,
    slug_fragment,
)


RESULT_RE = re.compile(
    r"^(?P<raw>Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Example|Remark)\s+"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?)\.?\s*(?P<body>.*)$",
    re.I,
)
PROOF_RE = re.compile(
    r"^Proof(?:\s+of\s+(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim)\s+"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?))?\.?\s*(?P<body>.*)$",
    re.I,
)

_BIBLIOGRAPHY_ENTRY_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<body>.+)$")
_ARXIV_RE = re.compile(
    r"(?<![A-Za-z0-9./:-])(?:arXiv:)?"
    r"(?P<id>\d{4}\.\d{4,5}(?:v[1-9]\d*)?|[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v[1-9]\d*)?)"
    r"(?![A-Za-z0-9/-])",
    re.I,
)
_ARXIV_VERSION_RE = re.compile(r"^(?P<base>.+?)(?P<version>v[1-9]\d*)$")
_DOI_RE = re.compile(r"(?:doi:|https://doi\.org/)(?P<doi>\S+)", re.I)
_URL_RE = re.compile(r"https?://\S+")
_LOCAL_RESULT_MENTION_RE = re.compile(
    r"\b(?P<kind>Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Example|Remark)\s+"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?)\b",
    re.I,
)
_CITATION_RE = re.compile(
    r"\[(?P<key>[^\],]+)(?:,\s*(?P<kind>Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Example|Remark)\s+"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?))?\]",
    re.I,
)


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _normalized_kind(kind: str) -> str:
    return kind.casefold()


def _display_kind(kind: str) -> str:
    return kind[:1].upper() + kind[1:].lower()


def _bibliography_start_index(spans: tuple[SourceSpanEvidence, ...]) -> int | None:
    for index, span in enumerate(spans):
        normalized = _normalized_text(span.text).casefold()
        if normalized in {"references", "bibliography"}:
            return index
    return None


def extract_result_blocks(
    paper_id: str,
    spans: tuple[SourceSpanEvidence, ...],
) -> tuple[ResultEvidence, ...]:
    """Extract result-like headings before the bibliography section."""

    bibliography_index = _bibliography_start_index(spans)
    limit = len(spans) if bibliography_index is None else bibliography_index
    results: list[ResultEvidence] = []
    used_local_ids: dict[str, int] = {}

    for span_index, span in enumerate(spans[:limit]):
        text = _normalized_text(span.text)
        match = RESULT_RE.match(text)
        if match is None:
            continue

        raw_kind = match.group("raw")
        visible_number = match.group("number") or None
        base_local_id = evidence_pdf_result_local_id(
            raw_kind,
            visible_number,
            len(results) + 1,
        )
        collision_count = used_local_ids.get(base_local_id, 0) + 1
        used_local_ids[base_local_id] = collision_count
        local_id = (
            base_local_id if collision_count == 1 else f"{base_local_id}:{collision_count}"
        )
        normalized_kind = _normalized_kind(raw_kind)

        results.append(
            ResultEvidence(
                result_id=evidence_result_id(paper_id, local_id),
                paper_id=paper_id,
                local_id=local_id,
                kind=normalized_kind,
                raw_kind=raw_kind,
                display_kind=_display_kind(raw_kind),
                normalized_kind=normalized_kind,
                label=None,
                visible_number=visible_number,
                title=None,
                statement=text,
                span_indices=(span_index,),
                method="pdf_heading_regex",
                confidence=0.85,
            )
        )

    return tuple(results)


def _result_lookup(
    results: tuple[ResultEvidence, ...],
) -> dict[tuple[str, str], list[ResultEvidence]]:
    lookup: dict[tuple[str, str], list[ResultEvidence]] = {}
    for result in results:
        if result.visible_number is None:
            continue
        key = (result.normalized_kind, result.visible_number.casefold())
        lookup.setdefault(key, []).append(result)
    return lookup


def _resolve_named_result(
    lookup: dict[tuple[str, str], list[ResultEvidence]],
    kind: str,
    number: str,
) -> ResultEvidence | None:
    matches = lookup.get((_normalized_kind(kind), number.casefold()), [])
    if len(matches) == 1:
        return matches[0]
    return None


def extract_proof_blocks(
    paper_id: str,
    spans: tuple[SourceSpanEvidence, ...],
    results: tuple[ResultEvidence, ...],
) -> tuple[ProofEvidence, ...]:
    """Extract proof blocks and associate them to local results when possible."""

    bibliography_index = _bibliography_start_index(spans)
    limit = len(spans) if bibliography_index is None else bibliography_index
    lookup = _result_lookup(results)
    result_by_span = {result.span_indices[0]: result for result in results}
    already_associated: set[str] = set()
    proofs: list[ProofEvidence] = []

    for span_index, span in enumerate(spans[:limit]):
        text = _normalized_text(span.text)
        match = PROOF_RE.match(text)
        if match is None:
            continue

        result_id: str | None = None
        association_basis = "unresolved"
        association_confidence = 0.0
        proof_id = f"{paper_id}::proof:{len(proofs) + 1}"

        if match.group("kind") and match.group("number"):
            result = _resolve_named_result(
                lookup,
                match.group("kind"),
                match.group("number"),
            )
            if result is not None:
                result_id = result.result_id
                association_basis = "proof_heading_names_result"
                association_confidence = 0.95
        else:
            for preceding_index in range(span_index - 1, -1, -1):
                result = result_by_span.get(preceding_index)
                if result is not None:
                    if result.result_id not in already_associated:
                        result_id = result.result_id
                        association_basis = "immediately_follows_result"
                        association_confidence = 0.75
                    break

        if result_id is not None:
            already_associated.add(result_id)

        proofs.append(
            ProofEvidence(
                proof_id=proof_id,
                paper_id=paper_id,
                result_id=result_id,
                text=text,
                span_indices=(span_index,),
                association_basis=association_basis,
                association_confidence=association_confidence,
                method="pdf_proof_heading",
                confidence=0.85,
            )
        )

    return tuple(proofs)


def _split_arxiv_version(arxiv_id: str) -> tuple[str, str | None]:
    match = _ARXIV_VERSION_RE.match(arxiv_id)
    if match is None:
        return arxiv_id, None
    return match.group("base"), match.group("version")


def _extract_arxiv_parts(text: str) -> tuple[str | None, str | None]:
    for match in _ARXIV_RE.finditer(text):
        try:
            normalized = normalize_arxiv_id(match.group("id"))
        except InvalidArxivIdError:
            continue
        return _split_arxiv_version(normalized)
    return None, None


def _strip_trailing_punctuation(value: str) -> str:
    return value.rstrip(".,;)")


def extract_bibliography_entries(
    paper_id: str,
    spans: tuple[SourceSpanEvidence, ...],
) -> tuple[BibliographyEntryEvidence, ...]:
    """Extract numeric bibliography entries after a bibliography heading."""

    bibliography_index = _bibliography_start_index(spans)
    if bibliography_index is None:
        return ()

    entries: list[BibliographyEntryEvidence] = []
    for span in spans[bibliography_index + 1 :]:
        text = _normalized_text(span.text)
        match = _BIBLIOGRAPHY_ENTRY_RE.match(text)
        if match is None:
            continue

        label = match.group("label")
        arxiv_id, arxiv_version = _extract_arxiv_parts(text)
        doi_match = _DOI_RE.search(text)
        url_match = _URL_RE.search(text)

        entries.append(
            BibliographyEntryEvidence(
                entry_id=f"{paper_id}::bib:{slug_fragment(label)}",
                paper_id=paper_id,
                raw_label=label,
                raw_text=text,
                entry_type="numeric",
                title=None,
                authors=(),
                year=None,
                arxiv_id=arxiv_id,
                arxiv_version=arxiv_version,
                doi=_strip_trailing_punctuation(doi_match.group("doi"))
                if doi_match is not None
                else None,
                url=_strip_trailing_punctuation(url_match.group(0))
                if url_match is not None
                else None,
                method="pdf_bibliography_regex",
                confidence=0.8,
            )
        )

    return tuple(entries)


def extract_local_result_mentions(
    paper_id: str,
    proofs: tuple[ProofEvidence, ...],
    results: tuple[ResultEvidence, ...],
) -> tuple[LocalResultMentionEvidence, ...]:
    """Extract proof-local references to results in the same paper."""

    lookup = _result_lookup(results)
    mentions: list[LocalResultMentionEvidence] = []

    for proof in proofs:
        for match in _LOCAL_RESULT_MENTION_RE.finditer(proof.text):
            raw_text = match.group(0)
            kind = _normalized_kind(match.group("kind"))
            visible_number = match.group("number") or None
            matches = lookup.get((kind, visible_number.casefold()), []) if visible_number else []
            target_result_id = matches[0].result_id if len(matches) == 1 else None
            if len(matches) == 1:
                resolution_status = "resolved_unique"
            elif len(matches) > 1:
                resolution_status = "ambiguous"
            else:
                resolution_status = "unresolved"

            mentions.append(
                LocalResultMentionEvidence(
                    mention_id=f"{paper_id}::local-mention:{len(mentions) + 1}",
                    paper_id=paper_id,
                    proof_id=proof.proof_id,
                    raw_text=raw_text,
                    kind=kind,
                    visible_number=visible_number,
                    target_result_id=target_result_id,
                    resolution_status=resolution_status,
                    method="proof_local_result_regex",
                    confidence=0.8,
                )
            )

    return tuple(mentions)


def _bibliography_lookup(
    entries: tuple[BibliographyEntryEvidence, ...],
) -> dict[str, BibliographyEntryEvidence]:
    return {entry.raw_label.casefold(): entry for entry in entries}


def extract_citation_mentions(
    paper_id: str,
    proofs: tuple[ProofEvidence, ...],
    bibliography_entries: tuple[BibliographyEntryEvidence, ...],
) -> tuple[CitationMentionEvidence, ...]:
    """Extract bracket citation mentions from proof text."""

    lookup = _bibliography_lookup(bibliography_entries)
    mentions: list[CitationMentionEvidence] = []

    for proof in proofs:
        for match in _CITATION_RE.finditer(proof.text):
            raw_key = match.group("key").strip()
            entry = lookup.get(raw_key.casefold())
            mentions.append(
                CitationMentionEvidence(
                    mention_id=f"{paper_id}::citation-mention:{len(mentions) + 1}",
                    paper_id=paper_id,
                    proof_id=proof.proof_id,
                    raw_text=match.group(0),
                    raw_key=raw_key,
                    entry_id=entry.entry_id if entry is not None else None,
                    resolution_status="resolved_unique"
                    if entry is not None
                    else "unresolved",
                    method="proof_citation_regex",
                    confidence=0.85,
                )
            )

    return tuple(mentions)


def extract_external_result_mentions(
    paper_id: str,
    citation_mentions: tuple[CitationMentionEvidence, ...],
) -> tuple[ExternalResultMentionEvidence, ...]:
    """Extract cited external result references from citation mentions."""

    mentions: list[ExternalResultMentionEvidence] = []
    for citation in citation_mentions:
        match = _CITATION_RE.fullmatch(citation.raw_text)
        if match is None or not (match.group("kind") and match.group("number")):
            continue

        mentions.append(
            ExternalResultMentionEvidence(
                mention_id=f"{paper_id}::external-mention:{len(mentions) + 1}",
                paper_id=paper_id,
                proof_id=citation.proof_id,
                citation_mention_id=citation.mention_id,
                raw_text=citation.raw_text,
                external_kind=_normalized_kind(match.group("kind")),
                external_number=match.group("number") or None,
                entry_id=citation.entry_id,
                target_paper_id=None,
                resolution_status="resolved_bibliography_entry"
                if citation.entry_id is not None
                else "unresolved",
                method="external_result_regex",
                confidence=0.8,
            )
        )

    return tuple(mentions)


def build_pdf_evidence_document(
    paper_id: str,
    source_ref: str,
    spans: tuple[SourceSpanEvidence, ...],
    title: str | None = None,
    authors: tuple[str, ...] = (),
) -> EvidenceDocument:
    """Build a PDF evidence document from already extracted source spans."""

    results = extract_result_blocks(paper_id, spans)
    proofs = extract_proof_blocks(paper_id, spans, results)
    bibliography_entries = extract_bibliography_entries(paper_id, spans)
    local_result_mentions = extract_local_result_mentions(paper_id, proofs, results)
    citation_mentions = extract_citation_mentions(
        paper_id,
        proofs,
        bibliography_entries,
    )
    external_result_mentions = extract_external_result_mentions(
        paper_id,
        citation_mentions,
    )

    return EvidenceDocument(
        paper_id=paper_id,
        source_type="pdf",
        source_ref=source_ref,
        source_version=None,
        title=title,
        authors=authors,
        main_file=source_ref,
        spans=spans,
        results=results,
        proofs=proofs,
        bibliography_entries=bibliography_entries,
        local_result_mentions=local_result_mentions,
        citation_mentions=citation_mentions,
        external_result_mentions=external_result_mentions,
        edges=(),
        warnings=(),
    )
