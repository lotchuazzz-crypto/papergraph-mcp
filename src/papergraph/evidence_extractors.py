"""Deterministic evidence extraction over PDF text spans."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace

from papergraph.arxiv import InvalidArxivIdError, normalize_arxiv_id
from papergraph.author_correspondence import declared_target, RELATION
from papergraph.evidence import (
    BibliographyEntryEvidence,
    CitationMentionEvidence,
    EvidenceDocument,
    EvidenceEdge,
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
    r"^Proof\b(?:\s+of\s+(?:(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim)\s+)?"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z]))(?![\w.]*\w))?\.?\s*(?P<body>.*)$",
    re.I,
)


@dataclass(frozen=True)
class _PDFProofHeading:
    body_start: int
    unnamed: bool = False
    kind: str | None = None
    number: str | None = None


_SINGLE_PROOF_GOAL_RE = re.compile(
    r"(?:(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim)\s+)?"
    r"(?P<number>[A-Za-z]?\d+(?:\.\d+)*|(?-i:[A-Z]))", re.I)


def _named_heading_boundary(line: str, start: int) -> tuple[int, int, str] | None:
    """Find top-level punctuation, retaining a checkable unannotated goal.

    Parentheses, brackets, braces and quotes are heading regions until closed;
    their punctuation cannot introduce body evidence. Mismatches, unfinished
    structures and unsupported quote syntax have no reliable body boundary.
    The caller also checks the remaining goal grammar, so an abbreviation in
    unsupported top-level text cannot certify a boundary merely by ending in a
    period. No vocabulary of annotation abbreviations is needed.
    """
    pairs = {'(': ')', '[': ']', '{': '}', '（': '）', '【': '】'}
    quotes = {'"': '"', "'": "'", '“': '”', '‘': '’', '«': '»', '‹': '›'}
    stack: list[str] = []
    plain: list[str] = []
    quote: str | None = None
    escaped = False
    for index in range(start, len(line)):
        char = line[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                stack.pop()
                quote = None
            continue
        # An apostrophe inside a word is not an opening quotation mark.
        apostrophe = (char in {"'", '’'} and index > start and index + 1 < len(line)
                      and line[index - 1].isalnum() and line[index + 1].isalnum())
        if char in quotes and not apostrophe:
            if index > start and line[index - 1] == '\\':
                return None
            if not stack:
                plain.append(' ')
            quote = quotes[char]
            stack.append(quote)
        elif char in pairs:
            if not stack:
                plain.append(' ')
            stack.append(pairs[char])
        elif char in pairs.values() or (char in quotes.values() and not apostrophe):
            if not stack or stack[-1] != char:
                return None
            stack.pop()
            if not stack:
                plain.append(' ')
        elif char == '`':
            return None
        elif not stack:
            if char == ':' or (char == '.' and (index + 1 == len(line)
                                                or line[index + 1].isspace())):
                return index, index + 1, ''.join(plain)
            plain.append(char)
    if stack:
        return None
    return len(line), len(line), ''.join(plain)


def _pdf_proof_heading(line: str) -> _PDFProofHeading | None:
    """Parse the entire heading, never a first-goal prefix of a goal list.

    The same boundary controls ownership and every proof-body mention extractor.
    Unsupported or compound goal syntax stays visible but cannot acquire an
    owner by proximity. A decimal point is not a heading/body delimiter.
    """
    prefix = re.match(r"^Proof\b", line, re.I)
    if prefix is None:
        return None
    tail = line[prefix.end():]
    named = re.match(r"\s+of\b\s*", tail, re.I)
    if named is not None:
        start = prefix.end() + named.end()
        boundary = _named_heading_boundary(line, start)
        if boundary is None:
            return _PDFProofHeading(len(line))
        stop, body_start, plain_goal = boundary
        if _SINGLE_PROOF_GOAL_RE.fullmatch(plain_goal.strip()) is None:
            return _PDFProofHeading(len(line))
        goal = _SINGLE_PROOF_GOAL_RE.fullmatch(line[start:stop].strip())
        # Alternatives after an apparent delimiter are still ambiguous goals.
        alternative = re.match(r"\s*(?:(?:and|or)\b|[/&]|\(\s*(?:and|or)\b)",
                               line[body_start:], re.I)
        if goal is not None and alternative is None:
            return _PDFProofHeading(body_start, kind=goal.group('kind'),
                                    number=goal.group('number'))
        return _PDFProofHeading(body_start if alternative is None else len(line))
    generic = re.match(r"\s*[.:]\s*", tail)
    if generic is not None:
        return _PDFProofHeading(prefix.end() + generic.end(), unnamed=True)
    if not tail.strip():
        return _PDFProofHeading(prefix.end(), unnamed=True)
    return _PDFProofHeading(len(line))


def _proof_body(proof: ProofEvidence) -> str:
    if not proof.method.startswith('pdf_proof_first_line_'):
        return proof.text
    heading = _pdf_proof_heading(proof.text)
    # Existing extractor callers may supply body-only ProofEvidence. There is
    # no heading role to exclude in that case; retain their original evidence.
    return proof.text[heading.body_start:] if heading is not None else proof.text

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
    r"(?P<number>(?:[A-Za-z]?\d+(?:\.\d+)*|(?-i:[A-Z])))\b",
    re.I,
)
_CITATION_RE = re.compile(
    r"\[(?P<key>[^\],]+)(?:,\s*(?P<kind>Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Example|Remark)\s+"
    r"(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?))?\]",
    re.I,
)
_LATEX_REF_RE = re.compile(
    r"\\(?:ref|eqref|autoref|cref|Cref)\{(?P<labels>[^}]+)\}"
)
_ROADMAP_TRIGGER_RE = re.compile(
    r"\b(?:"
    r"it\s+remains\s+to\s+prove|"
    r"we\s+(?:first\s+|next\s+|now\s+|shall\s+)?prove|"
    r"the\s+proof\s+(?:is\s+)?(?:divided\s+into|reduces\s+to)|"
    r"it\s+suffices\s+to\s+prove"
    r")\b",
    re.I,
)
_ROADMAP_RESULT_GROUP_RE = re.compile(
    r"\b(?P<kind>"
    r"Theorems?|Lemmas?|Propositions?|Corollaries?|Claims?"
    r")\s+"
    r"(?P<numbers>"
    r"[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])"
    r"(?:\s*(?:,|and)\s*[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z]))*"
    r")\b",
    re.I,
)
_ROADMAP_NUMBER_RE = re.compile(r"[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])")
_ROADMAP_WINDOW_BOUNDARY_RE = re.compile(r"(?<!\d)[.;]|[.;](?!\d)")


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
        if match is None or not _formal_result_heading(span.text, text, match):
            continue

        result_span_indices = _statement_span_indices(spans, span_index, limit)
        text = '\n'.join(_normalized_text(spans[i].text) for i in result_span_indices)

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
                span_indices=result_span_indices,
                method="pdf_heading_regex",
                confidence=0.85,
            )
        )

    return tuple(results)


def _formal_result_heading(raw_text, normalized, match):
    """Require an explicit heading boundary, never deduplicate by numbering."""
    remainder = normalized[match.end('number'):].lstrip()
    if remainder.startswith(('.', ':', '(')):
        return True
    first_line = _normalized_text(raw_text.splitlines()[0])
    return first_line == normalized[:match.end('number')]


def _statement_span_indices(spans, start, limit):
    """Collect a small lexical/layout continuation window, never certify entirety."""
    included = [start]
    heading = _normalized_text(spans[start].text)
    match = RESULT_RE.match(heading)
    isolated = bool(re.fullmatch(r'\s*(?:\([^)]*\)\s*)?[.:]?\s*', heading[match.end('number'):]))
    for following in range(start + 1, min(limit, start + 8)):
        candidate, previous = spans[following], spans[included[-1]]
        next_text = _normalized_text(candidate.text)
        if candidate.page is not None and spans[start].page is not None and candidate.page > spans[start].page + 1:
            break
        # Do not discard a mathematical denominator merely because it is numeric.
        if candidate.block_index == 0 and (next_text.isupper() or next_text == str(candidate.page)):
            continue
        if (PROOF_RE.match(next_text) or RESULT_RE.match(next_text)
                or next_text.casefold() in ('references', 'bibliography')
                or re.match(r'^\d+(?:\.\d+)*\.?\s+[A-Z]', next_text)):
            break
        if previous.page == candidate.page and previous.bbox and candidate.bbox:
            if candidate.bbox[1] - previous.bbox[3] > 36 or candidate.bbox[0] > previous.bbox[2] or candidate.bbox[2] < previous.bbox[0]:
                break
        explicit_continuation = re.match(r'^(?:Then\b|Moreover\b|Furthermore\b|In particular\b|where\b|such that\b|\([0-9]+\))', next_text)
        if not isolated and _normalized_text(previous.text).endswith(('.', '!', '?')) and not explicit_continuation:
            break
        if sum(len(spans[i].text) for i in included) + len(candidate.text) > 12000:
            break
        included.append(following)
        isolated = False
    return tuple(included)


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
        line = span.text.lstrip().splitlines()[0] if span.text.strip() else ''
        heading = _pdf_proof_heading(line)
        if heading is None:
            continue

        result_id: str | None = None
        association_basis = "unresolved"
        association_confidence = 0.0
        proof_id = f"{paper_id}::proof:{len(proofs) + 1}"

        if heading.number:
            if heading.kind:
                result = _resolve_named_result(lookup, heading.kind, heading.number)
            else:
                matches = [r for r in results if r.visible_number is not None
                           and r.visible_number.casefold() == heading.number.casefold()]
                result = matches[0] if len(matches) == 1 else None
            if result is not None:
                result_id = result.result_id
                association_basis = "proof_heading_names_result"
                association_confidence = 0.95
        elif heading.unnamed:
            for preceding_index in range(span_index - 1, -1, -1):
                result = result_by_span.get(preceding_index)
                if result is not None:
                    if (result.result_id not in already_associated
                            and max(result.span_indices) + 1 == span_index):
                        result_id = result.result_id
                        association_basis = "immediately_follows_result"
                        association_confidence = 0.75
                    break

        if result_id is not None:
            already_associated.add(result_id)

        proof_text, _start, _end, terminated = _proof_first_line_excerpt(span)
        proof_indices = (span_index,)
        proofs.append(
            ProofEvidence(
                proof_id=proof_id,
                paper_id=paper_id,
                result_id=result_id,
                text=proof_text,
                span_indices=proof_indices,
                association_basis=association_basis,
                association_confidence=association_confidence,
                method="pdf_proof_first_line_explicit_end" if terminated else "pdf_proof_first_line_excerpt",
                confidence=0.85,
            )
        )

    return tuple(proofs)



# A PDF text block is a container, not a proof region. Never infer ownership of
# later lines or blocks from a later QED, title vocabulary, font size or budget.
# Retain only the physical line carrying the explicit proof heading. Ambiguous
# marker mentions stop this excerpt without claiming a closed proof.
_PROOF_TERMINATOR_RE = re.compile(r'(?<!\w)(?:Q\.?E\.?D\.?|[\u25a1\u220e\u25a0])(?!\w)', re.I)
_ANOTHER_PROOF_RE = re.compile(r'\bProof(?:[.:]|\s+of\b)', re.I)


def _proof_first_line_excerpt(span):
    first = re.search(r'\S', span.text)
    if first is None:
        return '', 0, 0, False
    start = first.start()
    newline = re.search(r'[\r\n]', span.text[start:])
    end = start + newline.start() if newline else len(span.text)
    line = span.text[start:end]
    heading = _pdf_proof_heading(line)
    if heading is None:
        return '', start, start, False
    # A second explicit proof heading on this same line is not a continuation.
    another = _ANOTHER_PROOF_RE.search(line, heading.body_start)
    boundary = another.start() if another else len(line)
    if len(line) > 12000:
        boundary = heading.body_start
    marker = _PROOF_TERMINATOR_RE.search(line, 0, boundary)
    terminated = False
    if marker:
        before, after = line[:marker.start()].rstrip(), line[marker.end():boundary].lstrip()
        token = marker.group()
        # Standalone or sentence-final markers are explicit. A word such as
        # "QED is ...", a quotation or an abbreviation mention is ambiguous;
        # do not skip it and borrow a later marker. In either case nothing
        # after this first marker can become proof evidence.
        terminated = (not before or before.endswith(('.', '!', '?'))) and (
            not after or (token.endswith('.') and after[0].isupper()))
        boundary = marker.end() if terminated else marker.start()
    end = start + boundary
    while end > start and span.text[end - 1].isspace():
        end -= 1
    return _normalized_text(span.text[start:end]), start, end, terminated


def _materialize_pdf_proof_fragments(spans, proofs):
    """Persist exact block-relative ranges without altering the raw source."""
    from papergraph.source_navigation import block_locator

    fragments, linked = [], []
    for proof in proofs:
        index = proof.span_indices[0]
        original = spans[index]
        text, start, end, _terminated = _proof_first_line_excerpt(original)
        if text != proof.text:
            raise ValueError('PDF proof excerpt does not match its source range')
        if start == 0 and end == len(original.text):
            linked.append(proof)
            continue
        fragment = replace(original, text=original.text[start:end],
                           start_offset=(original.start_offset or 0) + start,
                           end_offset=(original.start_offset or 0) + end,
                           method='pdf_proof_fragment', span_id=None)
        locator = block_locator(asdict(fragment)).replace('source-block:', 'source-fragment:', 1)
        fragment = replace(fragment, span_id=locator)
        linked.append(replace(proof, span_indices=(len(spans) + len(fragments),)))
        fragments.append(fragment)
    return tuple(fragments), tuple(linked)


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
    """Extract bracket-labelled entries without mixing grouped PDF blocks."""

    entries: list[BibliographyEntryEvidence] = []
    for span in _bibliography_entry_spans(spans):
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
                entry_type="numeric" if label.isdecimal() else "keyed",
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


def _bibliography_entry_spans(spans):
    """Split at source line labels; preserve exact block-relative offsets."""
    bibliography_index = _bibliography_start_index(spans)
    if bibliography_index is None:
        return ()
    entries = []
    for span in spans[bibliography_index + 1:]:
        markers = list(re.finditer(r"(?m)^\s*\[[^\]\n]+\]\s*", span.text))
        for index, marker in enumerate(markers):
            start = marker.start()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(span.text)
            entries.append(replace(
                span, text=span.text[start:end],
                start_offset=(span.start_offset or 0) + start,
                end_offset=(span.start_offset or 0) + end,
            ))
    return tuple(entries)


def extract_local_result_mentions(
    paper_id: str,
    proofs: tuple[ProofEvidence, ...],
    results: tuple[ResultEvidence, ...],
) -> tuple[LocalResultMentionEvidence, ...]:
    """Extract proof-local references to results in the same paper."""

    lookup = _result_lookup(results)
    label_lookup: dict[str, list[ResultEvidence]] = {}
    for result in results:
        if result.label is not None:
            label_lookup.setdefault(result.label, []).append(result)
    mentions: list[LocalResultMentionEvidence] = []

    for proof in proofs:
        proof = replace(proof, text=_proof_body(proof))
        excluded_ranges = _local_mention_excluded_ranges(proof.text)
        for match in _LATEX_REF_RE.finditer(proof.text):
            raw_text = match.group(0)
            labels = [
                label.strip()
                for label in match.group("labels").split(",")
                if label.strip()
            ]
            for label in labels:
                matches = label_lookup.get(label, [])
                result = matches[0] if len(matches) == 1 else None
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
                        kind=result.normalized_kind if result is not None else "label",
                        visible_number=None,
                        target_result_id=result.result_id if result is not None else None,
                        resolution_status=resolution_status,
                        method="proof_latex_ref",
                        confidence=0.9,
                    )
                )
        for match in _LOCAL_RESULT_MENTION_RE.finditer(proof.text):
            if _overlaps_any_range(match.span(), excluded_ranges):
                continue

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

        mentions.extend(
            _extract_roadmap_result_mentions(
                paper_id,
                proof,
                lookup,
                len(mentions),
                {
                    mention.target_result_id
                    for mention in mentions
                    if mention.proof_id == proof.proof_id
                    and mention.target_result_id is not None
                    and mention.resolution_status == "resolved_unique"
                },
            )
        )

    return tuple(mentions)


def _extract_roadmap_result_mentions(
    paper_id: str,
    proof: ProofEvidence,
    lookup: dict[tuple[str, str], list[ResultEvidence]],
    start_index: int,
    resolved_targets_to_skip: set[str],
) -> tuple[LocalResultMentionEvidence, ...]:
    mentions: list[LocalResultMentionEvidence] = []
    for trigger_match in _ROADMAP_TRIGGER_RE.finditer(proof.text):
        window = _roadmap_window(proof.text, trigger_match.end())
        for group_match in _ROADMAP_RESULT_GROUP_RE.finditer(window):
            kind = _roadmap_normalized_kind(group_match.group("kind"))
            for number_match in _ROADMAP_NUMBER_RE.finditer(group_match.group("numbers")):
                visible_number = number_match.group(0)
                matches = lookup.get((kind, visible_number.casefold()), [])
                target_result_id = matches[0].result_id if len(matches) == 1 else None
                if len(matches) == 1:
                    resolution_status = "resolved_unique"
                elif len(matches) > 1:
                    resolution_status = "ambiguous"
                else:
                    resolution_status = "unresolved"
                if target_result_id in resolved_targets_to_skip:
                    continue

                raw_text = f"{_display_kind(kind)} {visible_number}"
                mentions.append(
                    LocalResultMentionEvidence(
                        mention_id=(
                            f"{paper_id}::local-mention:"
                            f"{start_index + len(mentions) + 1}"
                        ),
                        paper_id=paper_id,
                        proof_id=proof.proof_id,
                        raw_text=raw_text,
                        kind=kind,
                        visible_number=visible_number,
                        target_result_id=target_result_id,
                        resolution_status=resolution_status,
                        method="proof_roadmap_result_regex",
                        confidence=0.72,
                    )
                )
                if target_result_id is not None and resolution_status == "resolved_unique":
                    resolved_targets_to_skip.add(target_result_id)
    return tuple(mentions)


def _roadmap_window(text: str, start: int) -> str:
    suffix = text[start : start + 240]
    boundary = _ROADMAP_WINDOW_BOUNDARY_RE.search(suffix)
    if boundary is not None:
        return suffix[: boundary.start()]
    return suffix


def _roadmap_normalized_kind(raw_kind: str) -> str:
    lowered = raw_kind.casefold()
    if lowered.endswith("ies"):
        lowered = lowered[:-3] + "y"
    elif lowered.endswith("s"):
        lowered = lowered[:-1]
    return _normalized_kind(lowered)


def _local_mention_excluded_ranges(text: str) -> tuple[tuple[int, int], ...]:
    from papergraph.citations import _CITATION_RE as tex_citation_re
    ranges: list[tuple[int, int]] = [match.span() for match in _CITATION_RE.finditer(text)]
    ranges.extend(match.span() for match in tex_citation_re.finditer(text))
    ranges.extend(_roadmap_result_group_ranges(text))
    proof_match = PROOF_RE.match(text)
    if (
        proof_match is not None
        and proof_match.group("kind") is not None
        and proof_match.group("number") is not None
    ):
        ranges.append((proof_match.start("kind"), proof_match.end("number")))
    return tuple(ranges)


def _overlaps_any_range(
    target: tuple[int, int],
    ranges: tuple[tuple[int, int], ...],
) -> bool:
    start, end = target
    return any(start < range_end and range_start < end for range_start, range_end in ranges)


def _roadmap_result_group_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for trigger_match in _ROADMAP_TRIGGER_RE.finditer(text):
        window_start = trigger_match.end()
        window = _roadmap_window(text, window_start)
        for group_match in _ROADMAP_RESULT_GROUP_RE.finditer(window):
            ranges.append(
                (
                    window_start + group_match.start(),
                    window_start + group_match.end(),
                )
            )
    return tuple(ranges)


def _bibliography_lookup(
    entries: tuple[BibliographyEntryEvidence, ...],
) -> dict[str, list[BibliographyEntryEvidence]]:
    lookup = {}
    for entry in entries:
        lookup.setdefault(entry.raw_label.casefold(), []).append(entry)
    return lookup


def extract_citation_mentions(
    paper_id: str,
    proofs: tuple[ProofEvidence, ...],
    bibliography_entries: tuple[BibliographyEntryEvidence, ...],
) -> tuple[CitationMentionEvidence, ...]:
    """Extract explicit bracket/TeX citations, preserving repeated occurrences."""

    from papergraph.citations import _CITATION_RE as tex_citation_re
    from papergraph.loader import _is_commented

    lookup = _bibliography_lookup(bibliography_entries)
    mentions: list[CitationMentionEvidence] = []

    for proof in proofs:
        proof = replace(proof, text=_proof_body(proof))
        tex_matches = list(tex_citation_re.finditer(proof.text))
        matches = [(m, [k.strip() for k in m.group('keys').split(',') if k.strip()],
                    'proof_latex_citation') for m in tex_matches
                   if not _is_commented(proof.text, m.start())]
        matches.extend((m, [m.group('key').strip()], 'proof_citation_regex')
                       for m in _CITATION_RE.finditer(proof.text)
                       if not _overlaps_any_range(m.span(), tuple(t.span() for t in tex_matches)))
        for match, keys, method in sorted(matches, key=lambda item: item[0].start()):
            for raw_key in keys:
                entries = lookup.get(raw_key.casefold(), [])
                entry = entries[0] if len(entries) == 1 else None
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
                        else "ambiguous" if entries else "unresolved",
                        method=method,
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
        if citation.method == 'proof_latex_citation':
            from papergraph.citations import _CITATION_RE as tex_citation_re
            tex_match = tex_citation_re.fullmatch(citation.raw_text)
            locator = citation.raw_text[tex_match.end('command'):tex_match.start('keys') - 1]
            locator_matches = list(_LOCAL_RESULT_MENTION_RE.finditer(locator))
            match = locator_matches[0] if len(locator_matches) == 1 else None
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
    proof_fragments, proofs = _materialize_pdf_proof_fragments(spans, proofs)
    bibliography_entries = extract_bibliography_entries(paper_id, spans)
    # Bibliography entries can be uncited in extracted proof blocks. Keep their
    # actual PDF block locations so import validation does not require a citation
    # to establish traceability. Append copies to preserve all result/proof indices.
    bibliography_blocks = {
        _normalized_text(span.text): span
        for span in _bibliography_entry_spans(spans)
    }
    bibliography_spans = tuple(
        replace(bibliography_blocks[entry.raw_text], span_id=entry.entry_id,
                method="pdf_bibliography_block", confidence=entry.confidence)
        for entry in bibliography_entries
    )
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
    correspondence_edges = []
    lookup = _result_lookup(results)
    for result in results:
        target = declared_target(result.statement)
        matches = lookup.get(target, []) if target else []
        if len(matches) == 1:
            correspondence_edges.append(EvidenceEdge(
                edge_id=result.result_id + '::author-correspondence', paper_id=paper_id,
                source_id=result.result_id, target_id=matches[0].result_id,
                relation=RELATION, evidence_ids=(result.result_id,),
                method='pdf_explicit_author_declaration', confidence=0.95,
            ))

    return EvidenceDocument(
        paper_id=paper_id,
        source_type="pdf",
        source_ref=source_ref,
        source_version=None,
        title=title,
        authors=authors,
        main_file=source_ref,
        spans=(*spans, *proof_fragments, *bibliography_spans),
        results=results,
        proofs=proofs,
        bibliography_entries=bibliography_entries,
        local_result_mentions=local_result_mentions,
        citation_mentions=citation_mentions,
        external_result_mentions=external_result_mentions,
        edges=tuple(correspondence_edges),
        warnings=(),
    )
