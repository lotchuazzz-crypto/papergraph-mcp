from dataclasses import replace

import pytest

from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.project import load_project
from papergraph.workspace import Workspace
from tests.test_evidence_extractors import span


@pytest.mark.parametrize('body,keys', [
    (r'Apply \cite{external}.', ['external']),
    (r'Apply \citep[see][Theorem 2.1]{external, other}. Then \cite{external}.',
     ['external', 'other', 'external']),
])
def test_tex_proof_citations_keep_identity_and_trace(tmp_path, body, keys):
    main = tmp_path / 'main.tex'
    main.write_text(r'\begin{theorem}\label{thm:main}Synthetic.\end{theorem}'
                    r'\begin{proof}' + body + r'\end{proof}\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text(
        '@article{external, title={Synthetic}, arxiv={2401.12346}}\n'
        '@article{other, title={Other}, doi={10.1000/example}}')
    ws = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        ws.import_project('local:fixture', 'local', str(main), None, load_project(main))
        rid = 'local:fixture::thm:main'
        plan = ws.plan_external_imports_for_result(rid)
        assert plan['candidates'][0]['source']['arxiv_id'] == '2401.12346'
        queue = ws.create_reading_queue(rid)
        assert ws.plan_external_imports_for_queue(queue['queue_id'])['candidates'][0]['source']['arxiv_id'] == '2401.12346'
        mentions = ws._connection.execute(
            'SELECT mention_id,raw_key,entry_id,proof_id FROM citation_mentions ORDER BY mention_id').fetchall()
        assert [m[1] for m in mentions] == keys
        assert all(m[2] and m[3] == 'local:fixture::proof:1' for m in mentions)
        for m in mentions:
            evidence = ws.get_evidence(m[0])
            assert evidence['spans'][0]['excerpt'] == body
            assert evidence['spans'][0]['start_offset'] is not None
        for recursive in (False, True):
            deps = ws.get_proof_dependencies(rid, recursive=recursive)
            assert deps['known']['resolved_local_results'] == []
            assert deps['known']['resolved_external_results'] == []
            assert [m['raw_key'] for m in deps['known']['citation_mentions']] == keys
        assert len(ws.list_papers()) == 1  # planning never downloads
    finally:
        ws.close()


@pytest.mark.parametrize('extra,expected', [('', 'local:paper-a::pdf:proposition:2.17'),
                                         ('Lemma 2.17. Different.', None)])
def test_number_only_explicit_pdf_heading_never_uses_proximity(extra, expected):
    spans = [span(0, 'Proposition 2.17. Assertion.')]
    if extra:
        spans.append(span(1, extra))
    spans.extend([span(2, 'Lemma 2.20. Closer result.'),
                  replace(span(3, 'Proof of 2.17. Apply Lemma 2.20.'), page=15)])
    doc = build_pdf_evidence_document('local:paper-a', 'paper.pdf', tuple(spans))
    proof = doc.proofs[0]
    assert proof.result_id == expected
    assert proof.association_basis == ('proof_heading_names_result' if expected else 'unresolved')
    assert doc.spans[proof.span_indices[0]].page == 15


def test_missing_named_heading_does_not_fall_back_to_nearby_result():
    doc = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Lemma 2.20. Nearby.'), span(1, 'Proof of 9.99. Unknown.'),
    ))
    assert doc.proofs[0].result_id is None


def test_ambiguous_bracket_bibliography_and_tex_comments_stay_unknown():
    from papergraph.evidence_extractors import extract_citation_mentions
    doc = build_pdf_evidence_document('local:paper-a', 'paper.pdf', (
        span(0, 'Theorem 1.1. Main.'), span(1, 'Proof. Apply [key, Lemma 2.1].'),
        span(2, 'References'), span(3, '[key] First. arXiv:2401.12346.'),
        span(4, '[KEY] Second. arXiv:2401.12347.'),
    ))
    assert doc.citation_mentions[0].entry_id is None
    assert doc.citation_mentions[0].resolution_status == 'ambiguous'
    proof = replace(doc.proofs[0], text=r'\cite*{key,key} % \cite{ignored}' + '\n' + r'\cite[see][p. 2]{missing}')
    citations = extract_citation_mentions(doc.paper_id, (proof,), doc.bibliography_entries)
    assert [m.raw_key for m in citations] == ['key', 'key', 'missing']
    assert all(m.entry_id is None for m in citations)


def test_conflicting_bibtex_identity_is_rejected(tmp_path):
    main = tmp_path / 'main.tex'
    main.write_text(r'\begin{theorem}\label{main}X.\end{theorem}\begin{proof}\cite{key}\end{proof}\bibliography{a,b}')
    (tmp_path / 'a.bib').write_text('@article{key, arxiv={2401.12346}}')
    (tmp_path / 'b.bib').write_text('@article{key, arxiv={2401.12347}}')
    from papergraph.parser import latex_project_to_evidence_document
    with pytest.raises(ValueError, match='Conflicting bibliography'):
        latex_project_to_evidence_document('local:a', 'local', str(main), None, load_project(main))
