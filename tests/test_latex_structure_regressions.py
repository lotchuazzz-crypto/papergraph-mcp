"""Synthetic public fixtures: no manuscript text or identifiers."""
import pytest

from papergraph.parser import latex_project_to_evidence_document, parse_latex
from papergraph.project import load_project


def document(tmp_path, text):
    main = tmp_path / 'main.tex'
    main.write_text(text, encoding='utf-8')
    return latex_project_to_evidence_document('local:test', 'local', str(main), None, load_project(main))


def test_shared_section_counters_aliases_and_titles(tmp_path):
    doc = document(tmp_path, r'''
\title[Short]{Synthetic title}
\newtheorem {statement} {Theorem} [section]
\newtheorem{auxiliary}[statement]{Lemma}
\newtheorem{step}[auxiliary]{Proposition}
\newtheorem*{observation}{Remark}
\section{First}
\begin{statement}[A {nested [title]}]\label{main}A.\end{statement}
\begin{auxiliary}\label{base}B.\end{auxiliary}
\begin{observation}Unnumbered.\end{observation}
\section*{Interlude}
\begin{step}C.\end{step}
\section{Second}
\begin{auxiliary}D.\end{auxiliary}
''')
    assert doc.title == 'Synthetic title'
    assert [r.visible_number for r in doc.results] == ['1.1', '1.2', None, '1.3', '2.1']
    assert [r.normalized_kind for r in doc.results[:3]] == ['theorem', 'lemma', 'observation']
    assert doc.results[0].title == 'A {nested [title]}'


def test_commented_and_verbatim_declarations_and_results_are_inert():
    nodes = parse_latex(r'''
% \newtheorem{fake}{Lemma}
\begin{verbatim}\begin{theorem}Fake.\end{theorem}\end{verbatim}
% \begin{theorem}Fake.\end{theorem}
\begin{theorem}Real.\end{theorem}
''')
    assert len(nodes) == 1 and nodes[0].content == 'Real.'


@pytest.mark.parametrize('heading,owner', [
    (r'Proof of Theorem~\ref{early}', 'early'),
    (r'Proof of \ref{early}', 'early'),
    ('Proof of Theorem 1', 'early'),
    (r'Proof of Theorem~\ref{missing}', None),
    (r'Proof of Theorems \ref{early} and \ref{near}', None),
    (r'Proof of Theorem~\ref{early} or Lemma~\ref{near}', None),
    (r'Proof of Lemma~\ref{early}', None),
    ('Sketch', None),
    (r'Proof of \ref{early,near}', None),
    ('Proof of 1', None),  # theorem and lemma both have number 1
    ('Proof of Theorem 1 or Lemma 1', None),
    ('Unclosed [heading', None),
])
def test_explicit_heading_precedes_proximity_without_fallback(tmp_path, heading, owner):
    doc = document(tmp_path,
        r'\begin{theorem}\label{early}A.\end{theorem}'
        r'\begin{lemma}\label{near}B.\end{lemma}'
        r'\begin{proof}[' + heading + r']Use \ref{near}.\end{proof}')
    assert doc.proofs[0].result_id == ('local:test::' + owner if owner else None)
    assert [m.raw_text for m in doc.local_result_mentions] == [r'\ref{near}']


@pytest.mark.parametrize('gap', [
    r'\begin{unknownresult}Hidden.\end{unknownresult}',
    'Unattributed intervening prose.',
    r'\section{Another section}',
])
def test_unnamed_proof_does_not_cross_unknown_content(tmp_path, gap):
    doc = document(tmp_path, r'\begin{theorem}A.\end{theorem}' + gap + r'\begin{proof}B.\end{proof}')
    assert doc.proofs[0].result_id is None


def test_delayed_explicit_owner_and_all_proof_source_slices(tmp_path):
    text = (r'\begin{theorem}\label{early}A.\end{theorem}'
            r'\begin{lemma}\label{near}B.\end{lemma}'
            r'\begin{proof}Near.\end{proof}'
            r'\begin{proof}[Proof of Theorem~\ref{early}]Early.\end{proof}')
    doc = document(tmp_path, text)
    assert [p.result_id for p in doc.proofs] == ['local:test::near', 'local:test::early']
    for span in doc.spans:
        assert text[span.start_offset:span.end_offset] == span.text


def test_tex_math_brackets_and_bibitems_preserve_real_citations(tmp_path):
    doc = document(tmp_path, r'''
\begin{theorem}A.\end{theorem}
\begin{proof}
$R[w]$ and $[12]P$ and \(A[key]\) and \[B[other]\].
\begin{align} C[third] &= 0. \end{align}
% [external] \cite{ignored}
Use \cite[Theorem 2.1]{external}, \cite{missing} and [external, Lemma 3.2].
Unknown prose [unverified] and optional \item[external] labels.
\end{proof}
\begin{thebibliography}{9}
% \bibitem{fake} Decoy.
\bibitem[E]{external} A. Author, Synthetic. arXiv:2401.12346.
\bibitem{uncited} B. Author, Another. \url{https://doi.org/10.1000/example}
\end{thebibliography}
''')
    assert [e.raw_label for e in doc.bibliography_entries] == ['external', 'uncited']
    assert doc.bibliography_entries[0].arxiv_id == '2401.12346'
    assert [m.raw_key for m in doc.citation_mentions] == ['external', 'missing', 'external']
    assert [m.entry_id is not None for m in doc.citation_mentions] == [True, False, True]
    assert len(doc.external_result_mentions) == 2
    for entry in doc.bibliography_entries:
        span = next(s for s in doc.spans if s.span_id == entry.entry_id)
        assert (tmp_path / span.source_ref).read_text()[span.start_offset:span.end_offset] == entry.raw_text


@pytest.mark.parametrize('control', [
    r'\setcounter{section}{9}', r'\renewcommand{\theaux}{X}',
    r'\renewcommand{\thesection}{X}', r'\appendix',
])
def test_unsupported_numbering_is_unknown_not_invented(control):
    nodes = parse_latex(r'\newtheorem{aux}{Lemma}[section]\section{A}'
                        + control + r'\begin{aux}X.\end{aux}')
    assert nodes[0].visible_number is None


def test_inline_bibliography_include_legacy_records_and_duplicate_guard(tmp_path):
    from papergraph.citations import build_citation_records, BibliographyParseError
    (tmp_path / 'refs.tex').write_text(
        r'\begin{thebibliography}{9}\bibitem{key}arXiv:2401.12346.\end{thebibliography}')
    main = tmp_path / 'main.tex'
    main.write_text(r'\cite{key}\input{refs}')
    project = load_project(main)
    assert build_citation_records(project)[0].cited_arxiv_id == '2401.12346'
    doc = latex_project_to_evidence_document('local:test', 'local', str(main), None, project)
    span = doc.spans[0]
    assert span.source_ref == 'refs.tex'
    assert (tmp_path / span.source_ref).read_text()[span.start_offset:span.end_offset] == span.text
    main.write_text(r'\input{refs}\bibliography{other}')
    (tmp_path / 'other.bib').write_text('@article{key,title={Conflict}}')
    with pytest.raises(BibliographyParseError, match='Duplicate bibliography'):
        build_citation_records(load_project(main))


def test_comments_cannot_open_literal_regions_and_escaped_percent_is_text():
    nodes = parse_latex('% \\begin{verbatim}\n'
                        r'\begin{theorem}A \% real.\end{theorem}')
    assert len(nodes) == 1 and nodes[0].content == r'A \% real.'
    assert parse_latex(r'Literal \% text % \begin{theorem}Fake.\end{theorem}') == []


def test_explicit_owner_is_reserved_before_unnamed_fallback(tmp_path):
    doc = document(tmp_path, r'\begin{theorem}\label{a}A.\end{theorem}'
                   r'\begin{proof}Unspecified.\end{proof}'
                   r'\begin{proof}[Proof of \ref{a}]Explicit.\end{proof}')
    assert [p.result_id for p in doc.proofs] == [None, 'local:test::a']


def test_external_result_locator_retains_tex_ties_and_ambiguous_goals(tmp_path):
    doc = document(tmp_path, r'\begin{theorem}A.\end{theorem}\begin{proof}'
                   r'\cite[Chapter~V, Proposition~1.5]{key}; '
                   r'\cite[Theorem~1.1 and Lemma~1.2]{key}.\end{proof}'
                   r'\begin{thebibliography}{9}\bibitem{key}Synthetic.\end{thebibliography}')
    assert len(doc.citation_mentions) == 2
    assert len(doc.external_result_mentions) == 1
    mention = doc.external_result_mentions[0]
    assert (mention.external_kind, mention.external_number) == ('proposition', '1.5')
    assert mention.raw_text == r'\cite[Chapter~V, Proposition~1.5]{key}'


def test_explicit_bracket_result_is_evidence_without_bibliography(tmp_path):
    doc = document(tmp_path, r'\begin{theorem}A.\end{theorem}\begin{proof}'
                   r'Apply [12, Theorem 3.5]. Compare $[12]P$ and [12].\end{proof}')
    assert [m.raw_text for m in doc.citation_mentions] == ['[12, Theorem 3.5]']
    assert len(doc.external_result_mentions) == 1
    assert doc.external_result_mentions[0].entry_id is None
