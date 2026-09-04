from pathlib import Path

import fitz
import pytest

from papergraph.workspace import Workspace


def write_slice_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2.",
        "Remark 1.3. Extra comment.",
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


def test_get_source_slice_by_proof_id_is_bounded(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        result = workspace.get_source_slice(
            proof_id="local:paper::proof:1",
            context=1,
        )

        assert result["selector"] == {
            "kind": "proof_id",
            "value": "local:paper::proof:1",
        }
        assert result["paper_id"] == "local:paper"
        assert result["bounded"] is True
        assert [item["role"] for item in result["slices"]] == [
            "before",
            "anchor",
            "after",
        ]
        texts = [item["text"] for item in result["slices"]]
        assert "Theorem 1.1. Main result." in texts
        assert "Proof. By Lemma 1.2." in texts
        assert "Remark 1.3. Extra comment." in texts
        assert "Lemma 1.2. Base estimate." not in texts
    finally:
        workspace.close()


def test_export_reading_bundle_maps_pdf_evidence_to_ai4math_like_entities(
    tmp_path: Path,
):
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        bundle = workspace.export_reading_bundle("local:paper")

        assert bundle["bridge_schema_version"] == "1"
        assert bundle["paper"]["paper_id"] == "local:paper"
        assert bundle["uri_map"]["paper_uri"] == "paper:local:paper"
        assert "local:paper::pdf:theorem:1.1" in bundle["uri_map"][
            "papergraph_to_reading"
        ]
        theorem = next(
            entity for entity in bundle["entities"] if entity["label"] == "Theorem 1.1"
        )
        assert theorem["type"] == "THEOREM"
        assert theorem["dependencies"] == ["Lemma 1.2"]
        assert theorem["proof_methods"][0]["association_basis"] == (
            "immediately_follows_result"
        )
        assert bundle["interpretation_policy"]["proof_gap_filling"] == (
            "requires_bounded_source_slice"
        )
    finally:
        workspace.close()


def test_export_result_reading_context_includes_source_slice_handles(
    tmp_path: Path,
):
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        context = workspace.export_result_reading_context(
            "local:paper::pdf:theorem:1.1"
        )

        assert context["result"]["result_id"] == "local:paper::pdf:theorem:1.1"
        assert context["proof"]["known"]["proof"]["proof_id"] == (
            "local:paper::proof:1"
        )
        assert context["dependencies"]["known"]["resolved_local_results"][0][
            "result_id"
        ] == "local:paper::pdf:lemma:1.2"
        assert {
            "kind": "proof_id",
            "value": "local:paper::proof:1",
            "paper_id": "local:paper",
            "role": "proof",
        } in context["source_slice_handles"]
        assert "proof_gap_filling" in context["interpretation_prompts"]["allowed"]
    finally:
        workspace.close()


def test_get_result_reading_path_returns_top_down_and_bottom_up(tmp_path: Path):
    pdf = tmp_path / "recursive.pdf"
    write_recursive_dependency_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        path = workspace.get_result_reading_path(
            "local:paper::pdf:theorem:1.3",
            recursive=True,
        )

        assert [node["result_id"] for node in path["top_down"]] == [
            "local:paper::pdf:theorem:1.3",
            "local:paper::pdf:lemma:1.2",
            "local:paper::pdf:lemma:1.1",
        ]
        assert [node["result_id"] for node in path["bottom_up"]] == [
            "local:paper::pdf:lemma:1.1",
            "local:paper::pdf:lemma:1.2",
            "local:paper::pdf:theorem:1.3",
        ]
        assert path["external_stops"] == []
        assert path["cycles"] == []
    finally:
        workspace.close()


def test_get_source_slice_requires_exactly_one_selector(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(ValueError, match="Exactly one source slice selector"):
            workspace.get_source_slice()
        with pytest.raises(ValueError, match="Exactly one source slice selector"):
            workspace.get_source_slice(span_id="span", proof_id="proof")
    finally:
        workspace.close()


def test_get_source_slice_rejects_invalid_context(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(
            ValueError,
            match="context must be an integer from 0 through 5",
        ):
            workspace.get_source_slice(span_id="span", context=6)
    finally:
        workspace.close()
