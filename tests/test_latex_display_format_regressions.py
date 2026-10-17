"""Finite direct display-redefinition forms; never execute their TeX bodies."""
import pytest

from tests.test_latex_structure_regressions import document


@pytest.mark.parametrize('definition', [
    r'\renewcommand{\thea}{X}',
    r'\renewcommand*{\thea}{X}',
    r'\renewcommand * {\thea}{X}',
    r'\renewcommand * { \thea } {X}',
    r'\renewcommand*\thea{X}',
    r'\renewcommand * \thea {X}',
    '\\renewcommand % first\n * % second\n { \\thea % third\n }{X}',
    r'\renewcommand*{\thea}[1]{X}',
    r'\def\thea{X}',
    r'\gdef \thea {X}',
    r'\edef\thea{X}',
    r'\xdef \thea {X}',
])
def test_direct_display_definition_is_unknown_and_cannot_own_numeric_proof(tmp_path, definition):
    doc = document(tmp_path, r'\newtheorem{a}{Theorem}' + definition +
                   r'\begin{a}\label{main}A.\end{a}'
                   r'\begin{proof}[Proof of Theorem 1]By Theorem 1.\end{proof}'
                   r'\begin{proof}[Proof of \ref{main}]Label.\end{proof}')
    assert doc.results[0].visible_number is None
    assert [p.result_id for p in doc.proofs] == [None, 'local:test::main']
    assert doc.local_result_mentions[0].target_result_id is None


@pytest.mark.parametrize('within', ['chapter', 'section', 'subsection', 'subsubsection'])
def test_starred_prefix_display_definition_propagates_to_number(tmp_path, within):
    doc = document(tmp_path, r'\newtheorem{a}{Theorem}[' + within + r']'
                   r'\chapter{C}\section{S}\subsection{T}\subsubsection{U}'
                   r'\renewcommand * {\the' + within + r'} {X}'
                   r'\begin{a}\label{main}A.\end{a}'
                   r'\begin{proof}[Proof of \ref{main}]Label.\end{proof}')
    assert doc.results[0].visible_number is None
    assert doc.proofs[0].result_id == 'local:test::main'


def test_shared_alias_display_redefinition_taints_only_its_descendants(tmp_path):
    doc = document(tmp_path, r'\newtheorem{a}{Theorem}\newtheorem{middle}[a]{Lemma}'
                   r'\newtheorem{last}[middle]{Proposition}'
                   r'\renewcommand* {\themiddle}{X}'
                   r'\begin{a}A.\end{a}\begin{middle}B.\end{middle}'
                   r'\begin{last}\label{main}C.\end{last}'
                   r'\begin{proof}[Proof of Lemma 2]Unknown.\end{proof}'
                   r'\begin{proof}[Proof of \ref{main}]Label.\end{proof}')
    assert [r.visible_number for r in doc.results] == ['1', None, None]
    assert [p.result_id for p in doc.proofs] == [None, 'local:test::main']


@pytest.mark.parametrize('definition', [
    r'\renewcommand*{\theunrelated}{X}',
    '% \\renewcommand*{\\thea}{X}\n',
    r'\verb|\renewcommand*{\thea}{X}|',
    r'\begin{verbatim}\renewcommand*{\thea}{X}\end{verbatim}',
])
def test_unrelated_and_literal_display_definitions_leave_number_known(tmp_path, definition):
    doc = document(tmp_path, r'\newtheorem{a}{Theorem}' + definition +
                   r'\begin{a}\label{main}A.\end{a}'
                   r'\begin{proof}[Proof of Theorem 1]Known.\end{proof}')
    assert doc.results[0].visible_number == '1'
    assert doc.proofs[0].result_id == 'local:test::main'


def test_child_prefix_redefinition_does_not_taint_parent_prefix(tmp_path):
    doc = document(tmp_path, r'\newtheorem{a}{Theorem}[section]\section{S}'
                   r'\renewcommand*{\thesubsection}{X}'
                   r'\begin{a}\label{main}A.\end{a}'
                   r'\begin{proof}[Proof of Theorem 1.1]Known.\end{proof}')
    assert doc.results[0].visible_number == '1.1'
    assert doc.proofs[0].result_id == 'local:test::main'
