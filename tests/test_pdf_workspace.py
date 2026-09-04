from pathlib import Path

import fitz

from papergraph.workspace import Workspace


def write_math_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2 and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345v2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def test_workspace_import_pdf_paper_and_query_dependencies(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_math_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        imported = workspace.import_pdf(pdf, "local:pdf-paper")
        assert imported.paper_id == "local:pdf-paper"
        assert imported.theorem_count == 2

        paper = workspace.get_paper("local:pdf-paper")
        assert paper["source_type"] == "pdf"
        assert paper["main_file"] == "paper.pdf"

        result_id = "local:pdf-paper::pdf:theorem:1.1"
        proof = workspace.get_result_proof(result_id)
        assert "Lemma 1.2" in proof["known"]["proof"]["text"]

        dependencies = workspace.get_proof_dependencies(result_id)
        assert (
            dependencies["known"]["resolved_local_results"][0]["result_id"]
            == "local:pdf-paper::pdf:lemma:1.2"
        )
        assert dependencies["known"]["external_result_mentions"][0][
            "external_number"
        ] == "3.5"
    finally:
        workspace.close()


def test_reimport_pdf_replaces_old_evidence_atomically(tmp_path: Path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    write_math_pdf(first)
    write_math_pdf(second)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(first, "local:pdf-paper")
        workspace.import_pdf(second, "local:pdf-paper")

        papers = workspace.list_papers()
        assert len(papers) == 1
        assert papers[0]["source_ref"] == str(second.resolve())
        assert len(workspace.list_results()) == 2
    finally:
        workspace.close()
