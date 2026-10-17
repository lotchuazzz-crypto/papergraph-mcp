"""Synthetic counter/control and citation-context regressions from review."""
import pytest

from papergraph.parser import parse_latex
from tests.test_latex_structure_regressions import document


@pytest.mark.parametrize('control', [
    r'\stepcounter{axi}', r'\refstepcounter{axi}',
    r'\stepcounter{shared}', r'\refstepcounter{shared}',
    r'\setcounter{shared}{7}', r'\addtocounter{shared}{2}',
    r'\counterwithin*{shared}{section}', r'\counterwithout{shared}{section}',
    r'\numberwithin[arabic]{shared}{section}', r'\usecounter{axi}',
    r'\stepcounter{\chosen}', '\\stepcounter % comment\n {shared}',
])
def test_uninterpreted_counter_mutations_cannot_establish_numeric_owner(tmp_path, control):
    doc = document(tmp_path, r'\newtheorem{axi}{Theorem}\newtheorem{shared}[axi]{Lemma}'
                   r'\begin{axi}\label{a}A.\end{axi}' + control +
                   r'\begin{axi}\label{b}B.\end{axi}'
                   r'\begin{proof}[Proof of Theorem 2]Numeric.\end{proof}'
                   r'\begin{proof}[Proof of Theorem~\ref{b}]Label.\end{proof}')
    assert [r.visible_number for r in doc.results] == [None, None]
    assert [p.result_id for p in doc.proofs] == [None, 'local:test::b']
    assert any('counter' in w.casefold() for w in doc.warnings)


@pytest.mark.parametrize('within,control', [
    ('section', r'\stepcounter{section}'),
    ('section', r'\refstepcounter{chapter}'),
    ('subsection', r'\stepcounter{section}'),
    ('subsection', r'\refstepcounter{subsection}'),
])
def test_prefix_counter_mutations_make_dependent_numbers_unknown(within, control):
    nodes = parse_latex(r'\newtheorem{axi}{Theorem}[' + within + r']'
                        r'\section{A}\subsection{B}' + control + r'\begin{axi}A.\end{axi}')
    assert nodes[0].visible_number is None


def test_unrelated_counter_and_literal_mutations_do_not_taint_numbering(tmp_path):
    doc = document(tmp_path, '\n'.join([
        r'\newtheorem{axi}{Theorem}', r'\stepcounter{unrelated}',
        r'% \refstepcounter{axi}',
        r'\begin{verbatim}\stepcounter{axi}\end{verbatim}',
        r'\begin{axi}\label{a}A.\end{axi}', r'\begin{axi}\label{b}B.\end{axi}',
        r'\begin{proof}[Proof of Theorem 2]B.\end{proof}']))
    assert [r.visible_number for r in doc.results] == ['1', '2']
    assert doc.proofs[0].result_id == 'local:test::b'


def test_unknown_compatible_number_blocks_an_apparently_unique_numeric_match(tmp_path):
    doc = document(tmp_path, r'\newtheorem{axi}{Theorem}\newtheorem{other}{Theorem}'
                   r'\stepcounter{axi}\begin{axi}\label{a}A.\end{axi}'
                   r'\begin{other}First.\end{other}\begin{other}\label{b}Second.\end{other}'
                   r'\begin{proof}[Proof of Theorem 2]Unknown.\end{proof}')
    assert doc.results[0].visible_number is None
    assert doc.results[-1].visible_number == '2'
    assert doc.proofs[0].result_id is None


def test_unknown_numbers_cannot_create_numeric_body_dependency_either(tmp_path):
    doc = document(tmp_path, r'\newtheorem{axi}{Theorem}\newtheorem{other}{Theorem}'
                   r'\stepcounter{axi}\begin{axi}\label{a}A.\end{axi}'
                   r'\begin{other}First.\end{other}\begin{other}\label{b}Second.\end{other}'
                   r'\begin{proof}[Proof of \ref{a}]By Theorem 2 and \ref{b}.\end{proof}')
    assert doc.proofs[0].result_id == 'local:test::a'
    numeric = next(m for m in doc.local_result_mentions if m.method == 'proof_local_result_regex')
    assert numeric.target_result_id is None
    label = next(m for m in doc.local_result_mentions if m.method == 'proof_latex_ref')
    assert label.target_result_id == 'local:test::b'


@pytest.mark.parametrize('body,keys', [
    (r'\ensuremath{[K]}', []),
    (r'\ensuremath{{R[K]}} then [K].', ['K']),
    ('\\ensuremath % comment\n {[K]}', []),
    (r'\ensuremath{[absent, Theorem 2.1]}', []),
    (r'\ensuremath{[K] + \text{by \cite{K}}}', ['K']),
    (r'\ensuremath{[K]', []),
    (r'\ensuremath [K]', []),
])
def test_ensuremath_is_math_but_explicit_cites_survive(tmp_path, body, keys):
    doc = document(tmp_path, r'\begin{theorem}A.\end{theorem}\begin{proof}' + body +
                   r'\end{proof}\begin{thebibliography}{9}\bibitem{K}Synthetic.\end{thebibliography}')
    assert [m.raw_key for m in doc.citation_mentions] == keys


@pytest.mark.parametrize('body,keys', [
    (r'\makebox[2cm][c]{Text}', []),
    ('\\makebox[2cm]% comment\n[c]{Text}', []),
    ('\\makebox % comment\n [2cm] % another\n [c]{Text}', []),
    (r'\custom[one][{[nested]}][c]{Text}', []),
    (r'\makebox[\cite{K}][c]{Text}', ['K']),
    (r'\makebox[2cm][c]{Text} [K].', ['K']),
    (r'\emph{Text} [K] and [absent, Theorem 2.1].', ['K', 'absent']),
])
def test_consecutive_command_options_are_not_prose_citations(tmp_path, body, keys):
    doc = document(tmp_path, r'\begin{theorem}A.\end{theorem}\begin{proof}' + body +
                   r'\end{proof}\begin{thebibliography}{9}\bibitem{K}Synthetic.'
                   r'\bibitem{c}Alignment token.\end{thebibliography}')
    assert [m.raw_key for m in doc.citation_mentions] == keys
