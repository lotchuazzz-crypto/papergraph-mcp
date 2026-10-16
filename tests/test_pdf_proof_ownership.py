"""Default PDF proof ownership is a first-line excerpt, never a raw-block join."""
from contextlib import closing

import pymupdf
import pytest

from papergraph.workspace import Workspace


CASES = [
    ['Proof. The theorem follows. QED.\nUnrelated discussion uses Lemma 1.1.'],
    ['Proof. The theorem follows. QED. Unrelated discussion uses Lemma 1.1.'],
    ['Proof. We begin the argument.', 'The theorem follows. QED.\nUnrelated discussion uses Lemma 1.1.',
     'Independent calculation ends. QED.'],
    ['Proof. The theorem follows. QED.\nUnrelated discussion uses Lemma 1.1. QED.'],
    ['Proof. The theorem follows. QED.', 'Unrelated discussion uses Lemma 1.1.'],
    ['Proof. The theorem follows. QED.\nB.1 Other discussion\nApply Lemma 1.1. QED.'],
    ['Proof. We begin.\n(7.2.4). auxiliary material\nApply Lemma 1.1. QED.'],
    ['Proof. We begin.', '(7.2.4). auxiliary material', 'Apply Lemma 1.1. QED.'],
    ['Proof. We begin.\nD auxiliary material\nApply Lemma 1.1. QED.'],
    ['Proof. We begin.', 'a completely unfamiliar title', 'Apply Lemma 1.1. QED.'],
    ['Proof. We begin.\na completely unfamiliar title\nApply Lemma 1.1. QED.'],
    ['Proof. We begin.', 'Apply Lemma 1.1. QED.'],
    ['Proof. The theorem follows. QED.\nProof. Apply Lemma 1.1. QED.'],
    ['Proof. We begin. Proof. Apply Lemma 1.1. QED.'],
    ['Proof. The word QED is discussed by Lemma 1.1. QED.'],
    ['Proof. We quote "QED" and then discuss Lemma 1.1. QED.'],
    ['Proof. We begin.', 'We mention the abbreviation Q.E.D. in Lemma 1.1.', 'Done. QED.'],
]


def write_pdf(path, blocks):
    with pymupdf.open() as document:
        page = document.new_page()
        for index, text in enumerate(['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
                                      'Theorem 2.1. Main assertion.', *blocks]):
            page.insert_text((72, 60 + index * 85), text, fontsize=11)
        document.save(path)


@pytest.mark.parametrize('blocks', CASES)
def test_later_text_never_becomes_proof_evidence_but_remains_raw(tmp_path, blocks):
    path = tmp_path / 'ownership.pdf'
    write_pdf(path, blocks)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:ownership')
        rid = 'local:ownership::pdf:theorem:2.1'
        proof = workspace.get_result_proof(rid)['known']['proof']
        assert 'Lemma 1.1' not in proof['text']
        assert workspace.get_proof_dependencies(rid)['known']['resolved_local_results'] == []
        reading = workspace.get_result_reading_path(rid)
        assert all(row['result_id'] != 'local:ownership::pdf:lemma:1.1' for row in reading['bottom_up'])
        handle = workspace.get_source_slice(proof_id=proof['proof_id'])['source_reading']
        raw = []
        while handle:
            page = workspace.read_source_blocks(**{**handle['arguments'], 'limit': 2})
            assert page['proof_ownership'] == 'not_asserted'
            raw.extend(page['blocks'])
            handle = page['next']
        assert any('Lemma 1.1' in block['text'] for block in raw)
        assert len({block['span_id'] for block in raw}) == len(raw)


@pytest.mark.parametrize('terminator', ['QED.', 'Q.E.D.', 'QED'])
def test_explicit_short_first_line_retains_its_dependency_and_exact_fragment_offsets(tmp_path, terminator):
    path = tmp_path / 'short.pdf'
    line = 'Proof. Apply Lemma 1.1 and Lemma 9.9. ' + terminator
    write_pdf(path, [line + '\nAFTER_WITNESS. Unknown discussion.'])
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:short')
        rid = 'local:short::pdf:theorem:2.1'
        proof = workspace.get_result_proof(rid)['known']['proof']
        assert proof['text'] == line
        assert proof['method'] == 'pdf_proof_first_line_explicit_end'
        assert proof['text_coverage']['automatic_ownership_policy'] == 'heading_line_only_no_automatic_continuation'
        assert len(proof['spans']) == 1
        fragment = proof['spans'][0]
        assert fragment['end_offset'] - fragment['start_offset'] == len(line)
        source = workspace.get_source_slice(proof_id=proof['proof_id'])
        page = workspace.read_source_blocks(**source['source_reading']['arguments'])
        raw = page['blocks'][0]
        assert raw['text'][fragment['start_offset']:fragment['end_offset']] == line
        assert 'AFTER_WITNESS' in raw['text']
        assert [row['visible_number'] for row in workspace.get_proof_dependencies(rid)['known']['resolved_local_results']] == ['1.1']
        plan = workspace.plan_external_imports_for_result(rid)
        assert [row['raw_text'] for row in plan['unresolved_local_mentions']] == ['Lemma 9.9']
        assert plan['blocked'] == []
        assert plan['unresolved_local_mentions'][0]['spans']
        assert workspace.get_evidence(proof['proof_id'])['spans'] == proof['spans']
        # Fragment IDs also locate the containing raw block, not a duplicate row.
        assert workspace.read_source_blocks(fragment['span_id'])['blocks'][0]['span_id'] == raw['span_id']


def test_oversized_heading_line_does_not_create_arbitrary_late_edges():
    from tests.test_evidence_extractors import span
    from papergraph.evidence_extractors import build_pdf_evidence_document

    text = 'Proof. ' + 'We continue. ' * 1000 + 'Apply Lemma 1.1. QED.'
    document = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Theorem 2.1. Main assertion.'), span(1, text)))
    assert document.proofs[0].text == 'Proof.'
    assert document.local_result_mentions == ()
    assert document.spans[1].text == text


@pytest.mark.parametrize('word', ['Proofreading', 'Proofless', 'Proofs'])
def test_only_explicit_proof_word_can_start_automatic_evidence(word):
    from tests.test_evidence_extractors import span
    from papergraph.evidence_extractors import build_pdf_evidence_document

    document = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Theorem 2.1. Assertion.'), span(1, word + ' refers to Lemma 1.1. QED.')))
    assert document.proofs == ()
    assert document.local_result_mentions == ()


def test_fragment_and_raw_locators_survive_restart_without_writes(tmp_path):
    path = tmp_path / 'restart.pdf'
    write_pdf(path, ['Proof. Direct. QED.\nUnrelated discussion uses Lemma 1.1.'])
    db = tmp_path / 'reading.sqlite3'
    with closing(Workspace.open(db)) as workspace:
        workspace.import_pdf(path, 'local:restart')
        proof = workspace.get_result_proof('local:restart::pdf:theorem:2.1')['known']['proof']
        fragment_id = proof['spans'][0]['span_id']
        before = list(workspace._connection.iterdump())
        raw = workspace.read_source_blocks(fragment_id)
    with closing(Workspace.open(db)) as workspace:
        assert workspace.read_source_blocks(fragment_id) == raw
        assert list(workspace._connection.iterdump()) == before
