# Cross-Paper Reading Plan v0.12 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents for this implementation.

**Goal:** Build v0.12.0 Cross-Paper Reading Plan so a small explicit set of stored papers can be exported as a deterministic Markdown multi-paper reading plan through Workspace, MCP, and CLI.

**Architecture:** Add a focused `cross_paper_reading_plan.py` formatter over existing Paper Map, Reading Report, citation evidence, and external import planner payloads. Keep `Workspace` as a thin synchronized wrapper, keep `server.py` responsible only for MCP/CLI exposure, and keep file writing in the CLI layer.

**Tech Stack:** Python 3.10+, argparse CLI, FastMCP tools, pytest, existing SQLite-backed `Workspace`, existing Paper Map, Reading Report, citation evidence, and external import planner payloads.

## Global Constraints

- Release version is `0.12.0`.
- Plan schema version is `1`.
- Markdown only; no PDF, HTML, LLM-authored summaries, new extractors, schema changes, reading-session mutation, automatic discovery, or network calls.
- Output must be deterministic: no timestamps, random IDs, or environment-specific paths in Workspace/MCP payloads.
- `paper_ids` must contain between 2 and 8 distinct paper IDs.
- Unknown paper IDs raise `KeyError`; invalid `paper_ids` and candidate limits raise `ValueError`.
- `max_candidates_per_paper` validation must match Paper Map's integer range `1..20`.
- CLI `--output` must not create parent directories implicitly; it may overwrite existing files.
- Empty/sparse selected papers must appear in valid Markdown with warnings rather than failing.

---

## File Structure

- Create `src/papergraph/cross_paper_reading_plan.py`: plan model construction, explicit cross-paper evidence extraction, deterministic sequence generation, and Markdown rendering.
- Modify `src/papergraph/workspace.py`: import the builder and add `Workspace.export_cross_paper_reading_plan`.
- Modify `src/papergraph/server.py`: add MCP tool, CLI parser, CLI output-writing helper, and command dispatch.
- Add `tests/test_workspace_cross_paper_reading_plan.py`: workspace payload, validation, sequence, warnings, and Markdown rendering coverage.
- Add `tests/test_workspace_cross_paper_reading_plan_server.py`: MCP wrapper coverage.
- Add `tests/test_cli_cross_paper_reading_plan.py`: stdout, `--output`, and invalid-output CLI behavior.
- Modify repository/version docs and tests: `pyproject.toml`, `src/papergraph/arxiv.py`, `README.md`, and tests expecting `0.11.0`.

### Task 1: Workspace Plan Model and Markdown Renderer

**Files:**
- Create: `src/papergraph/cross_paper_reading_plan.py`
- Modify: `src/papergraph/workspace.py`
- Test: `tests/test_workspace_cross_paper_reading_plan.py`

**Interfaces:**
- Consumes: `Workspace.get_paper_map(paper_id: str, max_candidates: int = 5) -> dict`
- Consumes: `Workspace.plan_external_imports_for_paper(paper_id: str) -> dict`
- Consumes: `Workspace.get_citations(paper_id: str, direction: str = "outgoing", include_unresolved: bool = True) -> list[dict]`
- Produces: `build_cross_paper_reading_plan(workspace, paper_ids: list[str], focus: str | None = None, max_candidates_per_paper: int = 3) -> dict[str, Any]`
- Produces: `render_cross_paper_reading_plan_markdown(plan_model: dict[str, Any]) -> str`
- Produces: `Workspace.export_cross_paper_reading_plan(paper_ids: list[str], focus: str | None = None, max_candidates_per_paper: int = 3) -> dict`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/test_workspace_cross_paper_reading_plan.py` with real workspace fixtures:

```python
from pathlib import Path

import pytest

from papergraph.project import load_project
from papergraph.workspace import Workspace
from tests.test_workspace_external_import_planner import import_import_plan_pdf
from tests.test_workspace_paper_map import import_paper_map_pdf


def import_arxiv_context_paper(workspace: Workspace, tmp_path: Path) -> None:
    tex = tmp_path / "context.tex"
    tex.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\newtheorem{theorem}{Theorem}",
                r"\begin{document}",
                r"\begin{theorem}\label{main}",
                "Context fixed point theorem.",
                r"\end{theorem}",
                r"\begin{proof}",
                "This is direct.",
                r"\end{proof}",
                r"\end{document}",
            ]
        ),
        encoding="utf-8",
    )
    workspace.import_project(
        "arxiv:2401.12345",
        "arxiv",
        "2401.12345",
        None,
        load_project(tex),
    )


def test_cross_paper_reading_plan_exports_markdown_payload(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_context_paper(workspace, tmp_path)

        plan = workspace.export_cross_paper_reading_plan(
            ["local:paper", "arxiv:2401.12345"],
            focus="main result",
            max_candidates_per_paper=2,
        )

        assert plan["plan_schema_version"] == 1
        assert plan["format"] == "markdown"
        assert plan["paper_ids"] == ["local:paper", "arxiv:2401.12345"]
        assert plan["focus"] == "main result"
        assert plan["summary"]["paper_count"] == 2
        assert plan["summary"]["recommended_start_paper_id"] == "local:paper"
        assert plan["summary"]["recommended_start_result_id"]
        assert plan["summary"]["cross_paper_edge_count"] == 1
        assert plan["summary"]["evidence_status"] == "usable"
        assert len(plan["papers"]) == 2
        assert plan["cross_paper_edges"][0]["source_paper_id"] == "local:paper"
        assert plan["cross_paper_edges"][0]["target_paper_id"] == "arxiv:2401.12345"
        assert plan["recommended_sequence"][0]["role"] == "start"
        assert "selected_main_candidate" in plan["recommended_sequence"][0]["reason"]
        markdown = plan["markdown"]
        assert markdown.startswith("# Cross-Paper Reading Plan:")
        assert "## Paper Set" in markdown
        assert "## Recommended Reading Sequence" in markdown
        assert "## Cross-Paper Evidence" in markdown
        assert "`local:paper` cites selected paper `arxiv:2401.12345`" in markdown
        assert "## Per-Paper Reading Reports" in markdown
        assert "export-paper-reading-report" in markdown
        assert "Citation evidence does not imply logical dependency" in markdown
    finally:
        workspace.close()
```

Add tests for:

```python
def test_cross_paper_reading_plan_warns_without_edges(tmp_path: Path): ...
def test_cross_paper_reading_plan_rejects_invalid_inputs(tmp_path: Path): ...
def test_cross_paper_reading_plan_focus_no_match_warns(tmp_path: Path): ...
def test_cross_paper_reading_plan_includes_sparse_paper(tmp_path: Path): ...
```

The invalid-input test must assert duplicate IDs, one ID, nine IDs, unknown paper ID, `max_candidates_per_paper=True`, and `max_candidates_per_paper=0`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_cross_paper_reading_plan.py -q -p no:cacheprovider
```

Expected: fails because `Workspace.export_cross_paper_reading_plan` does not exist.

- [ ] **Step 3: Implement the plan builder and renderer**

Create `cross_paper_reading_plan.py` with:

```python
PLAN_SCHEMA_VERSION = 1
MAX_PAPER_COUNT = 8
REQUIRED_BOUNDARIES = [
    "PaperGraph does not verify proofs.",
    "PaperGraph does not infer hidden mathematical prerequisites.",
    "PaperGraph does not perform semantic theorem matching.",
    "Citation evidence does not imply logical dependency unless supported by reading-path evidence.",
    (
        "Empty cross-paper edges mean no supported extraction evidence was found, "
        "not that no relationship exists."
    ),
]
```

Implement:

```python
def build_cross_paper_reading_plan(workspace, paper_ids, focus=None, max_candidates_per_paper=3):
    normalized_ids = _validate_paper_ids(workspace, paper_ids)
    max_candidates_per_paper = _validate_max_candidates_per_paper(max_candidates_per_paper)
    normalized_focus = _normalize_focus(focus)
    paper_maps = [
        workspace.get_paper_map(paper_id, max_candidates=max_candidates_per_paper)
        for paper_id in normalized_ids
    ]
    papers = _paper_summaries(paper_maps)
    edges = _cross_paper_edges(workspace, normalized_ids)
    external_risks = _external_risks(workspace, normalized_ids, edges)
    sequence, focus_matched = _recommended_sequence(normalized_ids, paper_maps, edges, normalized_focus)
    warnings = _warnings(paper_maps, edges, external_risks, normalized_focus, focus_matched)
    summary = _summary(normalized_ids, paper_maps, edges, external_risks, sequence)
    plan = {...}
    plan["markdown"] = render_cross_paper_reading_plan_markdown(plan)
    return plan
```

Cross-paper edges should be built from `workspace.get_citations(source_id, include_unresolved=True)` rows whose `target_paper_id` is in the selected set. Also inspect each selected paper's `plan_external_imports_for_paper` candidates and already-imported items whose `source.recommended_paper_id` is in the selected set.

Markdown must render the required headings, compact paper summaries, ordered sequence, selected-paper citation edges, per-paper candidates, per-paper report commands, external risks, warnings, boundaries, and next commands.

Modify `workspace.py`:

```python
from papergraph.cross_paper_reading_plan import build_cross_paper_reading_plan

@_synchronized
def export_cross_paper_reading_plan(
    self,
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict:
    """Export a deterministic Markdown reading plan for selected papers."""
    return build_cross_paper_reading_plan(
        self,
        paper_ids,
        focus=focus,
        max_candidates_per_paper=max_candidates_per_paper,
    )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_cross_paper_reading_plan.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/cross_paper_reading_plan.py src/papergraph/workspace.py tests/test_workspace_cross_paper_reading_plan.py
git commit -m "feat: add cross-paper reading plan model"
```

### Task 2: MCP Tool Exposure

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_workspace_cross_paper_reading_plan_server.py`

**Interfaces:**
- Consumes: `Workspace.export_cross_paper_reading_plan(...) -> dict`
- Produces: `workspace_export_cross_paper_reading_plan(paper_ids: list[str], focus: str | None = None, max_candidates_per_paper: int = 3) -> dict`

- [ ] **Step 1: Write failing MCP tests**

Create tests that call:

```python
plan = server.workspace_export_cross_paper_reading_plan(
    ["local:paper", "arxiv:2401.12345"],
    focus="main",
    max_candidates_per_paper=1,
)
assert plan["plan_schema_version"] == 1
assert plan["format"] == "markdown"
assert plan["summary"]["paper_count"] == 2
assert "## Cross-Paper Evidence" in plan["markdown"]
```

Also assert no active workspace and unknown paper raise `ToolError`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_cross_paper_reading_plan_server.py -q -p no:cacheprovider
```

Expected: fails because the MCP wrapper does not exist.

- [ ] **Step 3: Implement MCP wrapper**

Add near `workspace_export_paper_reading_report`:

```python
@mcp.tool()
@_serialized_workspace_tool
def workspace_export_cross_paper_reading_plan(
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict:
    """Export a deterministic Markdown reading plan for selected papers."""
    try:
        return require_workspace().export_cross_paper_reading_plan(
            paper_ids,
            focus=focus,
            max_candidates_per_paper=max_candidates_per_paper,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_cross_paper_reading_plan_server.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_workspace_cross_paper_reading_plan_server.py
git commit -m "feat: expose cross-paper reading plan MCP tool"
```

### Task 3: CLI Export Command

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_cli_cross_paper_reading_plan.py`

**Interfaces:**
- Consumes: `Workspace.export_cross_paper_reading_plan(...) -> dict`
- Produces command: `export-cross-paper-reading-plan`
- Produces stdout behavior: Markdown when `--output` is absent, JSON metadata when `--output` is present.

- [ ] **Step 1: Write failing CLI tests**

Add tests that call:

```python
server.main([
    "export-cross-paper-reading-plan",
    "--workspace", str(workspace_path),
    "--paper-id", "local:paper",
    "--paper-id", "arxiv:2401.12345",
    "--focus", "main",
])
```

Assert stdout starts with `# Cross-Paper Reading Plan:` and includes `## Next Commands`.

Add `--output` test asserting:

```python
payload["status"] == "written"
payload["command"] == "export-cross-paper-reading-plan"
payload["paper_ids"] == ["local:paper", "arxiv:2401.12345"]
payload["format"] == "markdown"
payload["bytes"] == len(output_path.read_bytes())
payload["plan_schema_version"] == 1
```

Add invalid parent path test expecting `SystemExit(1)` and JSON `status == "error"`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_cross_paper_reading_plan.py -q -p no:cacheprovider
```

Expected: fails because command parser/dispatch is missing.

- [ ] **Step 3: Implement CLI parser, writer, and dispatch**

Add parser:

```python
cross_paper_plan_parser = subparsers.add_parser(
    "export-cross-paper-reading-plan",
    help="Export a deterministic Markdown reading plan for selected papers.",
)
cross_paper_plan_parser.add_argument("--workspace", required=True)
cross_paper_plan_parser.add_argument("--paper-id", action="append", required=True)
cross_paper_plan_parser.add_argument("--focus")
cross_paper_plan_parser.add_argument("--max-candidates-per-paper", type=int, default=3)
cross_paper_plan_parser.add_argument("--output")
```

Add a helper mirroring `_run_reading_report_cli_command`, with command-specific JSON metadata and JSON error payloads.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_cross_paper_reading_plan.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_cli_cross_paper_reading_plan.py
git commit -m "feat: add cross-paper reading plan CLI export"
```

### Task 4: Documentation and Version Bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/papergraph/arxiv.py`
- Modify: `README.md`
- Modify version-pinned tests under `tests/`
- Modify any release/install helper files found by `rg "0\\.11\\.0|v0\\.11\\.0"`

**Interfaces:**
- Produces release version: `0.12.0`
- Produces documented tool: `workspace_export_cross_paper_reading_plan`
- Produces documented CLI command: `export-cross-paper-reading-plan`

- [ ] **Step 1: Update repository tests first**

Update repository tests to expect:

```python
"0.12.0"
"v0.12.0"
"workspace_export_cross_paper_reading_plan"
"export-cross-paper-reading-plan"
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider
```

Expected: fails until docs/version files are updated.

- [ ] **Step 2: Implement docs and version updates**

Update:

- `pyproject.toml` version to `0.12.0`.
- `src/papergraph/arxiv.py` user agent to `PaperGraph/0.12.0`.
- README launch pins from `v0.11.0` to `v0.12.0`.
- README release highlight to say v0.12.0 adds Cross-Paper Reading Plan.
- README tool table and complete workspace tool index with `workspace_export_cross_paper_reading_plan`.
- README CLI examples with repeated `--paper-id`.
- Any test fixtures or install docs found by `rg "0\\.11\\.0|v0\\.11\\.0"`.

- [ ] **Step 3: Run focused docs/version tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```powershell
git add pyproject.toml src/papergraph/arxiv.py README.md tests
git commit -m "docs: document cross-paper reading plan v0.12"
```

### Task 5: Full Verification and Branch Handoff

**Files:**
- No implementation files expected beyond previous tasks.

**Interfaces:**
- Produces verified branch ready for PR/release workflow.

- [ ] **Step 1: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 2: Confirm clean status**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected: branch is clean and ahead of origin by the spec/plan/implementation commits.

- [ ] **Step 3: Push branch**

Run:

```powershell
git push origin design/v0.12-cross-paper-reading-plans
```

Expected: push succeeds.

- [ ] **Step 4: Prepare PR body**

Prepare a PR body summarizing:

- Cross-Paper Reading Plan Markdown export;
- Workspace/MCP/CLI entry points;
- explicit-paper-set scope and evidence boundaries;
- selected-paper citation edges and external risk aggregation;
- tests run.

If GitHub CLI is available, create the PR against `main`; otherwise provide the compare URL and PR body.
