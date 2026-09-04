"""PDF text extraction helpers for born-digital PaperGraph sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from papergraph.evidence import SourceSpanEvidence


class PdfExtractionError(ValueError):
    """Raised when a PDF cannot be converted into text evidence spans."""


@dataclass(frozen=True, slots=True)
class PdfTextBlock:
    page: int
    block_index: int
    text: str
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True, slots=True)
class PdfPage:
    page: int
    text: str
    blocks: tuple[PdfTextBlock, ...]


def extract_pdf_pages(path: str | Path) -> tuple[PdfPage, ...]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise PdfExtractionError(f"PDF file does not exist: {resolved}")
    if not resolved.is_file():
        raise PdfExtractionError(f"PDF path is not a file: {resolved}")
    if resolved.suffix.lower() != ".pdf":
        raise PdfExtractionError("PaperGraph PDF import only accepts .pdf files")

    document = fitz.open(resolved)
    try:
        if document.needs_pass:
            raise PdfExtractionError("Encrypted PDFs are not supported")

        pages: list[PdfPage] = []
        for page_index, page in enumerate(document, start=1):
            blocks = _extract_text_blocks(page, page_index)
            pages.append(
                PdfPage(
                    page=page_index,
                    text="\n".join(block.text for block in blocks),
                    blocks=tuple(blocks),
                )
            )
    finally:
        document.close()

    if all(not page.text for page in pages):
        raise PdfExtractionError(
            "PDF contains no born-digital text; scanned/OCR PDFs are not supported"
        )
    return tuple(pages)


def pdf_pages_to_spans(
    paper_id: str, source_ref: str, pages: tuple[PdfPage, ...]
) -> tuple[SourceSpanEvidence, ...]:
    spans: list[SourceSpanEvidence] = []
    for page in pages:
        for block in page.blocks:
            spans.append(
                SourceSpanEvidence(
                    paper_id=paper_id,
                    source_type="pdf",
                    source_ref=source_ref,
                    page=page.page,
                    block_index=block.block_index,
                    start_offset=0,
                    end_offset=len(block.text),
                    bbox=block.bbox,
                    text=block.text,
                    method="pdf_text_block",
                    confidence=1.0,
                )
            )
    return tuple(spans)


def load_pdf_evidence_spans(
    path: str | Path, paper_id: str
) -> tuple[SourceSpanEvidence, ...]:
    resolved = Path(path).expanduser().resolve()
    pages = extract_pdf_pages(resolved)
    return pdf_pages_to_spans(paper_id, str(resolved), pages)


def _extract_text_blocks(page: fitz.Page, page_number: int) -> list[PdfTextBlock]:
    blocks: list[PdfTextBlock] = []
    for block_index, raw_block in enumerate(page.get_text("blocks")):
        if len(raw_block) < 5:
            continue
        text = str(raw_block[4]).strip()
        if not text:
            continue
        x0, y0, x1, y1 = raw_block[:4]
        blocks.append(
            PdfTextBlock(
                page=page_number,
                block_index=block_index,
                text=text,
                bbox=(float(x0), float(y0), float(x1), float(y1)),
            )
        )
    return sorted(
        blocks,
        key=lambda block: (
            round(block.bbox[1], 1) if block.bbox is not None else 0.0,
            round(block.bbox[0], 1) if block.bbox is not None else 0.0,
            block.block_index,
        ),
    )
