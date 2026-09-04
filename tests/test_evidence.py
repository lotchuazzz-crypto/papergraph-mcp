import pytest

from papergraph.evidence import (
    BibliographyEntryEvidence,
    CitationMentionEvidence,
    EvidenceDocument,
    ExternalResultMentionEvidence,
    LocalResultMentionEvidence,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
    bounded_excerpt,
    confidence,
    evidence_pdf_result_local_id,
    evidence_result_id,
    slug_fragment,
    source_span_payload,
)


def test_confidence_accepts_numeric_range():
    assert confidence(0) == 0.0
    assert confidence(0.75) == 0.75
    assert confidence(1) == 1.0


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "1"])
def test_confidence_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="confidence"):
        confidence(value)


def test_bounded_excerpt_normalizes_whitespace_and_limits_text():
    text = "  A\n\t proof   with   spaces.  " + "x" * 300
    excerpt = bounded_excerpt(text, limit=30)
    assert excerpt == "A proof with spaces. xxxxxx..."
    assert len(excerpt) == 30


def test_slug_fragment_is_deterministic_and_lowercase():
    assert slug_fragment("Theorem 1.2 / Main Result") == "theorem-1.2-main-result"
    assert slug_fragment("   ") == "item"


def test_evidence_result_ids_reuse_global_theorem_id_shape():
    assert evidence_result_id("local:paper-a", "thm:main") == "local:paper-a::thm:main"
    assert evidence_pdf_result_local_id("Theorem", "1.2", 3) == "pdf:theorem:1.2"
    assert evidence_pdf_result_local_id("Remark", None, 4) == "pdf:remark:4"


def test_source_span_payload_preserves_pdf_location():
    span = SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=2,
        block_index=5,
        start_offset=10,
        end_offset=24,
        bbox=(1.0, 2.0, 3.0, 4.0),
        text="Lemma 2.1. Base.",
        method="pdf_text_block",
        confidence=1.0,
    )

    assert source_span_payload(span) == {
        "span_id": None,
        "paper_id": "local:paper-a",
        "source_type": "pdf",
        "source_ref": "paper.pdf",
        "page": 2,
        "block_index": 5,
        "start_offset": 10,
        "end_offset": 24,
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "excerpt": "Lemma 2.1. Base.",
        "method": "pdf_text_block",
        "confidence": 1.0,
    }


def test_evidence_document_groups_records():
    document = EvidenceDocument(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        source_version=None,
        title=None,
        authors=(),
        main_file="paper.pdf",
        spans=(SourceSpanEvidence(
            paper_id="local:paper-a",
            source_type="pdf",
            source_ref="paper.pdf",
            page=1,
            block_index=0,
            start_offset=0,
            end_offset=19,
            bbox=None,
            text="Theorem 1.1. Main.",
            method="pdf_text_block",
            confidence=1.0,
        ),),
        results=(ResultEvidence(
            result_id="local:paper-a::pdf:theorem:1.1",
            paper_id="local:paper-a",
            local_id="pdf:theorem:1.1",
            kind="theorem",
            raw_kind="Theorem",
            display_kind="Theorem",
            normalized_kind="theorem",
            label=None,
            visible_number="1.1",
            title=None,
            statement="Theorem 1.1. Main.",
            span_indices=(0,),
            method="pdf_heading_regex",
            confidence=0.9,
        ),),
        proofs=(ProofEvidence(
            proof_id="local:paper-a::proof:1",
            paper_id="local:paper-a",
            result_id="local:paper-a::pdf:theorem:1.1",
            text="Proof. By Lemma 1.2.",
            span_indices=(0,),
            association_basis="immediately_follows_result",
            association_confidence=0.75,
            method="pdf_proof_heading",
            confidence=0.85,
        ),),
        bibliography_entries=(BibliographyEntryEvidence(
            entry_id="local:paper-a::bib:12",
            paper_id="local:paper-a",
            raw_label="12",
            raw_text="[12] A. Author, A cited paper, arXiv:2401.12345.",
            entry_type="numeric",
            title=None,
            authors=(),
            year=None,
            arxiv_id="2401.12345",
            arxiv_version=None,
            doi=None,
            url=None,
            method="pdf_bibliography_regex",
            confidence=0.8,
        ),),
        local_result_mentions=(LocalResultMentionEvidence(
            mention_id="local:paper-a::local-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            raw_text="Lemma 1.2",
            kind="lemma",
            visible_number="1.2",
            target_result_id=None,
            resolution_status="unresolved",
            method="proof_local_result_regex",
            confidence=0.8,
        ),),
        citation_mentions=(CitationMentionEvidence(
            mention_id="local:paper-a::citation-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            raw_text="[12]",
            raw_key="12",
            entry_id="local:paper-a::bib:12",
            resolution_status="resolved_unique",
            method="proof_citation_regex",
            confidence=0.85,
        ),),
        external_result_mentions=(ExternalResultMentionEvidence(
            mention_id="local:paper-a::external-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            citation_mention_id="local:paper-a::citation-mention:1",
            raw_text="[12, Theorem 3.5]",
            external_kind="theorem",
            external_number="3.5",
            entry_id="local:paper-a::bib:12",
            target_paper_id=None,
            resolution_status="resolved_bibliography_entry",
            method="external_result_regex",
            confidence=0.8,
        ),),
        edges=(),
        warnings=("empty proof dependencies are not evidence of no dependencies",),
    )

    assert document.paper_id == "local:paper-a"
    assert document.results[0].span_indices == (0,)
    assert document.warnings == ("empty proof dependencies are not evidence of no dependencies",)
