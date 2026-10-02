from dataclasses import replace

from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace


def span(index, text, paper_id='local:paper-a'):
    return SourceSpanEvidence(paper_id=paper_id, source_type='pdf', source_ref='paper.pdf',
        page=1, block_index=index, start_offset=0, end_offset=len(text), bbox=None,
        text=text, method='pdf_text_block', confidence=1.0)


def import_blocks(tmp_path, texts):
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    workspace.import_evidence_document(build_pdf_evidence_document(
        'local:correspondence', 'paper.pdf', tuple(span(i, text, 'local:correspondence')
                                                for i, text in enumerate(texts))))
    return workspace


def rid(number, kind='theorem'):
    return f'local:correspondence::pdf:{kind}:{number}'


def test_discussion_is_not_a_second_declaration_and_correspondence_becomes_unique(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.4 (= Corollary 3.4). Formal assertion.',
        'Theorem 1.4 also supplies an answer to a question.',
        'Corollary 3.4. Detailed assertion.', 'Proof. Direct.',
        'Corollary 3.4 follows from a preceding result.',
    ])
    try:
        assert len(workspace.list_results()) == 2
        entry = workspace.get_result_proof(rid('1.4'))['proof_entry']
        assert entry['status'] == 'corresponding_proof'
        assert entry['proof_result_id'] == rid('3.4', 'corollary')
    finally:
        workspace.close()


def test_genuine_repeated_formal_numbers_remain_separate_and_ambiguous(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1 (= Theorem 3.1). Introductory assertion.',
        'Theorem 3.1. First assertion.', 'Proof. Direct.',
        'Theorem 3.1. Second assertion.', 'Proof. Direct.',
    ])
    try:
        assert len(workspace.list_results()) == 3
        assert workspace.get_result_proof(rid('1.1'))['proof_entry']['status'] == 'ambiguous_correspondence'
    finally:
        workspace.close()


def test_isolated_heading_retains_statement_on_next_page_without_consuming_proof():
    spans = (
        span(0, 'Theorem 2.1.'),
        replace(span(1, '2'), page=2, block_index=0),
        replace(span(2, 'Let x be positive. Then x squared is positive.'), page=2, block_index=1),
        replace(span(3, 'Proof. Direct.'), page=2, block_index=2),
    )
    document = build_pdf_evidence_document('local:paper-a', 'paper.pdf', spans)
    result = document.results[0]
    assert result.span_indices == (0, 2)
    assert 'Let x be positive' in result.statement
    assert 'Proof.' not in result.statement
    assert document.proofs[0].result_id == result.result_id


def test_line_separated_formal_heading_without_period_is_retained():
    document = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Theorem 2.1\nLet x be positive.'),
    ))
    assert len(document.results) == 1
