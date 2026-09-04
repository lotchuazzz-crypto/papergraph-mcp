from pathlib import Path

from papergraph.parser import latex_project_to_evidence_document
from papergraph.project import load_project


def test_latex_project_to_evidence_document_maps_theorems_to_results(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    main.write_text(
        r"\title{A TeX Paper}"
        r"\begin{lemma}\label{lem:base}Base.\end{lemma}"
        r"\begin{theorem}[Main]\label{thm:main}Uses \ref{lem:base}.\end{theorem}",
        encoding="utf-8",
    )
    project = load_project(main)

    document = latex_project_to_evidence_document(
        "local:paper-a",
        "local",
        str(main.resolve()),
        None,
        project,
    )

    assert document.paper_id == "local:paper-a"
    assert document.source_type == "local"
    assert document.title == "A TeX Paper"
    assert [result.result_id for result in document.results] == [
        "local:paper-a::lem:base",
        "local:paper-a::thm:main",
    ]
    assert document.results[1].label == "thm:main"
    assert document.results[1].title == "Main"
    assert document.results[1].method == "latex_environment"
    assert document.spans[0].source_type == "tex"
    assert document.spans[0].source_ref == "main.tex"
