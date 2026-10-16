"""Heading annotations cannot supply proof-body evidence through punctuation."""
from contextlib import closing

import pytest

from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace
from tests.test_evidence_extractors import span


ANNOTATIONS = [
    '(cf. [9, Theorem 3.1])',
    '[note: [9, Theorem 3.1]]',
    '{note: ([9, Theorem 3.1])}',
    '(cf. {note: [9, Theorem 3.1]})',
    '"cf. [9, Theorem 3.1]"',
    "'cf. [9, Theorem 3.1]'",
    '“cf. [9, Theorem 3.1]”',
    '‘note: [9, Theorem 3.1]’',
    '(note: "cf. [9, Theorem 3.1]")',
    r'("cf. \" [9, Theorem 3.1]")',
]
UNCERTAIN = [
    '(cf. [9, Theorem 3.1]',
    '[note: [9, Theorem 3.1])',
    '"cf. [9, Theorem 3.1]',
    'cf. [9, Theorem 3.1]',
]


def document(line):
    return build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Lemma 1.1. Base case.'), span(1, 'Proof. Immediate. QED.'),
        span(2, 'Theorem 2.1. First goal.'), span(3, 'Theorem 3.1. Second goal.'),
        span(4, line)))


@pytest.mark.parametrize('annotation', ANNOTATIONS)
def test_balanced_heading_annotations_are_never_body_citations(annotation, tmp_path):
    line = f'Proof of Theorem 2.1 {annotation}. Apply Lemma 1.1. QED.'
    doc = document(line)
    assert doc.proofs[-1].result_id is None
    assert not doc.citation_mentions and not doc.external_result_mentions
    assert [mention.raw_text for mention in doc.local_result_mentions] == ['Lemma 1.1']
    assert doc.proofs[-1].text == line
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_evidence_document(doc)
        assert workspace.plan_external_imports_for_paper(doc.paper_id)['blocked'] == []
        assert workspace.get_evidence(doc.proofs[-1].proof_id)['metadata']['text'] == line


@pytest.mark.parametrize('annotation', UNCERTAIN)
def test_unreliable_heading_boundary_extracts_no_body_mentions(annotation):
    line = f'Proof of Theorem 2.1 {annotation}. Apply Lemma 1.1. QED.'
    doc = document(line)
    assert doc.proofs[-1].result_id is None
    assert doc.local_result_mentions == ()
    assert doc.citation_mentions == ()
    assert doc.external_result_mentions == ()
    assert doc.spans[4].text == line


@pytest.mark.parametrize('references', [
    'cf. Lemma 3.1',
    r'cf. \ref{thm:other}',
    'note: we prove Lemmas 3.1 and 3.2',
    r'cf. \citep[Theorem 3.1]{9}',
    'cf. [9, Theorem 3.1]',
])
def test_all_shared_mention_pipelines_exclude_heading_annotations(references):
    doc = document(f'Proof of Theorem 2.1 ({references}). Apply Lemma 1.1. QED.')
    assert doc.proofs[-1].result_id is None
    assert [mention.raw_text for mention in doc.local_result_mentions] == ['Lemma 1.1']
    assert not doc.citation_mentions and not doc.external_result_mentions


@pytest.mark.parametrize('body', [
    '(By [9, Theorem 3.1], apply Lemma 1.1.) QED.',
    'Apply [9, Theorem 3.1] and Lemma 1.1. QED.',
])
def test_unique_heading_keeps_real_parenthesized_body_citations(body):
    doc = document('Proof of Theorem 2.1. ' + body)
    assert doc.proofs[-1].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert [mention.raw_text for mention in doc.local_result_mentions] == ['Lemma 1.1']
    assert [mention.raw_text for mention in doc.citation_mentions] == ['[9, Theorem 3.1]']
    assert [mention.raw_text for mention in doc.external_result_mentions] == ['[9, Theorem 3.1]']


def test_unique_heading_keeps_other_real_body_reference_pipelines():
    doc = document(r'Proof of Theorem 2.1. Apply \ref{thm:other}. '
                   r'We prove Lemmas 3.1 and 3.2 using \citep[Theorem 3.1]{9}. QED.')
    assert doc.proofs[-1].result_id == 'local:paper-a::pdf:theorem:2.1'
    assert {mention.method for mention in doc.local_result_mentions} == {
        'proof_latex_ref', 'proof_roadmap_result_regex'}
    assert [mention.raw_text for mention in doc.citation_mentions] == [r'\citep[Theorem 3.1]{9}']
    assert len(doc.external_result_mentions) == 1


@pytest.mark.parametrize('annotation', ANNOTATIONS[:2])
def test_annotated_heading_keeps_distinct_real_body_citation(annotation):
    doc = document(f'Proof of Theorem 2.1 {annotation}. '
                   'Apply [10, Theorem 4.1] and Lemma 1.1. QED.')
    assert doc.proofs[-1].result_id is None
    assert [mention.raw_text for mention in doc.local_result_mentions] == ['Lemma 1.1']
    assert [mention.raw_text for mention in doc.citation_mentions] == ['[10, Theorem 4.1]']
    assert [mention.raw_text for mention in doc.external_result_mentions] == ['[10, Theorem 4.1]']


@pytest.mark.parametrize('goals', ['Theorem 2.1 and Theorem 3.1', 'Theorem 2.1/3.1',
                                 'Theorems 2.1 and 3.1'])
def test_known_compound_heading_keeps_distinct_real_body_evidence(goals):
    doc = document(f'Proof of {goals}. Apply [10, Theorem 4.1] and Lemma 1.1. QED.')
    assert doc.proofs[-1].result_id is None
    assert [mention.raw_text for mention in doc.local_result_mentions] == ['Lemma 1.1']
    assert [mention.raw_text for mention in doc.citation_mentions] == ['[10, Theorem 4.1]']
    assert [mention.raw_text for mention in doc.external_result_mentions] == ['[10, Theorem 4.1]']
