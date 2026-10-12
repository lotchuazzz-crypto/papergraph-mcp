from dataclasses import replace

import pytest

from papergraph.parser import latex_project_to_evidence_document
from papergraph.project import load_project


@pytest.mark.parametrize('prefix', [
    '@comment{external, an ignored note}\n',
    '@article{other, title={Example @article{external, title={Decoy}, arxiv={2401.99999}}}}\n',
])
def test_bibtex_evidence_uses_actual_top_level_entry(tmp_path, prefix):
    actual = '@article{external, title={Actual}, arxiv={2001.00001}}'
    main = tmp_path / 'main.tex'
    main.write_text(r'\begin{theorem}Claim.\end{theorem}\begin{proof}\cite{external}\end{proof}\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text(prefix + actual)
    doc = latex_project_to_evidence_document('local:a', 'local', str(main), None, load_project(main))
    entry = next(e for e in doc.bibliography_entries if e.raw_label == 'external')
    assert entry.title == 'Actual' and entry.arxiv_id == '2001.00001'
    assert entry.raw_text == actual
    span = next(s for s in doc.spans if s.span_id == entry.entry_id)
    assert (tmp_path / span.source_ref).read_text()[span.start_offset:span.end_offset] == actual


@pytest.mark.parametrize('layout', ['single', 'included', 'nested', 'cross_file'])
def test_every_tex_evidence_span_slices_its_original_file(tmp_path, layout):
    result = r'\begin{theorem}\label{main}Claim.\end{theorem}'
    proof = r'\begin{proof}Use \cite{external}.\end{proof}'
    main = tmp_path / 'main.tex'
    if layout == 'single':
        body = result + proof
    elif layout == 'included':
        body = r'Text before input.\input{proofs}'
        (tmp_path / 'proofs.tex').write_text(result + proof)
    elif layout == 'nested':
        body = r'Text before input.\input{chapter}'
        (tmp_path / 'chapter.tex').write_text(r'Chapter prefix.\input{proofs}Chapter suffix.')
        (tmp_path / 'proofs.tex').write_text(result + proof)
    else:
        body = result + r'\begin{proof}Before \input{step} after.\end{proof}'
        (tmp_path / 'step.tex').write_text(r'\cite{external}')
    main.write_text(body + r'\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text('@article{external, title={Actual}, arxiv={2001.00001}}')
    doc = latex_project_to_evidence_document('local:a', 'local', str(main), None, load_project(main))
    for span in doc.spans:
        raw = (tmp_path / span.source_ref).read_text(encoding='utf-8')
        assert raw[span.start_offset:span.end_offset] == span.text
    for evidence, field in [(doc.results[0], 'statement'), (doc.proofs[0], 'text')]:
        assert ''.join(doc.spans[i].text for i in evidence.span_indices) == getattr(evidence, field)
    assert doc.citation_mentions[0].entry_id == 'local:a::bib:external'


@pytest.mark.parametrize('bib', [
    '@article(external, title="Actual (with parentheses) and {braces}", arxiv={2001.00001})',
    '@string{t="Actual"}\n@article{external, title=t, arxiv={2001.00001}}',
])
def test_bibtex_source_respects_parentheses_quotes_and_macros(tmp_path, bib):
    main = tmp_path / 'main.tex'
    main.write_text(r'\begin{theorem}Claim.\end{theorem}\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text(bib)
    doc = latex_project_to_evidence_document('local:a', 'local', str(main), None, load_project(main))
    entry = doc.bibliography_entries[0]
    assert entry.raw_text.startswith('@article') and entry.arxiv_id == '2001.00001'
    span = next(s for s in doc.spans if s.span_id == entry.entry_id)
    assert bib[span.start_offset:span.end_offset] == entry.raw_text


def test_missing_mapping_is_explicitly_rejected(tmp_path):
    main = tmp_path / 'main.tex'
    main.write_text(r'\begin{theorem}Claim.\end{theorem}')
    project = load_project(main)
    project = replace(project, spans=tuple(replace(s, source_start=None) for s in project.spans))
    with pytest.raises(ValueError, match='Cannot map TeX evidence'):
        latex_project_to_evidence_document('local:a', 'local', str(main), None, project)
