from pathlib import Path

import fitz
import pytest

from papergraph.evidence import source_span_payload
from papergraph.pdf import PdfExtractionError, extract_pdf_pages, load_pdf_evidence_spans


def write_text_pdf(path: Path, lines: list[str]) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def test_extract_pdf_pages_preserves_page_block_text_and_bbox(tmp_path: Path):
    path = tmp_path / "paper.pdf"
    write_text_pdf(path, ["Theorem 1.1. Main result.", "Proof. By Lemma 1.2."])

    pages = extract_pdf_pages(path)

    assert len(pages) == 1
    assert pages[0].page == 1
    assert "Theorem 1.1" in pages[0].text
    assert "Proof. By Lemma 1.2." in pages[0].text
    assert pages[0].blocks
    assert pages[0].blocks[0].page == 1
    assert pages[0].blocks[0].bbox is not None


def test_pdf_pages_to_spans_creates_source_locations(tmp_path: Path):
    path = tmp_path / "paper.pdf"
    write_text_pdf(path, ["Lemma 1.2. Base."])

    spans = load_pdf_evidence_spans(path, "local:paper-a")

    assert len(spans) >= 1
    payload = source_span_payload(spans[0])
    assert payload["paper_id"] == "local:paper-a"
    assert payload["source_type"] == "pdf"
    assert payload["page"] == 1
    assert payload["method"] == "pdf_text_block"
    assert "Lemma 1.2. Base." in payload["excerpt"]


@pytest.mark.parametrize("name", ["missing.pdf", "paper.tex"])
def test_rejects_missing_or_non_pdf_paths(tmp_path: Path, name: str):
    path = tmp_path / name
    if name.endswith(".tex"):
        path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PdfExtractionError):
        extract_pdf_pages(path)


def test_rejects_image_only_or_empty_text_pdf(tmp_path: Path):
    path = tmp_path / "empty.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    with pytest.raises(PdfExtractionError, match="born-digital text"):
        extract_pdf_pages(path)
