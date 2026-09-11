# Reading Report Export v0.11 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents for this implementation.

**Goal:** Build v0.11.0 Reading Report Export so a stored paper can be exported as a deterministic Markdown reading report through Workspace, MCP, and CLI.

**Architecture:** Add a focused `reading_report.py` formatter over the existing Paper Map payload. Keep `Workspace` as a thin synchronized wrapper, keep `server.py` responsible only for MCP/CLI exposure, and keep file writing in the CLI layer.

**Tech Stack:** Python 3.10+, argparse CLI, FastMCP tools, pytest, existing SQLite-backed `Workspace`, existing Paper Map and external import planner payloads.

## Global Constraints

- Release version is `0.11.0`.
- Report schema version is `1`.
- Markdown only; no PDF, HTML, LLM-authored summaries, new extractors, schema changes, reading-session mutation, or network calls.
- Output must be deterministic: no timestamps, random IDs, or environment-specific paths in Workspace/MCP payloads.
- `max_candidates` validation must match `get_paper_map`.
- Unknown `paper_id` raises `KeyError`; invalid `max_candidates` raises `ValueError`.
- CLI `--output` must not create parent directories implicitly; it may overwrite existing files.
- Empty/sparse papers must produce valid Markdown with warnings rather than failing.

---

## File Structure

- Create `src/papergraph/reading_report.py`: report model construction and deterministic Markdown rendering.
- Modify `src/papergraph/workspace.py`: import the builder and add `Workspace.export_paper_reading_report`.
- Modify `src/papergraph/server.py`: add MCP tool, CLI parser, CLI output-writing helper, and command dispatch.
- Add `tests/test_workspace_reading_report.py`: report payload and Markdown rendering coverage.
- Add `tests/test_workspace_reading_report_server.py`: MCP wrapper coverage.
- Add `tests/test_cli_reading_report.py`: stdout, `--output`, and invalid-output CLI behavior.
- Modify repository/version docs and tests: `pyproject.toml`, `src/papergraph/arxiv.py`, `README.md`, `.github`/skill references if version-pinned tests require them, and tests expecting `0.10.0`.

### Task 1: Workspace Report Model and Markdown Renderer

**Files:**
- Create: `src/papergraph/reading_report.py`
- Modify: `src/papergraph/workspace.py`
- Test: `tests/test_workspace_reading_report.py`

**Interfaces:**
- Consumes: `Workspace.get_paper_map(paper_id: str, max_candidates: int = 5) -> dict`
- Produces: `build_paper_reading_report(workspace, paper_id: str, max_candidates: int = 5) -> dict[str, Any]`
- Produces: `render_paper_reading_report_markdown(report_model: dict[str, Any]) -> str`
- Produces: `Workspace.export_paper_reading_report(paper_id: str, max_candidates: int = 5) -> dict`

- [ ] **Step 1: Write failing payload and Markdown tests**

Add tests that import the existing Paper Map PDF fixture helpers and assert:

```python
report = workspace.export_paper_reading_report("local:paper")
assert report["report_schema_version"] == 1
assert report["format"] == "markdown"
assert report["paper_id"] == "local:paper"
assert report["summary"]["evidence_status"] == "usable"
assert report["sections"][0]["id"] == "paper"
assert "# Reading Report:" in report["markdown"]
assert "## Main-Result Candidates" in report["markdown"]
assert "result text contains a main-result cue" in report["markdown"]
assert "## Recommended Reading Route" in report["markdown"]
assert "## External Reading Risks" in report["markdown"]
assert "Review candidate: arXiv:2401.12345" in report["markdown"]
assert "PaperGraph does not verify proofs." in report["markdown"]
```

Add a sparse-paper test that inserts `local:empty` as in `test_workspace_paper_map.py` and asserts the Markdown contains:

```python
"No main-result candidates were found"
"PaperGraph does not infer hidden mathematical prerequisites."
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_report.py -q -p no:cacheprovider
```

Expected: fails because `Workspace.export_paper_reading_report` or `papergraph.reading_report` does not exist.

- [ ] **Step 3: Implement the report builder and renderer**

Create `reading_report.py` with:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from papergraph.workspace import Workspace

REPORT_SCHEMA_VERSION = 1
REQUIRED_BOUNDARIES = [
    "PaperGraph does not verify proofs.",
    "PaperGraph does not infer hidden mathematical prerequisites.",
    "PaperGraph does not perform semantic theorem matching.",
    (
        "Empty dependencies mean no supported extraction evidence was found, "
        "not that no mathematical dependencies exist."
    ),
]

def build_paper_reading_report(
    workspace: Workspace,
    paper_id: str,
    max_candidates: int = 5,
) -> dict[str, Any]:
    paper_map = workspace.get_paper_map(paper_id, max_candidates=max_candidates)
    summary = {
        "recommended_start_result_id": paper_map["summary"]["recommended_start_result_id"],
        "main_candidate_count": paper_map["summary"]["main_candidate_count"],
        "reading_route_count": len(paper_map["reading_route"]),
        "external_risk_count": paper_map["summary"]["external_risk_count"],
        "unresolved_risk_count": paper_map["summary"]["unresolved_risk_count"],
        "evidence_status": paper_map["summary"]["evidence_status"],
    }
    sections = _sections_from_paper_map(paper_map, summary)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "format": "markdown",
        "paper_id": paper_map["paper"]["paper_id"],
        "title": paper_map["paper"].get("title"),
        "summary": summary,
        "sections": sections,
        "warnings": paper_map["evidence_quality"]["warnings"],
        "paper_map": paper_map,
    }
    report["markdown"] = render_paper_reading_report_markdown(report)
    return report
```

Implement helpers to render the exact required headings, candidate reason bullets, route ordered list, local dependency evidence from route items, external candidates/reviews/blocked items, warnings, boundaries, and next commands. Keep all helpers private and deterministic.

Modify `workspace.py`:

```python
from papergraph.reading_report import build_paper_reading_report
...
@_synchronized
def export_paper_reading_report(self, paper_id: str, max_candidates: int = 5) -> dict:
    """Export a deterministic Markdown reading report for one stored paper."""
    return build_paper_reading_report(
        self,
        paper_id,
        max_candidates=max_candidates,
    )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_report.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/reading_report.py src/papergraph/workspace.py tests/test_workspace_reading_report.py
git commit -m "feat: add reading report export model"
```

### Task 2: MCP Tool Exposure

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_workspace_reading_report_server.py`

**Interfaces:**
- Consumes: `Workspace.export_paper_reading_report(paper_id: str, max_candidates: int = 5) -> dict`
- Produces: `workspace_export_paper_reading_report(paper_id: str, max_candidates: int = 5) -> dict`

- [ ] **Step 1: Write failing MCP tests**

Add tests matching `tests/test_workspace_paper_map_server.py`:

```python
def test_workspace_export_paper_reading_report_returns_payload(tmp_path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)
        server._workspace = workspace
        report = server.workspace_export_paper_reading_report("local:paper", max_candidates=1)
        assert report["report_schema_version"] == 1
        assert report["format"] == "markdown"
        assert report["paper_id"] == "local:paper"
        assert "## Paper Map" in report["markdown"]
    finally:
        server._workspace = None
        workspace.close()
```

Also assert no active workspace and unknown paper raise `ToolError`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_report_server.py -q -p no:cacheprovider
```

Expected: fails because the MCP wrapper does not exist.

- [ ] **Step 3: Implement MCP wrapper**

Add near `workspace_get_paper_map`:

```python
@mcp.tool()
@_serialized_workspace_tool
def workspace_export_paper_reading_report(
    paper_id: str,
    max_candidates: int = 5,
) -> dict:
    """Export a deterministic Markdown reading report for one stored paper."""

    try:
        return require_workspace().export_paper_reading_report(
            paper_id,
            max_candidates=max_candidates,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reading_report_server.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_workspace_reading_report_server.py
git commit -m "feat: expose reading report MCP tool"
```

### Task 3: CLI Export Command

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_cli_reading_report.py`

**Interfaces:**
- Consumes: `Workspace.export_paper_reading_report(paper_id: str, max_candidates: int = 5) -> dict`
- Produces command: `export-paper-reading-report`
- Produces stdout behavior: Markdown when `--output` is absent, JSON metadata when `--output` is present.

- [ ] **Step 1: Write failing CLI tests**

Add tests that create a workspace, import the Paper Map PDF fixture, then call:

```python
server.main([
    "export-paper-reading-report",
    "--workspace", str(workspace_path),
    "--paper-id", "local:paper",
])
```

Assert stdout begins with `# Reading Report:` and includes `## Next Commands`.

Add `--output` test:

```python
output = tmp_path / "report.md"
server.main([
    "export-paper-reading-report",
    "--workspace", str(workspace_path),
    "--paper-id", "local:paper",
    "--output", str(output),
])
payload = json.loads(capsys.readouterr().out)
assert payload["status"] == "written"
assert payload["command"] == "export-paper-reading-report"
assert payload["format"] == "markdown"
assert payload["output"] == str(output)
assert payload["bytes"] == len(output.read_bytes())
assert output.read_text(encoding="utf-8").startswith("# Reading Report:")
```

Add invalid parent path test expecting `SystemExit(1)` and JSON `status == "error"`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_reading_report.py -q -p no:cacheprovider
```

Expected: fails because command parser/dispatch is missing.

- [ ] **Step 3: Implement CLI parser, writer, and dispatch**

Add parser:

```python
reading_report_parser = subparsers.add_parser(
    "export-paper-reading-report",
    help="Export a deterministic Markdown reading report for one stored paper.",
)
reading_report_parser.add_argument("--workspace", required=True)
reading_report_parser.add_argument("--paper-id", required=True)
reading_report_parser.add_argument("--max-candidates", type=int, default=5)
reading_report_parser.add_argument("--output")
```

Add a helper that opens the workspace, calls `export_paper_reading_report`, prints Markdown without `--output`, and writes bytes plus JSON metadata with `--output`. The helper must print JSON error payloads and exit `1` for missing parent, directory target, workspace errors, and write errors.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_reading_report.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_cli_reading_report.py
git commit -m "feat: add reading report CLI export"
```

### Task 4: Documentation and Version Bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/papergraph/arxiv.py`
- Modify: `README.md`
- Modify version-pinned tests under `tests/`
- Modify any release/install helper files found by `rg "0\\.10\\.0|v0\\.10\\.0"`

**Interfaces:**
- Produces release version: `0.11.0`
- Produces documented tool: `workspace_export_paper_reading_report`
- Produces documented CLI command: `export-paper-reading-report`

- [ ] **Step 1: Write/update failing repository tests**

Update repository tests to expect:

```python
"0.11.0"
"v0.11.0"
"workspace_export_paper_reading_report"
"export-paper-reading-report"
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider
```

Expected: fails until docs/version files are updated.

- [ ] **Step 2: Implement docs and version updates**

Update:

- `pyproject.toml` version to `0.11.0`.
- `src/papergraph/arxiv.py` user agent to `PaperGraph/0.11.0`.
- README launch pins from `v0.10.0` to `v0.11.0`.
- README release highlight to say v0.11.0 adds Reading Report Export.
- README tool table and complete workspace tool index with `workspace_export_paper_reading_report`.
- README CLI examples with:

```powershell
papergraph-mcp --workspace .\papergraph.sqlite3 export-paper-reading-report --paper-id local:paper-a
papergraph-mcp --workspace .\papergraph.sqlite3 export-paper-reading-report --paper-id local:paper-a --output report.md
```

- Any test fixtures or install docs found by `rg "0\\.10\\.0|v0\\.10\\.0"`.

- [ ] **Step 3: Run focused docs/version tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```powershell
git add pyproject.toml src/papergraph/arxiv.py README.md tests
git commit -m "docs: document reading report v0.11"
```

### Task 5: Full Verification, Push, PR, and Release Preparation

**Files:**
- No implementation files expected beyond previous tasks.

**Interfaces:**
- Produces pushed branch and PR.
- Produces release notes for `v0.11.0`.

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
git log --oneline -6
```

Expected: branch is clean and ahead of origin by the new spec/plan/implementation commits.

- [ ] **Step 3: Push branch**

Run:

```powershell
git push origin feature/v0.9.3-external-citation-evidence
```

Expected: push succeeds.

- [ ] **Step 4: Create PR**

Use GitHub CLI if available:

```powershell
gh pr create --base main --head feature/v0.9.3-external-citation-evidence --title "Add Reading Report Export v0.11.0" --body-file <generated-body-file>
```

The PR body must summarize:

- Markdown Reading Report export;
- Workspace/MCP/CLI entry points;
- deterministic evidence boundaries;
- tests run.

- [ ] **Step 5: Publish release only after main contains the release commit**

If the PR can be merged safely and the user has authorized release, merge through the repository's accepted workflow, update local `main`, tag `v0.11.0`, and create a GitHub Release with notes emphasizing:

- Markdown Reading Report export;
- persistent reading artifacts;
- main-result candidates, reading route, external risks, and evidence warnings in one file;
- no proof verification, semantic theorem matching, or hidden dependency inference.

If repository permissions or branch protection prevent merging/releasing, leave the PR ready and provide the exact release notes and commands.
