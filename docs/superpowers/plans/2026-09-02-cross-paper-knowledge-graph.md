# PaperGraph v0.4.0 Cross-Paper Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent, explainable multi-paper theorem-and-citation knowledge graph that MCP clients can query across local and arXiv LaTeX projects.

**Architecture:** Keep the current single-paper parser and MCP tools compatible, add a structured project loader and a pure citation-extraction layer, then persist paper, theorem, dependency, and citation evidence records in a versioned SQLite workspace. New workspace-prefixed MCP tools remain thin adapters over a protocol-independent `Workspace` domain API.

**Tech Stack:** Python 3.10+, SQLite via `sqlite3`, `pybtex>=0.25,<0.27`, MCP Python SDK 2.x, httpx, pytest, uv, GitHub Actions on Windows/Linux and Python 3.10/3.12.

## Global Constraints

- Preserve all existing MCP tool names, parameters, return values, and no-argument server startup behavior.
- Use paper IDs `arxiv:<base-id>` for arXiv and caller-supplied lowercase `local:<slug>` IDs for local papers.
- Use global theorem IDs `<paper_id>::<local_theorem_id>` and reject duplicate local theorem IDs during workspace import.
- Derive cross-paper edges only from explicit LaTeX/BibTeX evidence; do not use embeddings, LLMs, or semantic guesses.
- Store data locally in a versioned SQLite database with foreign keys, parameterized statements, explicit transactions, and atomic paper replacement.
- Use `pybtex>=0.25,<0.27` as the only new runtime dependency.
- Do not fetch citation metadata, recursively download citations, accept arbitrary URLs, parse PDFs, or add destructive removal tools.
- Keep CI deterministic and network-free on `ubuntu-latest` and `windows-latest`, Python `3.10` and `3.12`.
- Bound theorem search limits to 1–100 and return stable deterministic ordering.
- Do not merge `main`, create `v0.4.0`, or publish a Release during implementation without explicit user authorization.

---

## Planned file structure

- Create `src/papergraph/identity.py`: paper/global theorem ID validation and normalization.
- Create `src/papergraph/project.py`: structured LaTeX loading, file spans, safe bibliography discovery, and source metadata.
- Create `src/papergraph/citations.py`: citation-command extraction, Pybtex parsing, arXiv evidence normalization.
- Create `src/papergraph/workspace.py`: SQLite schema, transactional import, resolution, and query API.
- Modify `src/papergraph/models.py`: optional source provenance and workspace domain records.
- Modify `src/papergraph/loader.py`: preserve its public string API while exposing deterministic structured traversal to `project.py`.
- Modify `src/papergraph/parser.py`: parse structured projects and associate theorem nodes with source files.
- Modify `src/papergraph/server.py`: add workspace state and MCP adapters without changing existing tools.
- Create `tests/test_identity.py`, `tests/test_project.py`, `tests/test_citations.py`, `tests/test_workspace.py`, and `tests/test_workspace_server.py`.
- Create `tests/fixtures/workspace/`: three synthetic papers and BibTeX resources for deterministic integration tests.
- Modify `tests/test_repository.py`, `README.md`, `pyproject.toml`, and `uv.lock` for v0.4.0 documentation and packaging.

### Task 1: Stable paper and theorem identities

**Files:**
- Create: `src/papergraph/identity.py`
- Modify: `src/papergraph/models.py`
- Create: `tests/test_identity.py`

**Interfaces:**
- Produces: `normalize_paper_id(value: str) -> str`
- Produces: `paper_id_from_arxiv(arxiv_id: str) -> tuple[str, str | None]`
- Produces: `global_theorem_id(paper_id: str, local_id: str) -> str`
- Produces: `split_global_theorem_id(value: str) -> tuple[str, str]`
- Produces: `PaperRecord`, `CitationRecord`, and `WorkspaceImportResult` dataclasses used by later tasks.

- [ ] **Step 1: Write failing identity tests**

```python
import pytest

from papergraph.identity import (
    global_theorem_id,
    normalize_paper_id,
    paper_id_from_arxiv,
    split_global_theorem_id,
)


@pytest.mark.parametrize("value", ["local:my-preprint", "arxiv:2401.12345"])
def test_normalizes_valid_paper_ids(value):
    assert normalize_paper_id(value) == value


@pytest.mark.parametrize("value", ["paper", "local:UPPER", "local:two words", "arxiv:bad"])
def test_rejects_invalid_paper_ids(value):
    with pytest.raises(ValueError, match="Invalid paper id"):
        normalize_paper_id(value)


def test_arxiv_identity_ignores_version_but_preserves_it():
    assert paper_id_from_arxiv("2401.12345v3") == ("arxiv:2401.12345", "v3")


def test_round_trips_global_theorem_id():
    value = global_theorem_id("local:paper-a", "thm:main")
    assert value == "local:paper-a::thm:main"
    assert split_global_theorem_id(value) == ("local:paper-a", "thm:main")
```

- [ ] **Step 2: Run the identity tests and verify collection fails**

Run: `uv run pytest tests/test_identity.py -q -p no:cacheprovider`

Expected: FAIL with `ModuleNotFoundError: No module named 'papergraph.identity'`.

- [ ] **Step 3: Implement identities and workspace records**

```python
# src/papergraph/identity.py
import re

from papergraph.arxiv import normalize_arxiv_id

_LOCAL_RE = re.compile(r"local:[a-z0-9]+(?:[._-][a-z0-9]+)*")
_ARXIV_PAPER_RE = re.compile(r"arxiv:(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})", re.I)
_VERSION_RE = re.compile(r"(?P<base>.+?)(?P<version>v[1-9]\d*)?$")


def normalize_paper_id(value: str) -> str:
    normalized = value.strip()
    if _LOCAL_RE.fullmatch(normalized) or _ARXIV_PAPER_RE.fullmatch(normalized):
        return normalized.lower()
    raise ValueError(f"Invalid paper id: {value!r}")


def paper_id_from_arxiv(arxiv_id: str) -> tuple[str, str | None]:
    normalized = normalize_arxiv_id(arxiv_id)
    match = _VERSION_RE.fullmatch(normalized)
    assert match is not None
    base = match.group("base")
    version = match.group("version")
    return normalize_paper_id(f"arxiv:{base}"), version


def global_theorem_id(paper_id: str, local_id: str) -> str:
    paper_id = normalize_paper_id(paper_id)
    if not local_id or "::" in local_id:
        raise ValueError(f"Invalid local theorem id: {local_id!r}")
    return f"{paper_id}::{local_id}"


def split_global_theorem_id(value: str) -> tuple[str, str]:
    try:
        paper_id, local_id = value.split("::", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid global theorem id: {value!r}") from exc
    global_theorem_id(paper_id, local_id)
    return normalize_paper_id(paper_id), local_id
```

Add these exact frozen, slotted records to `models.py`, and add
`source_file: str | None = None` to `TheoremNode` after `position` so existing
keyword construction and payloads remain compatible:

```python
@dataclass(frozen=True, slots=True)
class PaperRecord:
    paper_id: str
    source_type: str
    source_ref: str
    source_version: str | None
    title: str | None
    authors: tuple[str, ...]
    main_file: str
    imported_at: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class CitationRecord:
    citation_key: str
    command: str
    source_file: str
    bib_file: str | None
    bib_entry_type: str | None
    cited_arxiv_id: str | None
    cited_version: str | None
    resolution_status: str


@dataclass(frozen=True, slots=True)
class WorkspaceImportResult:
    paper_id: str
    theorem_count: int
    citation_count: int
    unresolved_citation_count: int
```

- [ ] **Step 4: Run identity and existing model/parser tests**

Run: `uv run pytest tests/test_identity.py tests/test_parser.py tests/test_graph.py -q -p no:cacheprovider`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```text
git add src/papergraph/identity.py src/papergraph/models.py tests/test_identity.py
git commit -m "Add global paper and theorem identities"
```

### Task 2: Structured project loading and source provenance

**Files:**
- Modify: `src/papergraph/loader.py`
- Create: `src/papergraph/project.py`
- Modify: `src/papergraph/parser.py`
- Create: `tests/test_project.py`
- Modify: `tests/test_loader.py`

**Interfaces:**
- Produces: `SourceSpan(path: Path, start: int, end: int)`
- Produces: `LoadedProject(root_file: Path, project_root: Path, text: str, spans: tuple[SourceSpan, ...], bibliography_files: tuple[Path, ...], title: str | None, authors: tuple[str, ...])`
- Produces: `load_project(main_file: str | Path) -> LoadedProject`
- Produces: `parse_project(project: LoadedProject) -> list[TheoremNode]`
- Preserves: `load_latex_project(main_file) -> str` exactly.

- [ ] **Step 1: Add failing structured-loader tests**

```python
def test_load_project_preserves_sources_and_bibliographies(tmp_path):
    main = tmp_path / "main.tex"
    section = tmp_path / "sections" / "results.tex"
    bibliography = tmp_path / "refs.bib"
    section.parent.mkdir()
    main.write_text(
        r"\title{Graph Paper}\author{Ada}\input{sections/results}"
        r"\bibliography{refs}", encoding="utf-8"
    )
    section.write_text(r"\begin{theorem}\label{thm:x}X\end{theorem}", encoding="utf-8")
    bibliography.write_text("@article{x, title={X}}", encoding="utf-8")

    project = load_project(main)

    assert project.root_file == main.resolve()
    assert project.bibliography_files == (bibliography.resolve(),)
    assert project.title == "Graph Paper"
    assert project.authors == ("Ada",)
    assert {span.path for span in project.spans} == {main.resolve(), section.resolve()}
    assert parse_project(project)[0].source_file == "sections/results.tex"
```

Add tests for `\addbibresource{refs.bib}`, omitted `.bib`, commands relative to an included file, comments, missing files, `..` traversal, escaping symlinks, and repeated includes.

- [ ] **Step 2: Run the project tests and verify failure**

Run: `uv run pytest tests/test_project.py -q -p no:cacheprovider`

Expected: FAIL because `papergraph.project` does not exist.

- [ ] **Step 3: Refactor loading without changing the string API**

Implement a private traversal result in `loader.py` that appends text fragments and `SourceSpan` records using the final expanded-text offsets. Keep cycle detection scoped to the active include chain so repeated non-cyclic includes still expand twice. Make `load_latex_project()` return only `.text` from the traversal result.

In `project.py`, add anchored patterns for uncommented `\bibliography{a,b}` and `\addbibresource{a.bib}` commands, resolve each path relative to its declaring file, append `.bib` when missing, require the resolved regular file to remain under `project_root`, and deduplicate in first-seen order. Extract the first uncommented `\title` and split `\author` content on `\and` into stripped authors.

In `parser.py`, implement:

```python
def parse_project(project: LoadedProject) -> list[TheoremNode]:
    nodes = parse_latex(project.text)
    for node in nodes:
        span = next((item for item in project.spans if item.start <= node.position < item.end), None)
        if span is not None:
            node.source_file = span.path.relative_to(project.project_root).as_posix()
    return nodes
```

Use a mutable `TheoremNode` as today; do not alter `summary()` or `full()` payloads.

- [ ] **Step 4: Run loader, project, multifile, and parser tests**

Run: `uv run pytest tests/test_loader.py tests/test_project.py tests/test_multifile.py tests/test_parser.py -q -p no:cacheprovider`

Expected: all selected tests PASS, including existing repeated-include and cycle behavior.

- [ ] **Step 5: Commit**

```text
git add src/papergraph/loader.py src/papergraph/project.py src/papergraph/parser.py tests/test_loader.py tests/test_project.py
git commit -m "Add structured LaTeX project loading"
```

### Task 3: Explainable citation extraction

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/papergraph/citations.py`
- Create: `tests/test_citations.py`

**Interfaces:**
- Consumes: `LoadedProject` from Task 2.
- Produces: `CitationUse(key: str, command: str, source_file: str, position: int)`
- Produces: `extract_citation_uses(project: LoadedProject) -> tuple[CitationUse, ...]`
- Produces: `build_citation_records(project: LoadedProject) -> tuple[CitationRecord, ...]`
- Produces resolution statuses: `resolved_candidate`, `missing_bib_entry`, `unsupported_identifier`.

- [ ] **Step 1: Add Pybtex and write failing citation tests**

Add `"pybtex>=0.25,<0.27"` to runtime dependencies and run `uv lock`.

```python
def test_extracts_supported_commands_in_source_order(project_factory):
    project = project_factory(
        body=r"\cite{one,two}\citet{three}\autocite{four}\parencite{five}\textcite{six}"
    )
    uses = extract_citation_uses(project)
    assert [(use.command, use.key) for use in uses] == [
        ("cite", "one"), ("cite", "two"), ("citet", "three"),
        ("autocite", "four"), ("parencite", "five"), ("textcite", "six"),
    ]


def test_resolves_arxiv_evidence_and_preserves_version(project_factory):
    project = project_factory(
        body=r"\cite{target}",
        bib="@article{target, eprint={2401.12345v2}, archivePrefix={arXiv}}",
    )
    record = build_citation_records(project)[0]
    assert record.cited_arxiv_id == "2401.12345"
    assert record.cited_version == "v2"
    assert record.resolution_status == "resolved_candidate"
```

Add exact tests for `arxiv`, `url`, and `note` fields; nested braces; multiline fields; commented citations; missing keys; unsupported DOI-only entries; duplicate evidence; and source-file provenance.

- [ ] **Step 2: Run citation tests and verify failure**

Run: `uv run pytest tests/test_citations.py -q -p no:cacheprovider`

Expected: FAIL because `papergraph.citations` does not exist.

- [ ] **Step 3: Implement citation extraction and BibTeX resolution**

Use one regex limited to the supported command names, split comma-separated keys, and reuse `_is_commented`. Parse every discovered file with `pybtex.database.parse_file(str(path), bib_format="bibtex")`; merge entries in bibliography order and raise `ValueError` when the same key has conflicting entries.

Normalize fields case-insensitively. Resolve an arXiv identifier in this order: `eprint` with `archivePrefix=arXiv`, `arxiv`, arXiv `/abs/` or `/pdf/` URL, then an `arXiv:` token in `note`. Call the existing `normalize_arxiv_id`, strip a terminal version into `cited_version`, and retain the normalized base ID. Emit one immutable `CitationRecord` per citation use even when several uses resolve to the same paper.

- [ ] **Step 4: Run citation and arXiv normalization tests**

Run: `uv run pytest tests/test_citations.py tests/test_arxiv.py -q -p no:cacheprovider`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```text
git add pyproject.toml uv.lock src/papergraph/citations.py tests/test_citations.py
git commit -m "Extract explainable BibTeX citations"
```

### Task 4: Versioned SQLite workspace and atomic imports

**Files:**
- Create: `src/papergraph/workspace.py`
- Create: `tests/test_workspace.py`

**Interfaces:**
- Consumes: identity functions, `LoadedProject`, parsed theorem nodes, and citation records.
- Produces: `Workspace.open(path: str | Path) -> Workspace`
- Produces: `Workspace.close() -> None`
- Produces: `Workspace.import_project(paper_id: str, source_type: str, source_ref: str, source_version: str | None, project: LoadedProject) -> WorkspaceImportResult`
- Produces: `Workspace.counts() -> dict[str, int]`
- Uses schema version `1` and the five tables defined in the design.

- [ ] **Step 1: Write failing persistence and transaction tests**

```python
def test_workspace_persists_across_connections(tmp_path, loaded_project):
    path = tmp_path / "papers.sqlite3"
    workspace = Workspace.open(path)
    result = workspace.import_project("local:paper-a", "local", "paper-a/main.tex", None, loaded_project)
    workspace.close()

    reopened = Workspace.open(path)
    assert reopened.counts() == {"papers": 1, "theorems": result.theorem_count}


def test_import_rejects_duplicate_local_ids_without_replacing_old_data(
    workspace, loaded_project, duplicate_label_project
):
    workspace.import_project("local:paper-a", "local", "first.tex", None, loaded_project)
    with pytest.raises(DuplicateTheoremIdError, match="thm:duplicate"):
        workspace.import_project("local:paper-a", "local", "broken.tex", None, duplicate_label_project)
    assert workspace.get_paper("local:paper-a").source_ref == "first.tex"
```

Add tests for schema creation, newer schema rejection, foreign keys, colliding labels across different papers, non-ASCII content, rollback on an injected SQL failure, and atomic replacement.

- [ ] **Step 2: Run workspace tests and verify failure**

Run: `uv run pytest tests/test_workspace.py -q -p no:cacheprovider`

Expected: FAIL because `papergraph.workspace` does not exist.

- [ ] **Step 3: Implement the schema and import transaction**

Create `Workspace` around one `sqlite3.Connection`, enable
`PRAGMA foreign_keys = ON`, and initialize schema version 1 with this SQL:

```sql
CREATE TABLE workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
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
CREATE INDEX theorems_paper_kind ON theorems(paper_id, kind);
CREATE INDEX citations_source ON citation_evidence(source_paper_id);
CREATE INDEX citations_target ON citation_evidence(target_paper_id);
CREATE INDEX citations_arxiv ON citation_evidence(cited_arxiv_id);
```

Insert `('schema_version', '1')` into `workspace_meta` on a new database.

`Workspace.open()` must resolve the file, create only its parent directory, reject directory paths, validate `schema_version`, and close its new connection on failure. `import_project()` must parse the project before starting SQL mutation, validate duplicate local IDs, build global IDs, then use `with self._connection:` to delete/reinsert only the selected paper. Store JSON authors with `ensure_ascii=False`. Insert unresolved theorem references with a null target. Return counts for the imported paper, resolved candidate citations, and unresolved citations.

- [ ] **Step 4: Run persistence tests and the existing graph suite**

Run: `uv run pytest tests/test_workspace.py tests/test_graph.py tests/test_multifile.py -q -p no:cacheprovider`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```text
git add src/papergraph/workspace.py tests/test_workspace.py
git commit -m "Add persistent multi-paper workspace"
```

### Task 5: Resolve citation edges and implement workspace queries

**Files:**
- Modify: `src/papergraph/workspace.py`
- Modify: `tests/test_workspace.py`

**Interfaces:**
- Produces: `list_papers() -> list[dict]`
- Produces: `get_paper(paper_id: str) -> dict`
- Produces: `search_theorems(query: str, paper_id: str | None = None, kind: str | None = None, limit: int = 20) -> list[dict]`
- Produces: `get_dependencies(global_id: str, recursive: bool = False) -> list[dict]`
- Produces: `get_citations(paper_id: str, direction: str = "outgoing", include_unresolved: bool = True) -> list[dict]`

- [ ] **Step 1: Add failing multi-paper query tests**

```python
def test_resolves_citation_when_target_arrives_later(workspace, paper_a, paper_b):
    workspace.import_project("local:paper-a", "local", "a/main.tex", None, paper_a)
    assert workspace.get_citations("local:paper-a")[0]["target_paper_id"] is None
    workspace.import_project("arxiv:2401.12345", "arxiv", "2401.12345", None, paper_b)
    assert workspace.get_citations("local:paper-a")[0]["target_paper_id"] == "arxiv:2401.12345"


def test_searches_theorems_across_papers(workspace, three_paper_workspace):
    results = workspace.search_theorems("compactness", limit=20)
    assert [item["global_id"] for item in results] == sorted(
        item["global_id"] for item in results
    )
    assert {item["paper_id"] for item in results} == {
        "local:paper-a", "arxiv:2401.12345"
    }
```

Add tests for paper counts, incoming/outgoing direction, unresolved reasons, multiple evidence rows per edge, filters, empty queries, limit bounds, unknown IDs, recursive dependency cycles, and deterministic order.

- [ ] **Step 2: Run focused query tests and verify failure**

Run: `uv run pytest tests/test_workspace.py -q -p no:cacheprovider -k "citation or search or dependencies"`

Expected: FAIL with missing query methods or unresolved targets.

- [ ] **Step 3: Implement deterministic resolution and queries**

After every successful paper import, update all `citation_evidence.target_paper_id` values by joining `cited_arxiv_id` to `papers.paper_id = 'arxiv:' || cited_arxiv_id`; clear targets that no longer resolve during replacement. Keep the preserved `resolution_status` reason separate from whether the target is currently present.

Use parameterized SQL for filters and `instr(lower(coalesce(title, '') || char(10) || content), lower(?)) > 0` for substring search. Order search by `paper_id, global_id`; return an excerpt capped at 240 characters. Traverse dependencies in Python from ordered stored edges with a visited set matching current `PaperGraph` semantics. Validate direction and limits before executing SQL.

- [ ] **Step 4: Run all workspace tests**

Run: `uv run pytest tests/test_identity.py tests/test_project.py tests/test_citations.py tests/test_workspace.py -q -p no:cacheprovider`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```text
git add src/papergraph/workspace.py tests/test_workspace.py
git commit -m "Add cross-paper graph queries"
```

### Task 6: Add independent workspace MCP tools

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_workspace_server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: `Workspace` API from Tasks 4–5 and existing arXiv preparation.
- Produces eight tools: `open_workspace`, `workspace_add_local_paper`, `workspace_add_arxiv_paper`, `workspace_list_papers`, `workspace_get_paper`, `workspace_search_theorems`, `workspace_get_dependencies`, and `workspace_get_citations`.
- Preserves existing `_current_graph` and all six current tools independently.

- [ ] **Step 1: Write failing MCP adapter tests**

```python
def test_workspace_state_is_independent_from_single_paper_state(tmp_path, monkeypatch):
    database = tmp_path / "workspace.sqlite3"
    open_workspace(str(database))
    workspace_add_local_paper(str(FIXTURES / "paper_a" / "main.tex"), "local:paper-a")

    load_paper(str(FIXTURES / "sample.tex"))

    assert workspace_list_papers()[0]["paper_id"] == "local:paper-a"
    assert list_theorems()


def test_failed_workspace_open_preserves_active_workspace(tmp_path):
    open_workspace(str(tmp_path / "good.sqlite3"))
    with pytest.raises(ToolError, match="schema"):
        open_workspace(str(NEWER_SCHEMA_FIXTURE))
    assert workspace_list_papers() == []
```

Add exact delegation/payload tests for every tool, missing-workspace errors, local IDs, arXiv options, query validation, domain error translation, and preservation of prior state after failed imports.

- [ ] **Step 2: Run server tests and verify failure**

Run: `uv run pytest tests/test_workspace_server.py -q -p no:cacheprovider`

Expected: FAIL because the workspace tool functions do not exist.

- [ ] **Step 3: Implement thin MCP adapters**

Add `_current_workspace: Workspace | None`, `require_workspace()`, and a reset helper used by tests. `open_workspace` must construct and validate a new workspace before closing/replacing the old one. Local import calls `load_project` then `Workspace.import_project`; arXiv import calls `prepare_arxiv_project`, derives the canonical paper ID/version, loads the structured project, and imports it. Query adapters return domain dictionaries unchanged.

Catch the explicit workspace/project/citation/arXiv exception families and raise `ToolError(str(exc)) from exc`. Do not catch programming exceptions. Do not make any existing load tool write to the workspace or any workspace import replace `_current_graph`.

- [ ] **Step 4: Run all server and compatibility tests**

Run: `uv run pytest tests/test_server.py tests/test_workspace_server.py tests/test_cli.py tests/test_multifile.py -q -p no:cacheprovider`

Expected: all selected tests PASS and the original six tool payload assertions remain unchanged.

- [ ] **Step 5: Commit**

```text
git add src/papergraph/server.py tests/test_server.py tests/test_workspace_server.py
git commit -m "Expose cross-paper workspaces through MCP"
```

### Task 7: Add a three-paper end-to-end fixture

**Files:**
- Create: `tests/fixtures/workspace/paper_a/main.tex`
- Create: `tests/fixtures/workspace/paper_a/refs.bib`
- Create: `tests/fixtures/workspace/paper_b/main.tex`
- Create: `tests/fixtures/workspace/paper_b/refs.bib`
- Create: `tests/fixtures/workspace/paper_c/main.tex`
- Create: `tests/fixtures/workspace/paper_c/refs.bib`
- Create: `tests/test_workspace_integration.py`

**Interfaces:**
- Provides deterministic fixtures with duplicate `thm:main` labels across papers, A→B→C→A citation cycle, one missing citation key, and one valid arXiv citation whose target is absent.

- [ ] **Step 1: Create fixtures and write the failing reopen test**

```python
def test_three_paper_graph_survives_reopen(tmp_path):
    path = tmp_path / "knowledge.sqlite3"
    workspace = Workspace.open(path)
    import_fixture_papers(workspace)
    before = {
        "papers": workspace.list_papers(),
        "search": workspace.search_theorems("fixed point"),
        "citations": workspace.get_citations("local:paper-a", "outgoing"),
    }
    workspace.close()

    reopened = Workspace.open(path)
    assert reopened.list_papers() == before["papers"]
    assert reopened.search_theorems("fixed point") == before["search"]
    assert reopened.get_citations("local:paper-a", "outgoing") == before["citations"]
    assert len({item["global_id"] for item in reopened.search_theorems("theorem")}) == 3
```

- [ ] **Step 2: Run the integration test and verify the fixture exposes any missing behavior**

Run: `uv run pytest tests/test_workspace_integration.py -q -p no:cacheprovider`

Expected: FAIL until the helper imports all fixture metadata and query payloads are stable across reopen.

- [ ] **Step 3: Complete the fixture importer and close integration gaps**

Implement `import_fixture_papers()` in the test module by calling `load_project()` and `Workspace.import_project()` three times with `local:paper-a`, `arxiv:2401.12345`, and `local:paper-c`. Make only the smallest production changes required by the end-to-end test; do not add new relationship types or network access.

- [ ] **Step 4: Run the complete deterministic suite**

Run: `uv run pytest -q -p no:cacheprovider`

Expected: all previous 113 tests plus the new identity, project, citation, workspace, server, and integration tests PASS.

- [ ] **Step 5: Commit**

```text
git add tests/fixtures/workspace tests/test_workspace_integration.py src/papergraph
git commit -m "Test a persistent three-paper knowledge graph"
```

### Task 8: Document and package v0.4.0

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Modify: `tests/test_repository.py`
- Create: `docs/superpowers/specs/2026-09-02-cross-paper-knowledge-graph-design.md` (already committed)
- Create: `docs/superpowers/plans/2026-09-02-cross-paper-knowledge-graph.md` (this plan)

**Interfaces:**
- Sets package version to `0.4.0`.
- Documents exact schemas for all eight workspace MCP tools.
- Adds one reproducible local three-paper walkthrough and the explicit-evidence marketing statement.

- [ ] **Step 1: Extend repository tests before changing documentation**

```python
def test_readme_documents_v040_cross_paper_graph():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "v0.4.0" in readme
    assert "SQLite" in readme
    assert "workspace_add_arxiv_paper" in readme
    assert "workspace_search_theorems" in readme
    assert "workspace_get_citations" in readme
    assert "explicit" in readme.lower()
    assert "semantic" in readme.lower()
```

Also update version/lock assertions to `0.4.0`, assert `pybtex>=0.25,<0.27` is a runtime dependency, and assert the eight new tool names are present in the README.

- [ ] **Step 2: Run repository tests and verify failure**

Run: `uv run pytest tests/test_repository.py -q -p no:cacheprovider`

Expected: FAIL on the old `0.3.1` version and missing workspace documentation.

- [ ] **Step 3: Update version, lockfile, README, and contributor guidance**

Set `project.version = "0.4.0"`, run `uv lock`, update the version-pinned `uvx` examples to `v0.4.0`, and add:

- a multi-paper value proposition;
- a Mermaid diagram showing LaTeX/arXiv → structured loading → citations → SQLite → MCP;
- all eight tool signatures and return summaries;
- a temporary-workspace walkthrough that imports three public/synthetic projects;
- citation evidence and unresolved-citation examples;
- privacy, path, and database backup guidance;
- limitations stating there is no semantic theorem matching or automatic cited-paper download.

Update `CONTRIBUTING.md` only if new focused test commands or fixture privacy rules are required.

- [ ] **Step 4: Run documentation tests and the complete suite**

Run: `uv run pytest tests/test_repository.py -q -p no:cacheprovider`

Expected: repository tests PASS.

Run: `uv run pytest -q -p no:cacheprovider`

Expected: the complete deterministic suite PASS.

- [ ] **Step 5: Commit**

```text
git add pyproject.toml uv.lock README.md CONTRIBUTING.md tests/test_repository.py docs/superpowers
git commit -m "Prepare PaperGraph v0.4.0 documentation"
```

### Task 9: Final verification and delivery

**Files:**
- No intended source changes; fix only evidence-backed failures and commit each fix separately.

**Interfaces:**
- Verifies the distributable, installed CLI, persistent workspace, compatibility, and repository cleanliness.

- [ ] **Step 1: Run final deterministic verification with a workspace-owned temporary directory**

Run: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\ai4math\papergraph-pytest-v040-final`

Expected: all tests PASS with zero failures or errors.

- [ ] **Step 2: Build and install the wheel in a clean environment**

Run: `uv build`

Expected: `dist/papergraph_mcp-0.4.0.tar.gz` and `dist/papergraph_mcp-0.4.0-py3-none-any.whl` are created.

Create `.smoke-venv`, install only the wheel, then run:

```text
.smoke-venv\Scripts\papergraph-mcp.exe --version
```

Expected: `papergraph-mcp 0.4.0`.

- [ ] **Step 3: Run an installed-package workspace smoke test**

Use `.smoke-venv\Scripts\python.exe` to open a temporary SQLite workspace, import the three packaged test fixtures through the public Python APIs, close and reopen it, assert three papers exist, assert the three global theorem IDs are unique, search a shared term, and traverse A→B citation evidence.

Expected output: `workspace smoke OK: 3 papers`.

- [ ] **Step 4: Perform one bounded live arXiv acceptance check**

With a fresh temporary arXiv cache and workspace, import two known public arXiv source packages, confirm both paper IDs coexist, and inspect outgoing citation evidence. Do not require the two selected papers to cite each other; record unresolved evidence honestly. This is manual acceptance only and must not be added to CI.

Expected: both imports succeed, the workspace reopens, and no cache or source package appears in Git status.

- [ ] **Step 5: Clean generated artifacts and re-run the deterministic suite**

Resolve and verify the exact `dist`, `.smoke-venv`, test temporary, live cache, and live workspace paths before removing them. Then rerun the Step 1 command.

Expected: all tests PASS again and `git status --short` is empty.

- [ ] **Step 6: Review the branch and push for PR**

Run:

```text
git diff --check origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
git status --short
```

Expected: no whitespace errors, coherent task commits, and a clean worktree. Push `feature/v0.4-cross-paper-graph` and create a pull request only after review. Do not merge, tag, or publish a Release.
