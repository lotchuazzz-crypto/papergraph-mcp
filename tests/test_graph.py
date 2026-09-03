from pathlib import Path

from papergraph.graph import PaperGraph
from papergraph.parser import parse_file


SAMPLE = (
    Path(__file__).parent
    / "fixtures"
    / "sample.tex"
)


def build_graph() -> PaperGraph:
    return PaperGraph(
        parse_file(SAMPLE)
    )


def test_direct_dependencies():
    graph = build_graph()

    dependencies = graph.dependencies(
        "thm:main"
    )

    assert [
        node.id
        for node in dependencies
    ] == [
        "prop:key",
        "lem:vanishing",
    ]


def test_recursive_dependencies():
    graph = build_graph()

    dependencies = graph.dependencies(
        "thm:main",
        recursive=True,
    )

    ids = {
        node.id
        for node in dependencies
    }

    assert ids == {
        "prop:key",
        "lem:vanishing",
    }


def test_where_used():
    graph = build_graph()

    users = graph.where_used(
        "lem:vanishing"
    )

    assert {
        node.id
        for node in users
    } == {
        "prop:key",
        "thm:main",
    }


def test_dependency_diagnostics_explain_resolved_unresolved_and_basis():
    graph = build_graph()

    diagnostics = graph.dependency_diagnostics("thm:main")

    assert diagnostics == {
        "theorem_id": "thm:main",
        "recursive": False,
        "extraction_basis": "statement_explicit_latex_refs_only",
        "referenced_labels": ["prop:key", "lem:vanishing"],
        "resolved_labels": ["prop:key", "lem:vanishing"],
        "unresolved_labels": [],
        "dependency_ids": ["prop:key", "lem:vanishing"],
        "warnings": [],
    }


def test_empty_dependency_diagnostics_warn_about_scoped_negative_result(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text(
        r"\begin{theorem}\label{thm:isolated}No references here.\end{theorem}",
        encoding="utf-8",
    )
    graph = PaperGraph(parse_file(source))

    diagnostics = graph.dependency_diagnostics("thm:isolated")

    assert diagnostics["dependency_ids"] == []
    assert diagnostics["referenced_labels"] == []
    assert diagnostics["warnings"] == [
        "No explicit theorem-label dependencies were detected in the theorem statement. This is not evidence that the theorem has no mathematical dependencies."
    ]


def test_dependency_diagnostics_report_unresolved_labels(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text(
        r"\begin{theorem}\label{thm:main}Uses \ref{missing}.\end{theorem}",
        encoding="utf-8",
    )
    graph = PaperGraph(parse_file(source))

    diagnostics = graph.dependency_diagnostics("thm:main")

    assert diagnostics["referenced_labels"] == ["missing"]
    assert diagnostics["resolved_labels"] == []
    assert diagnostics["unresolved_labels"] == ["missing"]
    assert diagnostics["dependency_ids"] == []
    assert diagnostics["warnings"] == [
        "No explicit theorem-label dependencies were detected in the theorem statement. This is not evidence that the theorem has no mathematical dependencies."
    ]
