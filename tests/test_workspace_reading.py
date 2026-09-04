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
