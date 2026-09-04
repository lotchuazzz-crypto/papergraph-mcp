# PaperGraph v0.5 Evidence Graph v1 and PDF Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Evidence Graph v1 so PaperGraph can import born-digital PDFs, store page/span proof evidence, and query TeX/PDF results through one source-agnostic workspace API.

**Architecture:** Add a protocol-independent evidence domain model, a local PyMuPDF-backed PDF text extractor, deterministic text heuristics for result/proof/citation evidence, and schema v3 workspace storage. Keep the existing v0.4 theorem/citation tables and MCP tools compatible while adding new workspace-prefixed evidence tools.

**Tech Stack:** Python 3.10+, SQLite via `sqlite3`, PyMuPDF via `fitz`, existing `pybtex>=0.25,<0.27`, MCP Python SDK 2.x, httpx, pytest, uv, GitHub Actions on Windows/Linux and Python 3.10/3.12.

## Global Constraints

- The target release is `0.5.0` / `v0.5.0`.
- Existing v0.4.4 behavior and tests must remain compatible.
- Do not create tags, publish releases, merge PRs, delete branches, or change unrelated clones without explicit user approval.
- Support `source_type='pdf'` for explicit local PDF imports.
- Only support born-digital PDFs in v0.5; scanned PDF OCR is excluded.
- Do not use LLM-only result, proof, or dependency extraction.
- Do not automatically download cited papers.
- Do not perform semantic theorem equivalence or proof verification.
- Do not use Crossref, Semantic Scholar, OpenAlex, MathSciNet, zbMATH, arbitrary web lookup, or live network tests.
- Every public MCP result for Evidence Graph v1 must be traceable to stored source spans.
- Every dependency-like response must separate `known`, `inferred`, `unresolved`, and `warnings`.
- Empty proof dependencies are not evidence that the proof has no dependencies.
- PDF extraction confidence is an extraction confidence, not a mathematical truth score.
- A failed paper import must leave the previous stored version of that paper intact.
- The complete deterministic suite must pass with `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`.

---

## Planned File Structure

- Create `src/papergraph/evidence.py`: source-agnostic dataclasses, ID helpers, confidence validation, and payload serialization.
- Create `src/papergraph/pdf.py`: local PDF path validation and PyMuPDF page/block/span extraction.
- Create `src/papergraph/evidence_extractors.py`: deterministic heading, proof, bibliography, local mention, citation mention, and external result mention heuristics.
- Modify `src/papergraph/models.py`: add workspace import counts for evidence records while preserving current dataclasses.
- Modify `src/papergraph/parser.py`: add a TeX-to-evidence adapter over existing theorem nodes.
- Modify `src/papergraph/workspace.py`: schema v3, v2 migration, evidence storage, PDF import, and evidence query APIs.
- Modify `src/papergraph/server.py`: MCP adapters for PDF import and evidence queries.
- Modify `pyproject.toml` and `uv.lock`: add `PyMuPDF>=1.24,<2` and bump package version to `0.5.0`.
- Modify `README.md`: document v0.5 PDF and proof-evidence workflows.
- Create `tests/test_evidence.py`: evidence model and serialization tests.
- Create `tests/test_pdf.py`: PDF text extraction tests.
- Create `tests/test_evidence_extractors.py`: result/proof/mention/bibliography heuristic tests.
- Create `tests/test_workspace_evidence.py`: schema v3, migration, evidence storage, and query tests.
- Create `tests/test_pdf_workspace_server.py`: MCP tool behavior for PDF/evidence APIs.
- Modify existing workspace/server/parser tests where needed for schema version and counts.

## Task 1: Evidence Domain Model

**Files:**
- Create: `src/papergraph/evidence.py`
- Create: `tests/test_evidence.py`

**Interfaces:**
- Produces: `EVIDENCE_EMPTY_DEPENDENCY_WARNING: str`
- Produces: `EvidenceError(ValueError)`
- Produces: `confidence(value: float) -> float`
- Produces: `bounded_excerpt(text: str, limit: int = 240) -> str`
- Produces: `slug_fragment(value: str) -> str`
- Produces: `evidence_result_id(paper_id: str, local_id: str) -> str`
- Produces: `evidence_pdf_result_local_id(kind: str, visible_number: str | None, ordinal: int) -> str`
- Produces: `source_span_payload(span: SourceSpanEvidence) -> dict`
- Produces dataclasses: `SourceSpanEvidence`, `ResultEvidence`, `ProofEvidence`, `BibliographyEntryEvidence`, `LocalResultMentionEvidence`, `CitationMentionEvidence`, `ExternalResultMentionEvidence`, `EvidenceEdge`, `EvidenceDocument`.

- [ ] **Step 1: Write failing evidence tests**

Create `tests/test_evidence.py`:

```python
import pytest

from papergraph.evidence import (
    BibliographyEntryEvidence,
    CitationMentionEvidence,
    EvidenceDocument,
    ExternalResultMentionEvidence,
    LocalResultMentionEvidence,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
    bounded_excerpt,
    confidence,
    evidence_pdf_result_local_id,
    evidence_result_id,
    slug_fragment,
    source_span_payload,
)


def test_confidence_accepts_numeric_range():
    assert confidence(0) == 0.0
    assert confidence(0.75) == 0.75
    assert confidence(1) == 1.0


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "1"])
def test_confidence_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="confidence"):
        confidence(value)


def test_bounded_excerpt_normalizes_whitespace_and_limits_text():
    text = "  A\\n\\t proof   with   spaces.  " + "x" * 300
    excerpt = bounded_excerpt(text, limit=30)
    assert excerpt == "A proof with spaces. xxxxxxxxx..."
    assert len(excerpt) == 30


def test_slug_fragment_is_deterministic_and_lowercase():
    assert slug_fragment("Theorem 1.2 / Main Result") == "theorem-1.2-main-result"
    assert slug_fragment("   ") == "item"


def test_evidence_result_ids_reuse_global_theorem_id_shape():
    assert evidence_result_id("local:paper-a", "thm:main") == "local:paper-a::thm:main"
    assert evidence_pdf_result_local_id("Theorem", "1.2", 3) == "pdf:theorem:1.2"
    assert evidence_pdf_result_local_id("Remark", None, 4) == "pdf:remark:4"


def test_source_span_payload_preserves_pdf_location():
    span = SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=2,
        block_index=5,
        start_offset=10,
        end_offset=24,
        bbox=(1.0, 2.0, 3.0, 4.0),
        text="Lemma 2.1. Base.",
        method="pdf_text_block",
        confidence=1.0,
    )

    assert source_span_payload(span) == {
        "span_id": None,
        "paper_id": "local:paper-a",
        "source_type": "pdf",
        "source_ref": "paper.pdf",
        "page": 2,
        "block_index": 5,
        "start_offset": 10,
        "end_offset": 24,
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "excerpt": "Lemma 2.1. Base.",
        "method": "pdf_text_block",
        "confidence": 1.0,
    }


def test_evidence_document_groups_records():
    document = EvidenceDocument(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        source_version=None,
        title=None,
        authors=(),
        main_file="paper.pdf",
        spans=(SourceSpanEvidence(
            paper_id="local:paper-a",
            source_type="pdf",
            source_ref="paper.pdf",
            page=1,
            block_index=0,
            start_offset=0,
            end_offset=19,
            bbox=None,
            text="Theorem 1.1. Main.",
            method="pdf_text_block",
            confidence=1.0,
        ),),
        results=(ResultEvidence(
            result_id="local:paper-a::pdf:theorem:1.1",
            paper_id="local:paper-a",
            local_id="pdf:theorem:1.1",
            kind="theorem",
            raw_kind="Theorem",
            display_kind="Theorem",
            normalized_kind="theorem",
            label=None,
            visible_number="1.1",
            title=None,
            statement="Theorem 1.1. Main.",
            span_indices=(0,),
            method="pdf_heading_regex",
            confidence=0.9,
        ),),
        proofs=(ProofEvidence(
            proof_id="local:paper-a::proof:1",
            paper_id="local:paper-a",
            result_id="local:paper-a::pdf:theorem:1.1",
            text="Proof. By Lemma 1.2.",
            span_indices=(0,),
            association_basis="immediately_follows_result",
            association_confidence=0.75,
            method="pdf_proof_heading",
            confidence=0.85,
        ),),
        bibliography_entries=(BibliographyEntryEvidence(
            entry_id="local:paper-a::bib:12",
            paper_id="local:paper-a",
            raw_label="12",
            raw_text="[12] A. Author, A cited paper, arXiv:2401.12345.",
            entry_type="numeric",
            title=None,
            authors=(),
            year=None,
            arxiv_id="2401.12345",
            arxiv_version=None,
            doi=None,
            url=None,
            method="pdf_bibliography_regex",
            confidence=0.8,
        ),),
        local_result_mentions=(LocalResultMentionEvidence(
            mention_id="local:paper-a::local-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            raw_text="Lemma 1.2",
            kind="lemma",
            visible_number="1.2",
            target_result_id=None,
            resolution_status="unresolved",
            method="proof_local_result_regex",
            confidence=0.8,
        ),),
        citation_mentions=(CitationMentionEvidence(
            mention_id="local:paper-a::citation-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            raw_text="[12]",
            raw_key="12",
            entry_id="local:paper-a::bib:12",
            resolution_status="resolved_unique",
            method="proof_citation_regex",
            confidence=0.85,
        ),),
        external_result_mentions=(ExternalResultMentionEvidence(
            mention_id="local:paper-a::external-mention:1",
            paper_id="local:paper-a",
            proof_id="local:paper-a::proof:1",
            citation_mention_id="local:paper-a::citation-mention:1",
            raw_text="[12, Theorem 3.5]",
            external_kind="theorem",
            external_number="3.5",
            entry_id="local:paper-a::bib:12",
            target_paper_id=None,
            resolution_status="resolved_bibliography_entry",
            method="external_result_regex",
            confidence=0.8,
        ),),
        edges=(),
        warnings=("empty proof dependencies are not evidence of no dependencies",),
    )

    assert document.paper_id == "local:paper-a"
    assert document.results[0].span_indices == (0,)
    assert document.warnings == ("empty proof dependencies are not evidence of no dependencies",)
```

- [ ] **Step 2: Run the evidence tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evidence.py -q -p no:cacheprovider
```

Expected: collection fails with `ModuleNotFoundError: No module named 'papergraph.evidence'`.

- [ ] **Step 3: Implement `src/papergraph/evidence.py`**

Create `src/papergraph/evidence.py` with frozen, slotted dataclasses matching the test constructors. Use `papergraph.identity.global_theorem_id` inside `evidence_result_id`. Validate confidence in each dataclass `__post_init__` by calling `confidence`.

Implementation requirements:

```python
EVIDENCE_EMPTY_DEPENDENCY_WARNING = (
    "No proof-local dependencies were detected from explicit evidence. "
    "This is not evidence that the proof has no mathematical dependencies."
)
```

`bounded_excerpt` must normalize all whitespace with `" ".join(text.split())`, return the full normalized string if it fits, and return `normalized[: limit - 3] + "..."` when truncation is needed.

`slug_fragment` must lowercase, keep ASCII letters, digits, `.`, `_`, and `-`, convert other runs to `-`, strip surrounding `-`, and return `"item"` for an empty slug.

`evidence_pdf_result_local_id` must return `pdf:<normalized-kind>:<visible-number>` when `visible_number` exists and `pdf:<normalized-kind>:<ordinal>` otherwise.

- [ ] **Step 4: Run the evidence tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evidence.py -q -p no:cacheprovider
```

Expected: `6 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/papergraph/evidence.py tests/test_evidence.py
git commit -m "feat: add evidence graph domain records"
```

## Task 2: PDF Text Extraction

**Files:**
- Create: `src/papergraph/pdf.py`
- Create: `tests/test_pdf.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: `SourceSpanEvidence`
- Produces: `PdfExtractionError(ValueError)`
- Produces: `PdfPage(page: int, text: str, blocks: tuple[PdfTextBlock, ...])`
- Produces: `PdfTextBlock(page: int, block_index: int, text: str, bbox: tuple[float, float, float, float] | None)`
- Produces: `extract_pdf_pages(path: str | Path) -> tuple[PdfPage, ...]`
- Produces: `pdf_pages_to_spans(paper_id: str, source_ref: str, pages: tuple[PdfPage, ...]) -> tuple[SourceSpanEvidence, ...]`
- Produces: `load_pdf_evidence_spans(path: str | Path, paper_id: str) -> tuple[SourceSpanEvidence, ...]`

- [ ] **Step 1: Add PyMuPDF dependency**

Modify `pyproject.toml` dependencies:

```toml
dependencies = [
    "httpx>=0.27,<1",
    "mcp[cli]>=2,<3",
    "pybtex>=0.25,<0.27",
    "PyMuPDF>=1.24,<2",
]
```

Run:

```powershell
uv lock
```

Expected: `uv.lock` updates and contains a `pymupdf` package entry.

- [ ] **Step 2: Write failing PDF extraction tests**

Create `tests/test_pdf.py`:

```python
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
```

- [ ] **Step 3: Run the PDF tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pdf.py -q -p no:cacheprovider
```

Expected before implementation: collection fails with `ModuleNotFoundError: No module named 'papergraph.pdf'`.

- [ ] **Step 4: Implement `src/papergraph/pdf.py`**

Create `src/papergraph/pdf.py`. Use `import fitz`. Path rules:

```python
resolved = Path(path).expanduser().resolve()
if not resolved.exists(): raise PdfExtractionError(f"PDF file does not exist: {resolved}")
if not resolved.is_file(): raise PdfExtractionError(f"PDF path is not a file: {resolved}")
if resolved.suffix.lower() != ".pdf": raise PdfExtractionError("PaperGraph PDF import only accepts .pdf files")
```

Extraction rules:

- Open with `fitz.open(resolved)`.
- Reject `document.needs_pass` with `PdfExtractionError("Encrypted PDFs are not supported")`.
- For each page, call `page.get_text("blocks")`.
- Use only text blocks whose text normalizes to a non-empty string.
- Sort blocks by `(round(y0, 1), round(x0, 1), block_index)`.
- Store page numbers as one-based integers.
- Join page block text with `"\n"`.
- If all pages have no non-empty text, raise `PdfExtractionError("PDF contains no born-digital text; scanned/OCR PDFs are not supported")`.
- `pdf_pages_to_spans` converts each block into `SourceSpanEvidence` with `source_type="pdf"`, `source_ref`, page, block index, bbox, start/end offsets over block text, method `pdf_text_block`, confidence `1.0`.

- [ ] **Step 5: Run PDF tests and a focused full import smoke**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pdf.py tests/test_evidence.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add pyproject.toml uv.lock src/papergraph/pdf.py tests/test_pdf.py
git commit -m "feat: extract born-digital pdf spans"
```

## Task 3: Result, Proof, Mention, and Bibliography Extractors

**Files:**
- Create: `src/papergraph/evidence_extractors.py`
- Create: `tests/test_evidence_extractors.py`

**Interfaces:**
- Consumes: `SourceSpanEvidence`, `ResultEvidence`, `ProofEvidence`, `BibliographyEntryEvidence`, `LocalResultMentionEvidence`, `CitationMentionEvidence`, `ExternalResultMentionEvidence`, `EvidenceDocument`
- Produces: `build_pdf_evidence_document(paper_id: str, source_ref: str, spans: tuple[SourceSpanEvidence, ...], title: str | None = None, authors: tuple[str, ...] = ()) -> EvidenceDocument`
- Produces: `extract_result_blocks(...)`, `extract_proof_blocks(...)`, `extract_bibliography_entries(...)`, `extract_local_result_mentions(...)`, `extract_citation_mentions(...)`, `extract_external_result_mentions(...)`

- [ ] **Step 1: Write failing extractor tests**

Create `tests/test_evidence_extractors.py`:

```python
from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document


def span(index: int, text: str) -> SourceSpanEvidence:
    return SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=1,
        block_index=index,
        start_offset=0,
        end_offset=len(text),
        bbox=None,
        text=text,
        method="pdf_text_block",
        confidence=1.0,
    )


def test_extracts_results_and_proofs_with_unique_local_resolution():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Lemma 1.2. Base estimate."),
            span(1, "Theorem 1.1. Main result."),
            span(2, "Proof. By Lemma 1.2, the claim follows."),
        ),
    )

    assert [result.local_id for result in document.results] == [
        "pdf:lemma:1.2",
        "pdf:theorem:1.1",
    ]
    theorem = document.results[1]
    proof = document.proofs[0]
    assert theorem.result_id == "local:paper-a::pdf:theorem:1.1"
    assert proof.result_id == theorem.result_id
    assert proof.association_basis == "immediately_follows_result"
    assert document.local_result_mentions[0].raw_text == "Lemma 1.2"
    assert document.local_result_mentions[0].target_result_id == "local:paper-a::pdf:lemma:1.2"
    assert document.local_result_mentions[0].resolution_status == "resolved_unique"


def test_extracts_explicit_proof_of_number_association():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Theorem 1.1. Main result."),
            span(1, "Lemma 1.2. Base estimate."),
            span(2, "Proof of Theorem 1.1. We use Lemma 1.2."),
        ),
    )

    proof = document.proofs[0]
    assert proof.result_id == "local:paper-a::pdf:theorem:1.1"
    assert proof.association_basis == "proof_heading_names_result"


def test_ambiguous_local_mentions_remain_visible():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Lemma 1.2. First."),
            span(1, "Lemma 1.2. Second."),
            span(2, "Theorem 1.3. Main."),
            span(3, "Proof. By Lemma 1.2."),
        ),
    )

    mention = document.local_result_mentions[0]
    assert mention.target_result_id is None
    assert mention.resolution_status == "ambiguous"


def test_extracts_numeric_bibliography_and_external_result_mentions():
    document = build_pdf_evidence_document(
        "local:paper-a",
        "paper.pdf",
        (
            span(0, "Theorem 1.1. Main result."),
            span(1, "Proof. We apply [12, Theorem 3.5]."),
            span(2, "References"),
            span(3, "[12] A. Author. Cited paper. arXiv:2401.12345v2. doi:10.1000/example"),
        ),
    )

    assert document.bibliography_entries[0].raw_label == "12"
    assert document.bibliography_entries[0].arxiv_id == "2401.12345"
    assert document.bibliography_entries[0].arxiv_version == "v2"
    assert document.bibliography_entries[0].doi == "10.1000/example"
    citation = document.citation_mentions[0]
    assert citation.raw_text == "[12, Theorem 3.5]"
    assert citation.entry_id == "local:paper-a::bib:12"
    external = document.external_result_mentions[0]
    assert external.external_kind == "theorem"
    assert external.external_number == "3.5"
    assert external.entry_id == "local:paper-a::bib:12"
    assert external.resolution_status == "resolved_bibliography_entry"
```

- [ ] **Step 2: Run extractor tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evidence_extractors.py -q -p no:cacheprovider
```

Expected: collection fails with `ModuleNotFoundError: No module named 'papergraph.evidence_extractors'`.

- [ ] **Step 3: Implement heading and proof extraction**

Create `src/papergraph/evidence_extractors.py`.

Required regex behavior:

```python
RESULT_RE = re.compile(r"^(?P<raw>Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|Example|Remark)\s+(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?)\.?\s*(?P<body>.*)$", re.I)
PROOF_RE = re.compile(r"^Proof(?:\s+of\s+(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim)\s+(?P<number>[A-Za-z]?(?:\d+(?:\.\d+)*|[A-Z])?))?\.?\s*(?P<body>.*)$", re.I)
```

Implementation rules:

- Iterate spans in source order.
- Before bibliography starts, create one result per `RESULT_RE` span.
- Treat the whole matching span text as the v0.5 statement.
- Use `evidence_pdf_result_local_id` and append `:<collision-ordinal>` only if another result already used the same local ID.
- Create `ResultEvidence` with `method="pdf_heading_regex"` and `confidence=0.85`.
- A proof with explicit `Proof of Theorem 1.1` resolves by `(kind, visible_number)` and uses `association_basis="proof_heading_names_result"` and `association_confidence=0.95`.
- A bare `Proof.` associates to the nearest preceding result when no other proof is already associated to it and uses `association_basis="immediately_follows_result"` and `association_confidence=0.75`.
- Unassociated proof blocks are preserved with `result_id=None`, `association_basis="unresolved"`, and `association_confidence=0.0`.

- [ ] **Step 4: Implement mention and bibliography extraction**

Required behavior:

- Bibliography starts at a span whose normalized text is exactly `references` or `bibliography`, case-insensitive.
- Numeric entries match `^\[(?P<label>[^\]]+)\]\s*(?P<body>.+)$`.
- Entry IDs use `f"{paper_id}::bib:{slug_fragment(label)}"`.
- Extract arXiv IDs with the same valid forms accepted by `papergraph.arxiv.normalize_arxiv_id`; preserve version separately.
- Extract DOI from `doi:` or `https://doi.org/` text, stopping before whitespace.
- Extract URL from `http://` or `https://`, stopping before whitespace.
- Local result mentions inside proof text match visible references like `Lemma 1.2`, `Theorem A`, `Corollary 5.2`; resolve only when exactly one result in the same paper has matching normalized kind and visible number.
- Citation mentions match bracket forms like `[12]`, `[12, Theorem 3.5]`, and `[HM10, Theorem B]`.
- External result mentions are created only when a citation mention includes a result kind and number.

- [ ] **Step 5: Run extractor tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evidence_extractors.py tests/test_evidence.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src/papergraph/evidence_extractors.py tests/test_evidence_extractors.py
git commit -m "feat: extract proof evidence from pdf text"
```

## Task 4: Workspace Schema v3 and Evidence Storage

**Files:**
- Modify: `src/papergraph/workspace.py`
- Modify: `src/papergraph/models.py`
- Create: `tests/test_workspace_evidence.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/test_workspace_server.py`

**Interfaces:**
- Consumes: `EvidenceDocument`
- Produces: `SCHEMA_VERSION = 3`
- Produces: `Workspace.import_evidence_document(document: EvidenceDocument) -> WorkspaceImportResult`
- Produces: `Workspace.list_results(paper_id: str | None = None, kind: str | None = None, limit: int = 50) -> list[dict]`
- Produces: `Workspace.get_result(result_id: str) -> dict`
- Produces: `Workspace.get_result_proof(result_id: str) -> dict`
- Produces: `Workspace.get_proof_dependencies(result_id: str, recursive: bool = False) -> dict`
- Produces: `Workspace.get_external_result_mentions(result_id: str) -> list[dict]`
- Produces: `Workspace.get_evidence(node_or_edge_id: str) -> dict`

- [ ] **Step 1: Write failing schema and query tests**

Create `tests/test_workspace_evidence.py` with tests that:

```python
import sqlite3
from pathlib import Path

from papergraph.evidence import (
    EvidenceDocument,
    LocalResultMentionEvidence,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
)
from papergraph.workspace import SCHEMA_VERSION, Workspace


def simple_document() -> EvidenceDocument:
    span = SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=1,
        block_index=0,
        start_offset=0,
        end_offset=45,
        bbox=None,
        text="Theorem 1.1. Main. Proof. By Lemma 1.2.",
        method="pdf_text_block",
        confidence=1.0,
    )
    result = ResultEvidence(
        result_id="local:paper-a::pdf:theorem:1.1",
        paper_id="local:paper-a",
        local_id="pdf:theorem:1.1",
        kind="theorem",
        raw_kind="Theorem",
        display_kind="Theorem",
        normalized_kind="theorem",
        label=None,
        visible_number="1.1",
        title=None,
        statement="Theorem 1.1. Main.",
        span_indices=(0,),
        method="pdf_heading_regex",
        confidence=0.85,
    )
    proof = ProofEvidence(
        proof_id="local:paper-a::proof:1",
        paper_id="local:paper-a",
        result_id=result.result_id,
        text="Proof. By Lemma 1.2.",
        span_indices=(0,),
        association_basis="immediately_follows_result",
        association_confidence=0.75,
        method="pdf_proof_heading",
        confidence=0.85,
    )
    mention = LocalResultMentionEvidence(
        mention_id="local:paper-a::local-mention:1",
        paper_id="local:paper-a",
        proof_id=proof.proof_id,
        raw_text="Lemma 1.2",
        kind="lemma",
        visible_number="1.2",
        target_result_id=None,
        resolution_status="unresolved",
        method="proof_local_result_regex",
        confidence=0.8,
    )
    return EvidenceDocument(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        source_version=None,
        title="PDF Paper",
        authors=("Ada Lovelace",),
        main_file="paper.pdf",
        spans=(span,),
        results=(result,),
        proofs=(proof,),
        bibliography_entries=(),
        local_result_mentions=(mention,),
        citation_mentions=(),
        external_result_mentions=(),
        edges=(),
        warnings=(),
    )


def test_schema_v3_initializes_evidence_tables(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        tables = {
            row[0]
            for row in workspace._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"source_spans", "results", "proofs", "local_result_mentions", "evidence_edges"} <= tables
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("3",)
    finally:
        workspace.close()


def test_import_evidence_document_and_query_result_proof_dependencies(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result = workspace.import_evidence_document(simple_document())
        assert result.paper_id == "local:paper-a"
        assert result.theorem_count == 1

        listed = workspace.list_results()
        assert listed[0]["result_id"] == "local:paper-a::pdf:theorem:1.1"
        assert listed[0]["source_type"] == "pdf"
        assert listed[0]["first_location"]["page"] == 1

        full = workspace.get_result("local:paper-a::pdf:theorem:1.1")
        assert full["statement"] == "Theorem 1.1. Main."
        assert full["spans"][0]["page"] == 1

        proof = workspace.get_result_proof("local:paper-a::pdf:theorem:1.1")
        assert proof["known"]["proof"]["proof_id"] == "local:paper-a::proof:1"
        assert proof["inferred"][0]["basis"] == "immediately_follows_result"

        dependencies = workspace.get_proof_dependencies("local:paper-a::pdf:theorem:1.1")
        assert dependencies["known"]["resolved_local_results"] == []
        assert dependencies["unresolved"]["local_result_mentions"][0]["raw_text"] == "Lemma 1.2"
        assert dependencies["warnings"]
    finally:
        workspace.close()


def test_v2_workspace_migrates_without_losing_legacy_tables(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            '''
            CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL CHECK (source_type IN ('local', 'arxiv')),
                source_ref TEXT NOT NULL,
                source_version TEXT,
                title TEXT,
                authors_json TEXT NOT NULL,
                main_file TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                parser_version TEXT NOT NULL
            );
            CREATE TABLE theorems (
                global_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
                local_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                raw_kind TEXT NOT NULL,
                display_kind TEXT NOT NULL,
                normalized_kind TEXT NOT NULL,
                title TEXT,
                label TEXT,
                content TEXT NOT NULL,
                source_file TEXT,
                position INTEGER NOT NULL,
                UNIQUE (paper_id, local_id)
            );
            CREATE TABLE theorem_refs (
                source_global_id TEXT NOT NULL REFERENCES theorems(global_id) ON DELETE CASCADE,
                ref_label TEXT NOT NULL,
                target_global_id TEXT REFERENCES theorems(global_id) ON DELETE CASCADE,
                PRIMARY KEY (source_global_id, ref_label)
            );
            CREATE TABLE citation_evidence (
                id INTEGER PRIMARY KEY,
                source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
                citation_key TEXT NOT NULL,
                command TEXT NOT NULL,
                source_file TEXT NOT NULL,
                bib_file TEXT,
                bib_entry_type TEXT,
                cited_arxiv_id TEXT,
                cited_version TEXT,
                target_paper_id TEXT REFERENCES papers(paper_id) ON DELETE SET NULL,
                resolution_status TEXT NOT NULL
            );
            INSERT INTO workspace_meta VALUES ('schema_version', '2');
            INSERT INTO papers VALUES ('local:old', 'local', 'main.tex', NULL, NULL, '[]', 'main.tex', '2026-09-03T00:00:00+00:00', '0.4.4');
            INSERT INTO theorems VALUES ('local:old::thm:main', 'local:old', 'thm:main', 'theorem', 'theorem', 'theorem', 'theorem', NULL, 'thm:main', 'Main.', 'main.tex', 0);
            '''
        )

    workspace = Workspace.open(path)
    try:
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("3",)
        assert workspace.get_paper("local:old")["paper_id"] == "local:old"
    finally:
        workspace.close()
```

- [ ] **Step 2: Run schema tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider
```

Expected: failures show `SCHEMA_VERSION == 2` and missing evidence APIs.

- [ ] **Step 3: Update schema initialization and migration**

Modify `src/papergraph/workspace.py`:

- Set `SCHEMA_VERSION = 3`.
- Update `_SCHEMA_SQL` so `papers.source_type` accepts `'local', 'arxiv', 'pdf'`.
- Add all evidence tables from the design with foreign keys and deterministic indexes.
- Teach `_initialize_or_validate_schema` to call `_migrate_v2_to_v3(connection)` when metadata version is `2`.
- `_migrate_v2_to_v3` must run in one transaction, rebuild `papers` with the expanded `CHECK`, create evidence tables, preserve all existing rows, and update `workspace_meta` to `3`.
- Extend `_REQUIRED_TABLES` and table-column validation for evidence tables.

- [ ] **Step 4: Add `Workspace.import_evidence_document`**

Implementation rules:

- Normalize `document.paper_id` using `normalize_paper_id`.
- Accept `source_type` in `{"local", "arxiv", "pdf"}`.
- For `source_type == "pdf"`, require the paper ID prefix to be `local:` in v0.5.
- Delete the existing row from `papers` for that paper ID inside the transaction, relying on cascading deletes.
- Insert `papers`, `source_spans`, `results`, result-span links, `proofs`, proof-span links, bibliography entries, mentions, external mentions, edges, and edge-span links.
- Maintain an in-memory map from document span tuple index to inserted integer span ID.
- Return `WorkspaceImportResult` with `theorem_count=len(document.results)`, `citation_count=len(document.citation_mentions)`, and `unresolved_citation_count` equal to unresolved local, citation, and external mentions.

- [ ] **Step 5: Add evidence query methods**

Implement:

- `list_results`: validate `limit` as integer 1 through 100; optionally filter normalized paper ID and kind; order by `paper_id, result_id`.
- `get_result`: include result metadata, statement, confidence, and span payloads.
- `get_result_proof`: return `{"known": {"proof": ...}, "inferred": [...], "unresolved": {}, "warnings": [...]}` when proof exists; return `{"known": {}, "inferred": [], "unresolved": {"proof": "not_found"}, "warnings": [...]}` when absent.
- `get_proof_dependencies`: include resolved local targets under `known`, proof association under `inferred`, unresolved local/citation/external mentions under `unresolved`, and `EVIDENCE_EMPTY_DEPENDENCY_WARNING` when no resolved local or external mentions exist.
- `get_external_result_mentions`: return external mention rows for the associated proof.
- `get_evidence`: accept IDs from result, proof, mention, bibliography, edge; return source spans and metadata.

- [ ] **Step 6: Update existing schema tests**

Modify existing assertions in `tests/test_workspace.py` and `tests/test_workspace_server.py`:

- Expected schema version becomes `3`.
- Required table sets include evidence tables.
- Existing v0.4 workspace tool payloads remain exactly the same except `schema_version`.

- [ ] **Step 7: Run workspace tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add src/papergraph/workspace.py src/papergraph/models.py tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py
git commit -m "feat: persist evidence graph workspace records"
```

## Task 5: TeX Evidence Adapter

**Files:**
- Modify: `src/papergraph/parser.py`
- Modify: `src/papergraph/workspace.py`
- Create: `tests/test_tex_evidence_adapter.py`
- Modify: `tests/test_workspace_evidence.py`

**Interfaces:**
- Consumes: `LoadedProject`, `parse_project(project) -> list[TheoremNode]`
- Produces: `latex_project_to_evidence_document(paper_id: str, source_type: str, source_ref: str, source_version: str | None, project: LoadedProject) -> EvidenceDocument`
- Updates: `Workspace.import_project(...)` writes legacy v0.4 rows and evidence v1 rows in the same transaction.

- [ ] **Step 1: Write failing TeX adapter tests**

Create `tests/test_tex_evidence_adapter.py`:

```python
from pathlib import Path

from papergraph.parser import latex_project_to_evidence_document
from papergraph.project import load_project


def test_latex_project_to_evidence_document_maps_theorems_to_results(tmp_path: Path):
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
```

- [ ] **Step 2: Run TeX adapter tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tex_evidence_adapter.py -q -p no:cacheprovider
```

Expected: import fails because `latex_project_to_evidence_document` does not exist.

- [ ] **Step 3: Implement TeX adapter in `parser.py`**

Implementation rules:

- Call `parse_project(project)`.
- For each node, find the `project.spans` entry containing `node.position`.
- Create one `SourceSpanEvidence` per theorem node with `source_type="tex"`, relative `source_ref`, `start_offset=node.position`, `end_offset=node.position + len(node.content)`, text `node.content`, method `latex_environment`, confidence `1.0`.
- Create `ResultEvidence` with `result_id=global_theorem_id(paper_id, node.id)`, `local_id=node.id`, kind metadata from `TheoremNode`, label, title, statement `node.content`, span index, method `latex_environment`, confidence `1.0`.
- Leave proofs and mentions empty for TeX in v0.5 unless a later task explicitly adds proof parsing.

- [ ] **Step 4: Update `Workspace.import_project` to store TeX evidence**

Implementation rules:

- Preserve all existing legacy table behavior and payloads.
- In the same transaction that inserts `papers`, `theorems`, `theorem_refs`, and `citation_evidence`, also insert evidence tables from `latex_project_to_evidence_document`.
- Avoid deleting/reinserting `papers` twice. Factor shared insertion into a private `_insert_evidence_document(connection, document)` helper that assumes the paper row already exists when called from `import_project`.

- [ ] **Step 5: Add workspace assertion that TeX imports appear in `list_results`**

Extend `tests/test_workspace_evidence.py`:

```python
def test_latex_import_populates_source_agnostic_results(workspace, loaded_project):
    workspace.import_project("local:paper-a", "local", "main.tex", None, loaded_project)

    results = workspace.list_results()

    assert [item["result_id"] for item in results] == [
        "local:paper-a::lem:base",
        "local:paper-a::thm:main",
    ]
    assert results[0]["source_type"] == "local"
```

- [ ] **Step 6: Run parser and workspace tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_parser.py tests/test_tex_evidence_adapter.py tests/test_workspace.py tests/test_workspace_evidence.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add src/papergraph/parser.py src/papergraph/workspace.py tests/test_tex_evidence_adapter.py tests/test_workspace_evidence.py
git commit -m "feat: adapt latex imports to evidence graph"
```

## Task 6: PDF Workspace Import

**Files:**
- Modify: `src/papergraph/workspace.py`
- Create: `tests/test_pdf_workspace.py`

**Interfaces:**
- Consumes: `load_pdf_evidence_spans`, `build_pdf_evidence_document`, `Workspace.import_evidence_document`
- Produces: `Workspace.import_pdf(path: str | Path, paper_id: str) -> WorkspaceImportResult`

- [ ] **Step 1: Write failing PDF workspace tests**

Create `tests/test_pdf_workspace.py`:

```python
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
        assert dependencies["known"]["resolved_local_results"][0]["result_id"] == "local:pdf-paper::pdf:lemma:1.2"
        assert dependencies["known"]["external_result_mentions"][0]["external_number"] == "3.5"
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
```

- [ ] **Step 2: Run PDF workspace tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pdf_workspace.py -q -p no:cacheprovider
```

Expected: failures show `Workspace` has no `import_pdf`.

- [ ] **Step 3: Implement `Workspace.import_pdf`**

Implementation rules:

- Resolve path and call `load_pdf_evidence_spans(path, normalized_paper_id)`.
- Build an `EvidenceDocument` with `build_pdf_evidence_document`.
- Set `source_ref` to the absolute resolved PDF path.
- Set `main_file` to the PDF filename.
- Use `source_type="pdf"` and `source_version=None`.
- Call `import_evidence_document`.
- Reject non-`local:` PDF paper IDs with `ValueError("PDF paper ids must use the local: prefix in v0.5")`.

- [ ] **Step 4: Run PDF workspace and evidence tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pdf.py tests/test_evidence_extractors.py tests/test_pdf_workspace.py tests/test_workspace_evidence.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 6**

Run:

```powershell
git add src/papergraph/workspace.py tests/test_pdf_workspace.py
git commit -m "feat: import pdf papers into workspace"
```

## Task 7: MCP Evidence Tools

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_pdf_workspace_server.py`
- Modify: `tests/test_workspace_server.py`

**Interfaces:**
- Consumes: workspace evidence APIs from Tasks 4 and 6
- Produces MCP tools:
  - `workspace_add_pdf_paper(path: str, paper_id: str) -> dict`
  - `workspace_list_results(paper_id: str | None = None, kind: str | None = None, limit: int = 50) -> list[dict]`
  - `workspace_get_result(result_id: str) -> dict`
  - `workspace_get_result_proof(result_id: str) -> dict`
  - `workspace_get_proof_dependencies(result_id: str, recursive: bool = False) -> dict`
  - `workspace_get_external_result_mentions(result_id: str) -> list[dict]`
  - `workspace_get_evidence(node_or_edge_id: str) -> dict`

- [ ] **Step 1: Write failing MCP server tests**

Create `tests/test_pdf_workspace_server.py`:

```python
import asyncio
import json
from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def call_mcp_tool(name: str, arguments: dict):
    return asyncio.run(server.mcp.call_tool(name, arguments))


def result_json(result):
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


def write_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2 and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


@pytest.mark.parametrize(
    "call",
    [
        lambda pdf: server.workspace_add_pdf_paper(str(pdf), "local:paper"),
        lambda pdf: server.workspace_list_results(),
        lambda pdf: server.workspace_get_result("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_result_proof("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_proof_dependencies("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_external_result_mentions("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_evidence("local:paper::pdf:theorem:1.1"),
    ],
)
def test_evidence_tools_report_missing_workspace(tmp_path: Path, call):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    with pytest.raises(ToolError, match="open_workspace"):
        call(pdf)


def test_pdf_evidence_mcp_workflow(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    imported = server.workspace_add_pdf_paper(str(pdf), "local:paper")
    assert imported["paper_id"] == "local:paper"
    assert imported["source_type"] == "pdf"
    assert imported["result_count"] == 2

    results = server.workspace_list_results()
    assert [item["result_id"] for item in results] == [
        "local:paper::pdf:lemma:1.2",
        "local:paper::pdf:theorem:1.1",
    ]

    result = server.workspace_get_result("local:paper::pdf:theorem:1.1")
    assert result["spans"][0]["page"] == 1

    proof = server.workspace_get_result_proof("local:paper::pdf:theorem:1.1")
    assert proof["known"]["proof"]["result_id"] == "local:paper::pdf:theorem:1.1"

    dependencies = server.workspace_get_proof_dependencies("local:paper::pdf:theorem:1.1")
    assert dependencies["known"]["resolved_local_results"][0]["visible_number"] == "1.2"
    assert dependencies["known"]["external_result_mentions"][0]["external_number"] == "3.5"

    evidence = server.workspace_get_evidence("local:paper::pdf:theorem:1.1")
    assert evidence["node_or_edge_id"] == "local:paper::pdf:theorem:1.1"
    assert evidence["spans"][0]["page"] == 1


def test_pdf_evidence_tool_errors_are_translated(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="PDF"):
        server.workspace_add_pdf_paper(str(tmp_path / "missing.pdf"), "local:paper")


def test_mcp_dispatch_for_new_tools(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    call_mcp_tool("open_workspace", {"path": str(tmp_path / "workspace.sqlite3")})
    imported = call_mcp_tool("workspace_add_pdf_paper", {"path": str(pdf), "paper_id": "local:paper"})

    assert result_json(imported)["paper_id"] == "local:paper"
    listed = call_mcp_tool("workspace_list_results", {})
    assert result_json(listed)[0]["paper_id"] == "local:paper"
```

- [ ] **Step 2: Run MCP tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pdf_workspace_server.py -q -p no:cacheprovider
```

Expected: failures show missing `server.workspace_add_pdf_paper` and missing registered MCP tools.

- [ ] **Step 3: Implement server adapters**

Implementation rules:

- Extend `_WORKSPACE_TOOL_ERRORS` to include `PdfExtractionError`.
- Each new tool must be decorated with `@mcp.tool()` and `@_serialized_workspace_tool`.
- Each tool must call `require_workspace()` and delegate directly to the matching `Workspace` method.
- `workspace_add_pdf_paper` returns `workspace.get_paper(result.paper_id)` plus evidence import counts: `result_count`, `proof_count`, `bibliography_entry_count`, `local_mention_count`, `external_mention_count`, `unresolved_count`, and `warnings` when available.
- Error translation must mirror existing workspace tools: domain errors become `ToolError(str(exc))`; programming errors are not swallowed.

- [ ] **Step 4: Run all server tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_server.py tests/test_workspace_server.py tests/test_pdf_workspace_server.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 7**

Run:

```powershell
git add src/papergraph/server.py tests/test_pdf_workspace_server.py tests/test_workspace_server.py
git commit -m "feat: expose pdf evidence workspace tools"
```

## Task 8: Documentation, Version, and Repository Checks

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/papergraph/__init__.py`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_readme_local_workspace_walkthrough.py`
- Create or modify: focused README tests as needed

**Interfaces:**
- Consumes: all public MCP tool names and payload semantics
- Produces: README guidance for v0.5 PDF import, proof evidence, known/inferred/unresolved semantics, and limitations.

- [ ] **Step 1: Write failing documentation tests**

Add assertions to existing repository/readme tests:

```python
def test_readme_documents_pdf_evidence_workflow():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "workspace_add_pdf_paper" in readme
    assert "workspace_get_proof_dependencies" in readme
    assert "known" in readme
    assert "inferred" in readme
    assert "unresolved" in readme
    assert "scanned PDFs" in readme or "scanned PDF" in readme
    assert "does not verify proofs" in readme
```

If `src/papergraph/__init__.py` contains a version constant, add or update a test requiring `0.5.0`.

- [ ] **Step 2: Run documentation tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Expected: README assertion fails before documentation updates.

- [ ] **Step 3: Update README**

Required README changes:

- Opening paragraph mentions v0.5 PDF import and evidence-first proof logic.
- Tools table includes `workspace_add_pdf_paper`, `workspace_list_results`, `workspace_get_result`, `workspace_get_result_proof`, `workspace_get_proof_dependencies`, `workspace_get_external_result_mentions`, and `workspace_get_evidence`.
- Add a compact PDF workflow:

```text
open_workspace(path="C:/Temp/papergraph-pdf.sqlite3")
workspace_add_pdf_paper(path="C:/Papers/example.pdf", paper_id="local:example")
workspace_list_results(paper_id="local:example")
workspace_get_result_proof(result_id="local:example::pdf:theorem:1.1")
workspace_get_proof_dependencies(result_id="local:example::pdf:theorem:1.1")
```

- Add wording that dependency responses split `known`, `inferred`, `unresolved`, and `warnings`.
- Limitations include scanned PDFs/OCR, proof verification, semantic matching, automatic cited-paper download, and recursive literature tracing.
- Safety/privacy section states local PDFs remain local and extracted text is stored in the user-chosen SQLite workspace.

- [ ] **Step 4: Bump version metadata**

Modify `pyproject.toml`:

```toml
version = "0.5.0"
```

If `src/papergraph/__init__.py` has a version string, set it to `0.5.0`. If it only exports package metadata, leave it alone and do not invent a duplicate version source.

- [ ] **Step 5: Run documentation and repository tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 8**

Run:

```powershell
git add README.md pyproject.toml src/papergraph/__init__.py tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py
git commit -m "docs: document pdf proof evidence workflow"
```

## Task 9: Full Verification and Polish

**Files:**
- Modify only files touched by earlier tasks if verification exposes a defect.

**Interfaces:**
- Consumes: all implementation tasks
- Produces: passing deterministic suite and final implementation readiness notes.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Expected: all tests pass. The exact count may increase from the v0.4.4 baseline because this plan adds new evidence and PDF tests.

- [ ] **Step 2: Run package version smoke**

Run:

```powershell
.\.venv\Scripts\python.exe -m papergraph.server --version
```

Expected output includes:

```text
papergraph-mcp 0.5.0
```

- [ ] **Step 3: Run focused CLI safety smoke**

Run:

```powershell
.\.venv\Scripts\python.exe -m papergraph.server validate-arxiv-request "[math/0307200](https://arxiv.org/abs/2609.01574)"
```

Expected JSON includes:

```json
{
  "status": "conflict",
  "action": "ask_user_to_choose",
  "selected_id": null
}
```

- [ ] **Step 4: Run git diff checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` prints nothing. `git status --short` shows only intentional implementation files before the final commit or nothing after the final commit.

- [ ] **Step 5: Fix verification defects with focused tests**

If a verification defect appears, write or adjust the narrowest failing test that captures the defect, implement the fix, then rerun:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Expected: all tests pass before final readiness.

- [ ] **Step 6: Commit final verification fixes if any**

If Step 5 changed files, run:

```powershell
git add src/papergraph/evidence.py src/papergraph/pdf.py src/papergraph/evidence_extractors.py src/papergraph/workspace.py src/papergraph/server.py src/papergraph/parser.py src/papergraph/models.py src/papergraph/__init__.py pyproject.toml uv.lock README.md tests/test_evidence.py tests/test_pdf.py tests/test_evidence_extractors.py tests/test_workspace_evidence.py tests/test_tex_evidence_adapter.py tests/test_pdf_workspace.py tests/test_pdf_workspace_server.py tests/test_workspace.py tests/test_workspace_server.py tests/test_parser.py tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py
git commit -m "test: verify evidence graph pdf workflow"
```

If Step 5 changed no files, skip this commit.

## Self-Review Checklist

- Spec coverage: Tasks 1-8 cover evidence model, PDF import, source spans, theorem/proof/citation extraction, TeX/PDF unification, conservative proof dependencies, MCP tools, README, and verification.
- Scope check: Recursive cited-paper import, scanned OCR, semantic theorem matching, proof verification, and main theorem ranking remain excluded.
- Type consistency: Public names are stable across tasks: `EvidenceDocument`, `SourceSpanEvidence`, `ResultEvidence`, `ProofEvidence`, `workspace_add_pdf_paper`, `workspace_list_results`, `workspace_get_result`, `workspace_get_result_proof`, `workspace_get_proof_dependencies`, `workspace_get_external_result_mentions`, and `workspace_get_evidence`.
- No network tests: all PDF fixtures are generated locally with PyMuPDF.
- Compatibility: existing v0.4 tools are preserved, and schema v3 migration is explicitly tested.
