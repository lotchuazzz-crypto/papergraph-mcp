from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document


def span(index: int, text: str) -> SourceSpanEvidence:
    return SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=1,
        block_index=index,
        start_offset=0,
        end_offset=len(text),
        bbox=None,
        text=text,
        method="pdf_text_block",
        confidence=1.0,
    )


def test_extracts_results_and_proofs_with_unique_local_resolution():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Lemma 1.2. Base estimate."),
            span(1, "Theorem 1.1. Main result."),
            span(2, "Proof. By Lemma 1.2, the claim follows."),
        ),
    )

    assert [result.local_id for result in document.results] == [
        "pdf:lemma:1.2",
        "pdf:theorem:1.1",
    ]
    theorem = document.results[1]
    proof = document.proofs[0]
    assert theorem.result_id == "local:paper-a::pdf:theorem:1.1"
    assert proof.result_id == theorem.result_id
    assert proof.association_basis == "immediately_follows_result"
    assert document.local_result_mentions[0].raw_text == "Lemma 1.2"
    assert (
        document.local_result_mentions[0].target_result_id
        == "local:paper-a::pdf:lemma:1.2"
    )
    assert document.local_result_mentions[0].resolution_status == "resolved_unique"


def test_extracts_explicit_proof_of_number_association():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Theorem 1.1. Main result."),
            span(1, "Lemma 1.2. Base estimate."),
            span(2, "Proof of Theorem 1.1. We use Lemma 1.2."),
        ),
    )

    proof = document.proofs[0]
    assert proof.result_id == "local:paper-a::pdf:theorem:1.1"
    assert proof.association_basis == "proof_heading_names_result"
    assert [mention.raw_text for mention in document.local_result_mentions] == [
        "Lemma 1.2"
    ]


def test_ambiguous_local_mentions_remain_visible():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Lemma 1.2. First."),
            span(1, "Lemma 1.2. Second."),
            span(2, "Theorem 1.3. Main."),
            span(3, "Proof. By Lemma 1.2."),
        ),
    )

    mention = document.local_result_mentions[0]
    assert mention.target_result_id is None
    assert mention.resolution_status == "ambiguous"


def test_extracts_numeric_bibliography_and_external_result_mentions():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Theorem 1.1. Main result."),
            span(1, "Proof. We apply [12, Theorem 3.5]."),
            span(2, "References"),
            span(
                3,
                "[12] A. Author. Cited paper. arXiv:2401.12345v2. "
                "doi:10.1000/example",
            ),
        ),
    )

    assert document.bibliography_entries[0].raw_label == "12"
    assert document.bibliography_entries[0].arxiv_id == "2401.12345"
    assert document.bibliography_entries[0].arxiv_version == "v2"
    assert document.bibliography_entries[0].doi == "10.1000/example"
    citation = document.citation_mentions[0]
    assert citation.raw_text == "[12, Theorem 3.5]"
    assert citation.entry_id == "local:paper-a::bib:12"
    external = document.external_result_mentions[0]
    assert external.external_kind == "theorem"
    assert external.external_number == "3.5"
    assert external.entry_id == "local:paper-a::bib:12"
    assert external.resolution_status == "resolved_bibliography_entry"


def test_cited_result_inside_brackets_is_not_local_result_mention():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Theorem 3.5. Local result with same number."),
            span(1, "Theorem 4.1. Main result."),
            span(2, "Proof. We apply [12, Theorem 3.5]."),
            span(3, "References"),
            span(4, "[12] A. Author. Cited paper."),
        ),
    )

    assert document.local_result_mentions == ()
    assert document.citation_mentions[0].raw_text == "[12, Theorem 3.5]"
    assert document.external_result_mentions[0].external_number == "3.5"
