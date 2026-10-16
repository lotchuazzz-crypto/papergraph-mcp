"""Regressions from the independent 1.2.2 acceptance, with real PDF imports."""
from contextlib import closing

import pymupdf
import pytest

from papergraph.workspace import Workspace
from tests.test_dependency_reading import import_graph


BOUNDARIES = [
    '2. independent example', '2. Independent example', '2 independent example',
    '2.3 independent example', '2.3. independent example',
    'A. Independent example', 'b. independent example', 'C) Independent example',
    'II. independent example', 'iv. independent example',
    'Appendix A. Auxiliary arguments', 'appendix b: auxiliary arguments',
    'Section 3. Further discussion', 'Chapter IV. Further discussion',
    'Part II. Further discussion', 'Claim. Another assertion.',
    'Definition. Another assertion.', 'Remark (auxiliary). Further discussion.',
    'Example. Another assertion.', 'Lemma (auxiliary). Another assertion.',
]


def write_boundary_pdf(path, boundary, heading_size=11):
    with pymupdf.open() as document:
        page = document.new_page()
        texts = ['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
                 'Theorem 2.1. Main assertion.', 'Proof. An incomplete main argument.',
                 boundary, 'For a separate example, apply Lemma 1.1. QED.']
        for index, text in enumerate(texts):
            page.insert_text((72, 72 + index * 70), text,
                             fontsize=heading_size if index == 4 else 11)
        document.save(path)


@pytest.mark.parametrize('boundary', BOUNDARIES)
def test_actual_pdf_proof_never_crosses_section_or_declaration_boundary(tmp_path, boundary):
    path = tmp_path / 'boundary.pdf'
    write_boundary_pdf(path, boundary)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:boundary')
        result_id = 'local:boundary::pdf:theorem:2.1'
        proof = workspace.get_result_proof(result_id)['known']['proof']
        assert proof['text'] == 'Proof. An incomplete main argument.'
        assert proof['text_coverage']['complete'] is False
        dependencies = workspace.get_proof_dependencies(result_id)
        assert dependencies['known']['resolved_local_results'] == []
        assert dependencies['unresolved']['local_result_mentions'] == []
        assert workspace.get_result_reading_path(result_id)['edges'] == []
        # Rejected proof association does not make the following source vanish.
        args = workspace.get_source_slice(proof_id=proof['proof_id'])['source_reading']['arguments']
        blocks = workspace.read_source_blocks(**args)['blocks']
        assert any('For a separate example' in row['text'] for row in blocks)


def test_actual_pdf_unnumbered_larger_heading_is_an_ambiguous_boundary(tmp_path):
    path = tmp_path / 'layout.pdf'
    write_boundary_pdf(path, 'independent auxiliary material', heading_size=16)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:layout')
        result_id = 'local:layout::pdf:theorem:2.1'
        proof = workspace.get_result_proof(result_id)['known']['proof']
        assert 'For a separate example' not in proof['text']
        assert workspace.get_proof_dependencies(result_id)['known']['resolved_local_results'] == []


def test_actual_pdf_ordinary_continuation_retains_explicit_late_evidence(tmp_path):
    path = tmp_path / 'continuation.pdf'
    # The same plain body size is intentionally not a layout heading signal.
    write_boundary_pdf(path, 'We continue with the required construction.')
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:continuation')
        deps = workspace.get_proof_dependencies('local:continuation::pdf:theorem:2.1')
        assert [r['visible_number'] for r in deps['known']['resolved_local_results']] == ['1.1']


@pytest.mark.parametrize('embedded_in_opening', [True, False])
def test_actual_pdf_boundary_inside_one_text_block_does_not_leak_mentions(tmp_path, embedded_in_opening):
    path = tmp_path / 'multiline.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        for index, text in enumerate(['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
                                      'Theorem 2.1. Main assertion.']):
            page.insert_text((72, 72 + index * 70), text, fontsize=11)
        text = 'Proof. An incomplete main argument.'
        if not embedded_in_opening:
            page.insert_text((72, 282), text, fontsize=11)
            text = 'We continue the calculation.'
        page.insert_text((72, 282 if embedded_in_opening else 352),
                         text + '\n2. independent example\nApply Lemma 1.1. QED.', fontsize=11)
        document.save(path)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:multiline')
        result_id = 'local:multiline::pdf:theorem:2.1'
        proof = workspace.get_result_proof(result_id)['known']['proof']
        assert proof['text'] == 'Proof. An incomplete main argument.'
        assert proof['method'] == 'pdf_proof_heading'
        assert workspace.get_proof_dependencies(result_id)['known']['resolved_local_results'] == []


@pytest.mark.parametrize('recursive', [True, False])
def test_compact_full_handle_preserves_custom_candidate_limit(tmp_path, recursive):
    with closing(import_graph(tmp_path, {'B': [], 'C': [], 'A': ['B', 'C']})) as workspace:
        args = {'paper_id': 'local:graph', 'target_result_id': 'local:graph::node:A',
                'recursive': recursive, 'max_candidates': 1}
        expected = workspace.get_dependency_reading(**args, detail='full')
        compact = workspace.get_dependency_reading(**args, detail='compact')
        handle = compact['full_evidence']['arguments']
        assert handle['max_candidates'] == 1
        assert workspace.get_dependency_reading(**handle) == expected
