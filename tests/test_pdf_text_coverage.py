from dataclasses import replace

from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace


def span(index, text):
    return SourceSpanEvidence('local:coverage', 'pdf', 'paper.pdf', 2, index,
                              0, len(text), None, text, 'pdf_text_block', 1.0)


def test_split_fraction_statement_retains_denominator_conclusion_and_locations(tmp_path):
    document = build_pdf_evidence_document('local:coverage', 'paper.pdf', (
        span(0, 'Theorem 1.1. For any 0 < epsilon < 1'),
        span(1, '5 there exists a map such that either'),
        span(2, '(1) the target is nef; or (2) a fibration exists.'),
        span(3, 'We also discuss another question.'),
        span(4, 'Theorem 1.2. Another assertion.'),
    ))
    result = document.results[0]
    assert '5 there exists' in result.statement
    assert 'a fibration exists' in result.statement
    assert 'We also discuss' not in result.statement
    assert result.span_indices == (0, 1, 2)
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        workspace.import_evidence_document(document)
        stored = workspace.get_result(result.result_id)
        assert stored['statement_complete'] is False
        assert stored['text_coverage']['status'] == 'unverified'
        assert stored['text_coverage']['captured_span_count'] == 3
        assert stored['text_coverage']['continuation_source']['arguments']['result_id'] == result.result_id
        assert workspace.list_results()[0]['statement_complete'] is False
        assert workspace.get_evidence(result.result_id)['metadata']['text_coverage'] == stored['text_coverage']
        candidate = workspace.get_paper_map('local:coverage')['main_result_candidates'][0]
        assert candidate['statement_complete'] is False
        assert 'PDF Text Coverage' in workspace.export_paper_reading_report('local:coverage')['markdown']
    finally:
        workspace.close()


def test_period_after_assumptions_does_not_discard_explicit_then_conclusion():
    document = build_pdf_evidence_document('local:coverage', 'paper.pdf', (
        span(0, 'Theorem 3.1. Suppose the surface is smooth.'),
        span(1, 'Then we may run a sequence. The following properties hold:'),
        span(2, '(1) the target is smooth; (2) the divisor is nef.'),
        span(3, 'Proof. First argument.'),
    ))
    assert document.results[0].span_indices == (0, 1, 2)
    assert 'Proof.' not in document.results[0].statement


def test_pdf_proof_is_explicitly_partial_and_adjacent_context_is_not_a_dependency(tmp_path):
    document = build_pdf_evidence_document('local:coverage', 'paper.pdf', (
        span(0, 'Theorem 3.1. Assertion.'), span(1, 'Proof. First argument.'),
        span(2, 'The argument continues by Lemma 9.9.'),
        span(3, 'Theorem 4.1. Another assertion.'),
    ))
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        workspace.import_evidence_document(document)
        result_id = document.results[0].result_id
        proof = workspace.get_result_proof(result_id)
        assert proof['known']['proof']['proof_complete'] is False
        coverage = proof['known']['proof']['text_coverage']
        assert coverage['status'] == 'unverified'
        assert coverage['adjacent_after'][0]['block_index'] == 2
        assert coverage['adjacent_context_is_proof_evidence'] is False
        assert any('PDF' in warning and 'incomplete' in warning for warning in proof['warnings'])
        deps = workspace.get_proof_dependencies(result_id)
        assert deps['proof_coverage'] == coverage
        assert deps['unresolved']['local_result_mentions'] == []
        assert workspace.export_result_reading_context(result_id)['proof']['known']['proof']['proof_complete'] is False
        assert workspace.export_reading_bundle('local:coverage')['proofs'][0]['proof_complete'] is False
    finally:
        workspace.close()


def test_continuation_is_bounded_and_does_not_join_across_a_new_heading():
    spans = (span(0, 'Theorem 1.1. Let x be'),) + tuple(span(i, 'and another condition') for i in range(1, 15))
    document = build_pdf_evidence_document('local:coverage', 'paper.pdf', spans)
    assert len(document.results[0].span_indices) <= 8
    assert len(document.results[0].span_indices) > 1
    cross_page = build_pdf_evidence_document('local:coverage', 'paper.pdf', (
        span(0, 'Theorem 2.1.'),
        replace(span(1, '3'), page=3, block_index=0),
        replace(span(2, 'Let x be positive.'), page=3, block_index=1),
        replace(span(3, 'Proof. Direct.'), page=3, block_index=2),
    ))
    assert cross_page.results[0].span_indices == (0, 2)
