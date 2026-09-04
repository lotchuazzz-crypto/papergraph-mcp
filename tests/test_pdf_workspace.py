from pathlib import Path

import fitz
import pytest

from papergraph.evidence import EVIDENCE_EMPTY_DEPENDENCY_WARNING
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


def write_external_only_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Theorem 1.1. Main result.",
        "Proof. We apply [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345v2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def write_recursive_dependency_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.1. Base estimate.",
        "Proof. This is direct.",
        "Lemma 1.2. Bootstrap estimate.",
        "Proof. By Lemma 1.1.",
        "Theorem 1.3. Main result.",
        "Proof. By Lemma 1.2.",
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
        assert paper["source_ref"] == str(pdf.resolve())
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
        via_mentions = dependencies["known"]["resolved_local_results"][0][
            "via_mentions"
        ]
        assert via_mentions[0]["mention_id"] == "local:pdf-paper::local-mention:1"
        assert via_mentions[0]["raw_text"] == "Lemma 1.2"
        assert via_mentions[0]["spans"][0]["source_ref"] == str(pdf.resolve())
        assert via_mentions[0]["span_trail"] == [
            {
                "evidence_id": "local:pdf-paper::proof:1",
                "evidence_type": "proof",
                "relation": "parent_proof",
            }
        ]
    finally:
        workspace.close()


def test_pdf_recursive_dependencies_follow_resolved_unique_local_mentions(
    tmp_path: Path,
):
    pdf = tmp_path / "recursive.pdf"
    write_recursive_dependency_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:pdf-paper")

        dependencies = workspace.get_proof_dependencies(
            "local:pdf-paper::pdf:theorem:1.3",
            recursive=True,
        )

        assert [
            result["result_id"]
            for result in dependencies["known"]["resolved_local_results"]
        ] == [
            "local:pdf-paper::pdf:lemma:1.2",
            "local:pdf-paper::pdf:lemma:1.1",
        ]
    finally:
        workspace.close()


def test_bibliography_backed_external_mentions_count_as_known_dependencies(
    tmp_path: Path,
):
    pdf = tmp_path / "external-only.pdf"
    write_external_only_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        imported = workspace.import_pdf(pdf, "local:pdf-paper")
        assert imported.unresolved_citation_count == 0

        dependencies = workspace.get_proof_dependencies(
            "local:pdf-paper::pdf:theorem:1.1"
        )
        assert EVIDENCE_EMPTY_DEPENDENCY_WARNING not in dependencies["warnings"]
        assert dependencies["known"]["resolved_local_results"] == []
        assert dependencies["known"]["resolved_external_results"] == []
        external_mentions = dependencies["known"]["external_result_mentions"]
        assert len(external_mentions) == 1
        assert external_mentions[0]["external_number"] == "3.5"
        assert external_mentions[0]["resolution_status"] == (
            "resolved_bibliography_entry"
        )
        assert dependencies["unresolved"]["external_result_mentions"] == []
    finally:
        workspace.close()


def test_import_pdf_rejects_non_local_paper_ids(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_math_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(
            ValueError,
            match="PDF paper ids must use the local: prefix in v0.5",
        ):
            workspace.import_pdf(pdf, "arxiv:2401.12345")
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
