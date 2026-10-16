"""A later QED must not attach named back matter to an unfinished PDF proof."""
from contextlib import closing

import pymupdf
import pytest

from papergraph.workspace import Workspace
from tests.test_v122_independent_regressions import write_boundary_pdf


HEADINGS = [
    'Acknowledgment', 'Acknowledgments', 'ACKNOWLEDGMENTS',
    'Acknowledgement', 'Acknowledgements', 'Acknowledgments:',
    'Acknowledgments and Funding', 'Acknowledgements and disclosures',
    'References', 'REFERENCES.', 'Reference', 'References and Notes',
    'Notes and References', 'Bibliography', 'Bibliographical References',
    'Literature Cited', 'Works Cited', 'Further Reading',
    'Appendix', 'Appendices', 'APPENDIX A: additional arguments',
    'Supplementary Material', 'Supplementary Materials',
    'Supplemental Information', 'Supplementary Information',
    'Electronic Supplementary Material', 'Supporting Information',
    'Data Availability', 'Data Availability Statement', 'Code Availability',
    'Data and Code Availability', 'Availability of Data and Materials',
    'Author Contributions', "Authors' Contributions", 'Funding',
    'Funding Information', 'Competing Interests', 'Conflict of Interest',
    'Conflicts of Interest', 'Declarations', 'Ethics Approval',
    'Ethical Approval', 'Notes', 'Endnotes', 'Abstract', 'Contents',
    'Table of Contents', 'Introduction', 'Background', 'Preliminaries',
    'Notation', 'Methods', 'Materials and Methods', 'Results',
    'Discussion', 'Conclusion', 'Conclusions', 'Summary', 'Future Work',
    'Outlook', 'Acknowledgments: additional support',
    '(2) independent discussion', '[2] independent discussion',
    '(A) independent discussion', 'A: independent discussion',
    'B.1 auxiliary estimates', 'a.1 auxiliary estimates',
    'A.2.3 auxiliary estimates', 'a.2.3. auxiliary estimates',
    '2.a auxiliary estimates', '2.a.3 auxiliary estimates',
    'II.2 auxiliary estimates', 'iv.a.2 auxiliary estimates',
    '(B.1) auxiliary estimates', '[a.1] auxiliary estimates',
    'B.1: auxiliary estimates', 'a.1) auxiliary estimates',
    'B.1', 'a.1', '2.3', '(A.1)', '[2.b]',
    'Annex A. Additional material', 'Supplement B. More material',
    'Sec. 4 further discussion', 'Ch. II further discussion',
    'References Cited', 'Literature', 'Bibliographic References',
    'Supplementary Data', 'Declaration of Competing Interests',
    'Conflict of Interest Statement',
]


@pytest.mark.parametrize('heading', HEADINGS)
def test_same_size_named_heading_prevents_false_proof_edge_and_keeps_raw(tmp_path, heading):
    path = tmp_path / 'backmatter.pdf'
    write_boundary_pdf(path, heading)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:boundary')
        result_id = 'local:boundary::pdf:theorem:2.1'
        proof = workspace.get_result_proof(result_id)['known']['proof']
        assert proof['text'] == 'Proof. An incomplete main argument.'
        assert proof['text_coverage']['complete'] is False
        assert proof['method'] == 'pdf_proof_heading'
        assert workspace.get_proof_dependencies(result_id)['known']['resolved_local_results'] == []
        assert workspace.get_result_reading_path(result_id)['edges'] == []
        args = workspace.get_source_slice(proof_id=proof['proof_id'])['source_reading']['arguments']
        blocks = workspace.read_source_blocks(**args)['blocks']
        assert any('For a separate example' in block['text'] for block in blocks)


@pytest.mark.parametrize('heading', [
    'Acknowledgments', 'Acknowledgements', 'References and Notes',
    'Data Availability Statement', 'Supplementary Material', '(A) independent discussion',
    'B.1 auxiliary estimates', 'a.1 auxiliary estimates',
])
@pytest.mark.parametrize('embedded_in_opening', [True, False])
def test_named_boundary_within_pdf_block_does_not_leak_later_qed(tmp_path, heading, embedded_in_opening):
    path = tmp_path / 'embedded.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        for index, text in enumerate(['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
                                      'Theorem 2.1. Main assertion.']):
            page.insert_text((72, 72 + index * 70), text, fontsize=11)
        text = 'Proof. An incomplete main argument.'
        if not embedded_in_opening:
            page.insert_text((72, 282), text, fontsize=11)
            text = 'We continue the argument.'
        page.insert_text((72, 282 if embedded_in_opening else 352),
                         text + '\n' + heading + '\nApply Lemma 1.1. QED.', fontsize=11)
        document.save(path)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:embedded')
        result_id = 'local:embedded::pdf:theorem:2.1'
        proof = workspace.get_result_proof(result_id)['known']['proof']
        assert proof['text'] == 'Proof. An incomplete main argument.'
        assert workspace.get_proof_dependencies(result_id)['known']['resolved_local_results'] == []


@pytest.mark.parametrize('prefix', ['A', 'b', 'II', 'iv', '1', '12'])
@pytest.mark.parametrize('middle', ['1', '2.a', 'II.3', 'a.2.10'])
@pytest.mark.parametrize('wrapper', ['{}', '{}.', '{}:', '{} )', '({})', '[{}]'])
def test_outline_grammar_handles_hierarchical_segments_without_title_case_assumptions(prefix, middle, wrapper):
    from papergraph.evidence_extractors import _proof_lexical_boundary

    label = wrapper.format(prefix + '.' + middle)
    assert _proof_lexical_boundary(label + ' auxiliary estimates')
    assert _proof_lexical_boundary(label)


@pytest.mark.parametrize('heading', HEADINGS)
@pytest.mark.parametrize('case', ['lower', 'upper'])
def test_named_heading_grammar_is_case_independent(heading, case):
    from papergraph.evidence_extractors import _proof_lexical_boundary

    assert _proof_lexical_boundary(getattr(heading, case)())


def test_unicode_apostrophe_in_named_author_contributions():
    from papergraph.evidence_extractors import _proof_lexical_boundary

    assert _proof_lexical_boundary('Authors’ Contributions')


@pytest.mark.parametrize('continuation', [
    'Acknowledgments are not needed to justify this estimate.',
    'References to Lemma 1.1 suffice for the next bound.',
    'The supplementary material is not used in this construction.',
])
def test_heading_words_inside_ordinary_prose_are_not_named_headings(tmp_path, continuation):
    path = tmp_path / 'continuation.pdf'
    write_boundary_pdf(path, continuation)
    with closing(Workspace.open(tmp_path / 'reading.sqlite3')) as workspace:
        workspace.import_pdf(path, 'local:continuation')
        result_id = 'local:continuation::pdf:theorem:2.1'
        assert workspace.get_proof_dependencies(result_id)['known']['resolved_local_results']
