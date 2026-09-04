# PaperGraph Reading Bridge v0.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic Reading Bridge exports that let AI4Math-Paper-Reading consume PaperGraph evidence without making PaperGraph responsible for natural-language explanation.

**Architecture:** Add a focused `papergraph.reading` helper module for URI mapping, AI4Math-like entity shaping, source-slice shaping, and reading-path assembly. Add small `Workspace` methods that query existing schema v3 tables and delegate payload shaping to the helper. Expose those methods through MCP wrappers and document the workflow.

**Tech Stack:** Python 3.11+, dataclass/dict payloads, SQLite workspace schema v3, MCPServer tools, pytest, PyMuPDF test fixtures already used by PDF tests.

## Global Constraints

- `bridge_schema_version` is `"1"`.
- PaperGraph exports evidence and structure only; AI4Math-Paper-Reading performs interpretation.
- Do not generate `paper_summary`, natural-language theorem explanations, proof strategy summaries, or proof gap fillings inside PaperGraph.
- Do not add OCR, semantic theorem matching, automatic cited-paper download, or proof verification.
- `workspace_get_source_slice` requires exactly one selector among `span_id`, `result_id`, and `proof_id`.
- `workspace_get_source_slice.context` is an integer from 0 through 5.
- Source slices must be bounded and must not return an unrelated full-paper dump.
- Consumers display bridge reading URIs but call PaperGraph tools with PaperGraph IDs.

---

## File Structure

- Create `src/papergraph/reading.py`: deterministic bridge constants and pure helpers.
- Modify `src/papergraph/workspace.py`: add source-span lookup methods and bridge export methods.
- Modify `src/papergraph/server.py`: expose MCP tools for the four new workspace methods.
- Create `tests/test_reading.py`: pure helper tests.
- Create `tests/test_workspace_reading.py`: workspace method tests using PDF fixtures and custom evidence documents.
- Create `tests/test_workspace_reading_server.py`: MCP wrapper smoke and error conversion tests.
- Modify `README.md`: add Reading Bridge workflow and boundary notes.

---

### Task 1: Reading Helper Contracts

**Files:**
- Create: `src/papergraph/reading.py`
- Test: `tests/test_reading.py`

**Interfaces:**
- Produces: `BRIDGE_SCHEMA_VERSION: str`
- Produces: `base_bridge_payload(papergraph_version: str) -> dict`
- Produces: `reading_paper_uri(paper_id: str) -> str`
- Produces: `reading_result_uri(paper_id: str, display_kind: str, visible_number: str | None, local_id: str) -> str`
- Produces: `result_to_reading_entity(result: dict, dependencies: dict, source_handles: list[dict]) -> dict`
- Produces: `source_handle(kind: str, value: str, paper_id: str, role: str) -> dict`

- [ ] **Step 1: Write failing pure helper tests**

```python
from papergraph.reading import (
    BRIDGE_SCHEMA_VERSION,
    base_bridge_payload,
    reading_paper_uri,
    reading_result_uri,
    result_to_reading_entity,
    source_handle,
)


def test_base_bridge_payload_declares_evidence_boundary():
    payload = base_bridge_payload("0.6.0")

    assert payload["bridge_schema_version"] == BRIDGE_SCHEMA_VERSION == "1"
    assert payload["papergraph_version"] == "0.6.0"
    assert payload["source_policy"] == {
        "facts_from": "papergraph_evidence_graph",
        "interpretation_from": "consumer",
        "proof_verification": False,
        "semantic_matching": False,
    }
    assert payload["warnings"] == []


def test_reading_result_uri_uses_visible_number_and_kind_abbreviation():
    assert (
        reading_result_uri("local:paper", "Theorem", "1.1", "pdf:theorem:1.1")
        == "paper:local:paper#Thm-1.1"
    )


def test_reading_result_uri_falls_back_to_slugged_local_id():
    assert (
        reading_result_uri("local:paper", "Remark", None, "pdf:remark:2")
        == "paper:local:paper#Rem-pdf-remark-2"
    )


def test_source_handle_is_selector_payload():
    assert source_handle("proof_id", "local:paper::proof:1", "local:paper", "proof") == {
        "kind": "proof_id",
        "value": "local:paper::proof:1",
        "paper_id": "local:paper",
        "role": "proof",
    }


def test_result_to_reading_entity_maps_known_and_unresolved_dependencies():
    result = {
        "result_id": "local:paper::pdf:theorem:1.1",
        "paper_id": "local:paper",
        "local_id": "pdf:theorem:1.1",
        "display_kind": "Theorem",
        "visible_number": "1.1",
        "label": None,
        "statement": "Theorem 1.1. Main result.",
        "method": "pdf_heading_regex",
        "confidence": 0.85,
    }
    dependencies = {
        "known": {
            "resolved_local_results": [
                {
                    "result_id": "local:paper::pdf:lemma:1.2",
                    "display_kind": "Lemma",
                    "visible_number": "1.2",
                    "local_id": "pdf:lemma:1.2",
                    "paper_id": "local:paper",
                }
            ],
            "external_result_mentions": [
                {
                    "raw_text": "[12, Theorem 3.5]",
                    "external_kind": "Theorem",
                    "external_number": "3.5",
                    "resolution_status": "resolved_bibliography_entry",
                }
            ],
        },
        "unresolved": {
            "local_result_mentions": [
                {
                    "raw_text": "Lemma 9.9",
                    "resolution_status": "unresolved",
                }
            ],
            "citation_mentions": [],
            "external_result_mentions": [],
        },
    }

    entity = result_to_reading_entity(
        result,
        dependencies,
        [source_handle("result_id", result["result_id"], "local:paper", "statement")],
    )

    assert entity["type"] == "THEOREM"
    assert entity["label"] == "Theorem 1.1"
    assert entity["statement"] == "Theorem 1.1. Main result."
    assert entity["dependencies"] == ["Lemma 1.2"]
    assert entity["uncertain_dependencies"] == ["Lemma 9.9 [UNCERTAIN: unresolved]"]
    assert entity["external_refs"] == ["[12, Theorem 3.5] [EXTERNAL: resolved_bibliography_entry]"]
    assert entity["source_handles"][0]["kind"] == "result_id"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_reading.py -q`

Expected: FAIL because `papergraph.reading` does not exist.

- [ ] **Step 3: Implement helper module**

Create `src/papergraph/reading.py` with pure functions for bridge metadata, kind abbreviations, slug fallback, dependency labels, external refs, and source handles.

- [ ] **Step 4: Run helper tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_reading.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/papergraph/reading.py tests/test_reading.py
git commit -m "feat: add reading bridge helpers"
```

---

### Task 2: Bounded Source Slice Workspace API

**Files:**
- Modify: `src/papergraph/workspace.py`
- Test: `tests/test_workspace_reading.py`

**Interfaces:**
- Consumes: `source_handle(...)`
- Produces: `Workspace.get_source_slice(span_id: str | None = None, result_id: str | None = None, proof_id: str | None = None, context: int = 1) -> dict`

- [ ] **Step 1: Write failing workspace source-slice tests**

```python
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
        "References",
        "[1] A. Author. Cited paper.",
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
        assert "[1] A. Author. Cited paper." not in texts
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
        with pytest.raises(ValueError, match="context must be an integer from 0 through 5"):
            workspace.get_source_slice(span_id="span", context=6)
    finally:
        workspace.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading.py -q`

Expected: FAIL because `Workspace.get_source_slice` does not exist.

- [ ] **Step 3: Implement `Workspace.get_source_slice`**

Add selector validation, anchor span lookup by result/proof/span ID, neighboring span lookup ordered by paper/source/page/block/id, and role assignment `before`, `anchor`, `after`.

- [ ] **Step 4: Run source-slice tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading.py -q`

Expected: PASS for the source-slice tests.

- [ ] **Step 5: Commit**

```bash
git add src/papergraph/workspace.py tests/test_workspace_reading.py
git commit -m "feat: add bounded source slice export"
```

---

### Task 3: Reading Bundle, Result Context, and Reading Path

**Files:**
- Modify: `src/papergraph/workspace.py`
- Modify: `src/papergraph/reading.py`
- Test: `tests/test_workspace_reading.py`

**Interfaces:**
- Consumes: `Workspace.get_source_slice(...) -> dict`
- Consumes: `result_to_reading_entity(...) -> dict`
- Produces: `Workspace.export_reading_bundle(paper_id: str) -> dict`
- Produces: `Workspace.export_result_reading_context(result_id: str) -> dict`
- Produces: `Workspace.get_result_reading_path(result_id: str, recursive: bool = True) -> dict`

- [ ] **Step 1: Write failing bundle/context/path tests**

```python
def test_export_reading_bundle_maps_pdf_evidence_to_ai4math_like_entities(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        bundle = workspace.export_reading_bundle("local:paper")

        assert bundle["bridge_schema_version"] == "1"
        assert bundle["paper"]["paper_id"] == "local:paper"
        assert bundle["uri_map"]["paper_uri"] == "paper:local:paper"
        assert "local:paper::pdf:theorem:1.1" in bundle["uri_map"]["papergraph_to_reading"]
        theorem = next(
            entity for entity in bundle["entities"] if entity["label"] == "Theorem 1.1"
        )
        assert theorem["type"] == "THEOREM"
        assert theorem["dependencies"] == ["Lemma 1.2"]
        assert theorem["proof_methods"][0]["association_basis"] == "immediately_follows_result"
        assert bundle["interpretation_policy"]["proof_gap_filling"] == (
            "requires_bounded_source_slice"
        )
    finally:
        workspace.close()


def test_export_result_reading_context_includes_source_slice_handles(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")

        context = workspace.export_result_reading_context(
            "local:paper::pdf:theorem:1.1"
        )

        assert context["result"]["result_id"] == "local:paper::pdf:theorem:1.1"
        assert context["proof"]["known"]["proof"]["proof_id"] == "local:paper::proof:1"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading.py -q`

Expected: FAIL because export/path methods do not exist.

- [ ] **Step 3: Implement bundle export**

Use existing workspace methods `get_paper`, `list_results`, `get_result`,
`get_result_proof`, `get_proof_dependencies`, and
`get_external_result_mentions` to build the bundle. Keep generated summaries out
of the payload and use `requires_consumer_interpretation` markers.

- [ ] **Step 4: Implement result context export**

Return one result, proof evidence, dependencies, a path preview, source slice
handles, and interpretation prompts. Missing proof must be represented as
unresolved evidence, not an exception.

- [ ] **Step 5: Implement reading path**

Use known resolved local result dependencies. Build deterministic top-down
order with cycle protection and bottom-up as the reverse acyclic path. Add
external and unresolved stop nodes from dependency payloads.

- [ ] **Step 6: Run workspace reading tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/papergraph/reading.py src/papergraph/workspace.py tests/test_workspace_reading.py
git commit -m "feat: export reading bridge bundles"
```

---

### Task 4: MCP Tools and Documentation

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_workspace_reading_server.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Workspace.export_reading_bundle(...) -> dict`
- Consumes: `Workspace.export_result_reading_context(...) -> dict`
- Consumes: `Workspace.get_source_slice(...) -> dict`
- Consumes: `Workspace.get_result_reading_path(...) -> dict`
- Produces MCP tools:
  - `workspace_export_reading_bundle(paper_id: str) -> dict`
  - `workspace_export_result_reading_context(result_id: str) -> dict`
  - `workspace_get_source_slice(span_id: str | None = None, result_id: str | None = None, proof_id: str | None = None, context: int = 1) -> dict`
  - `workspace_get_result_reading_path(result_id: str, recursive: bool = True) -> dict`

- [ ] **Step 1: Write failing MCP wrapper tests**

```python
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from tests.test_pdf_workspace import write_recursive_dependency_pdf
from tests.test_workspace_reading import write_slice_pdf


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_reading_bridge_mcp_tools_return_payloads(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    bundle = server.workspace_export_reading_bundle("local:paper")
    context = server.workspace_export_result_reading_context(
        "local:paper::pdf:theorem:1.1"
    )
    source_slice = server.workspace_get_source_slice(
        proof_id="local:paper::proof:1",
        context=1,
    )

    assert bundle["bridge_schema_version"] == "1"
    assert context["result"]["result_id"] == "local:paper::pdf:theorem:1.1"
    assert source_slice["bounded"] is True


def test_reading_path_mcp_tool_returns_recursive_path(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "recursive.pdf"
    write_recursive_dependency_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    path = server.workspace_get_result_reading_path(
        "local:paper::pdf:theorem:1.3",
        recursive=True,
    )

    assert [node["result_id"] for node in path["bottom_up"]] == [
        "local:paper::pdf:lemma:1.1",
        "local:paper::pdf:lemma:1.2",
        "local:paper::pdf:theorem:1.3",
    ]


def test_source_slice_mcp_tool_converts_errors_to_tool_error(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Exactly one source slice selector"):
        server.workspace_get_source_slice()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_server.py -q`

Expected: FAIL because MCP wrappers do not exist.

- [ ] **Step 3: Implement MCP wrappers**

Add four `@mcp.tool()` functions in `src/papergraph/server.py`, follow existing
workspace wrapper style, call `require_workspace()`, and catch
`_WORKSPACE_TOOL_ERRORS`.

- [ ] **Step 4: Update README**

Document Reading Bridge workflow:

```text
open_workspace(path="C:/Temp/papergraph-reading.sqlite3")
workspace_add_pdf_paper(path="C:/Papers/example.pdf", paper_id="local:example")
workspace_export_reading_bundle(paper_id="local:example")
workspace_export_result_reading_context(result_id="local:example::pdf:theorem:1.1")
workspace_get_source_slice(proof_id="local:example::proof:1", context=1)
workspace_get_result_reading_path(result_id="local:example::pdf:theorem:1.1", recursive=True)
```

The README must explicitly say PaperGraph exports evidence and source slices,
while AI4Math-Paper-Reading or another consumer performs explanation and proof
gap filling.

- [ ] **Step 5: Run MCP and focused README tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_server.py tests/test_readme_local_workspace_walkthrough.py -q`

Expected: PASS.

- [ ] **Step 6: Full verification**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`

Expected: all tests pass.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 7: Commit**

```bash
git add src/papergraph/server.py README.md tests/test_workspace_reading_server.py
git commit -m "feat: expose reading bridge mcp tools"
```

---

## Self-Review

- Spec coverage: the four tools, bridge schema, source-slice boundedness, URI mapping, fact/interpretation policy, AI4Math mapping, errors, tests, and README are covered by Tasks 1-4.
- Scope: OCR, semantic matching, proof verification, main-result detection, and automatic cited-paper download are explicitly excluded.
- Type consistency: helper names and workspace/MCP method names match the spec and task interfaces.
- Placeholder scan: no red-flag placeholder text remains.
