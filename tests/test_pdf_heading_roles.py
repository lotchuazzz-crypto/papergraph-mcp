"""Owner goals and proof-body references have different roles."""
from contextlib import closing

import pytest

from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace
from tests.test_evidence_extractors import span


MULTI = [
    'Proof of Theorem 2.1 and Theorem 3.1.',
    'Proof of Theorem 2.1 or Theorem 3.1.',
    'Proof of Theorem 2.1/Theorem 3.1.',
    'Proof of Theorem 2.1/3.1.',
    'Proof of Theorem 2.1 (or Theorem 3.1).',
    'Proof of Theorem 2.1 (or 3.1).',
    'Proof of Theorem 2.1 (and Theorem 3.1).',
    'Proof of Theorem 2.1 and 3.1.',
    'Proof of Theorems 2.1 and 3.1.',
    'Proof of 2.1 and 3.1.',
    'Proof of Theorem 2.1, Theorem 3.1.',
    'Proof of Theorem 2.1; Theorem 3.1.',
    'Proof of Theorem 2.1 & Theorem 3.1.',
    'Proof (Theorem 2.1 or Theorem 3.1).',
]


def document(heading):
    return build_pdf_evidence_document('local:paper-a', 'paper.pdf', tuple(
        span(i, text) for i, text in enumerate([
            'Lemma 1.1. Base case.', 'Proof. Immediate. QED.',
            'Theorem 2.1. First goal.', 'Theorem 3.1. Second goal.',
            heading + ' Apply Lemma 1.1. QED.'])))


@pytest.mark.parametrize('heading', MULTI)
def test_multiple_or_unsupported_goals_never_choose_first_or_nearest(heading, tmp_path):
    doc = document(heading)
    proof = doc.proofs[-1]
    assert proof.result_id is None
    assert not any(m.raw_text.startswith('Theorem') for m in doc.local_result_mentions)
    assert heading in proof.text  # Full headed excerpt remains available.
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_evidence_document(doc)
        for number in ('2.1', '3.1'):
            rid = 'local:paper-a::pdf:theorem:' + number
            assert workspace.get_result_proof(rid)['unresolved']['proof'] == 'not_found'
            assert workspace.get_proof_dependencies(rid)['known']['resolved_local_results'] == []
            assert all(row['result_id'] != 'local:paper-a::pdf:lemma:1.1'
                       for row in workspace.get_result_reading_path(rid)['bottom_up'])


@pytest.mark.parametrize('heading', ['Proof of Theorem 2.1.', 'Proof of Theorem 2.1:', 'Proof of 2.1.'])
def test_single_complete_named_goal_keeps_body_evidence_only(heading):
    doc = document(heading)
    assert doc.proofs[-1].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert [m.raw_text for m in doc.local_result_mentions] == ['Lemma 1.1']


def test_real_body_reference_to_another_goal_is_retained():
    doc = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Theorem 2.1. Goal.'), span(1, 'Theorem 3.1. Prior result.'),
        span(2, 'Proof of Theorem 2.1. Apply Theorem 3.1. QED.')))
    assert doc.proofs[0].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert [m.raw_text for m in doc.local_result_mentions] == ['Theorem 3.1']


def test_parenthesized_body_is_not_a_heading_alternative():
    doc = document('Proof of Theorem 2.1. (Take the base case.)')
    assert doc.proofs[-1].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert [m.raw_text for m in doc.local_result_mentions] == ['Lemma 1.1']


def test_heading_citations_are_not_body_evidence():
    doc = document('Proof of Theorem 2.1 [9, Theorem 3.1].')
    assert doc.proofs[-1].result_id is None
    assert not doc.citation_mentions and not doc.external_result_mentions
    assert [m.raw_text for m in doc.local_result_mentions] == ['Lemma 1.1']


def test_actual_body_citations_remain_accessible():
    doc = document('Proof of Theorem 2.1. Apply [9, Theorem 3.1].')
    assert doc.proofs[-1].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert [m.raw_text for m in doc.citation_mentions] == ['[9, Theorem 3.1]']
    assert [m.raw_text for m in doc.external_result_mentions] == ['[9, Theorem 3.1]']


@pytest.mark.parametrize('entries', [1, 2])
@pytest.mark.parametrize('null_raw_ids', [False, True])
def test_raw_bibliography_has_only_original_blocks_but_entries_remain_accessible(tmp_path, entries, null_raw_ids):
    text = '\n'.join(f'[{i}] A. Author. Reference {i}.' for i in range(1, entries + 1))
    originals = (span(0, 'Theorem 2.1. Assertion.'), span(1, 'Proof. Direct. QED.'),
                 span(2, 'References'), span(3, text))
    doc = build_pdf_evidence_document('local:paper-a', 'paper.pdf', originals)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_evidence_document(doc)
        if null_raw_ids:
            workspace._connection.execute("UPDATE source_spans SET span_id=NULL WHERE method='pdf_text_block'")
        selector = workspace.get_source_slice(result_id=doc.results[0].result_id)['source_reading']
        rows = []
        while selector:
            page = workspace.read_source_blocks(**{**selector['arguments'], 'limit': 1})
            rows += page['blocks']
            selector = page['next']
        assert [row['text'] for row in rows] == [row.text for row in originals]
        assert len({row['span_id'] for row in rows}) == 4
        before = list(workspace._connection.iterdump())
        for entry in doc.bibliography_entries:
            assert workspace.get_evidence(entry.entry_id)['metadata']['raw_text'] == entry.raw_text
            source = workspace.get_source_slice(span_id=entry.entry_id, context=0)
            assert source['slices'][0]['text'] == text
            assert workspace.read_source_blocks(entry.entry_id, 1)['blocks'][0]['text'] == text
        assert list(workspace._connection.iterdump()) == before
        # Legacy content locators for null-ID derived rows also project back to
        # the container, rather than disappearing when derived rows are hidden.
        from papergraph.source_navigation import block_locator
        for entry in doc.bibliography_entries:
            workspace._connection.execute('UPDATE source_spans SET span_id=NULL WHERE span_id=?',
                                          (entry.entry_id,))
        from papergraph.workspace import _source_slice_record_from_row
        derived = workspace._connection.execute(
            "SELECT id,span_id,paper_id,source_type,source_ref,page,block_index,"
            "start_offset,end_offset,bbox_json,text,method,confidence FROM source_spans "
            "WHERE method='pdf_bibliography_block'").fetchall()
        before = list(workspace._connection.iterdump())
        for row in derived:
            locator = block_locator(_source_slice_record_from_row(row))
            assert workspace.get_source_slice(span_id=locator, context=0)['slices'][0]['text'] == text
            assert workspace.read_source_blocks(locator, 1)['blocks'][0]['text'] == text
        assert list(workspace._connection.iterdump()) == before
