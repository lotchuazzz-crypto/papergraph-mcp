# External Import Planner v0.9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build read-only external import planning for result, queue, and paper scopes.

**Architecture:** Add deterministic planner methods to `Workspace` without changing the SQLite schema. Reuse existing reading path, reading queue, citation evidence, bibliography entries, and external result mention records; expose the planner through MCP wrappers and JSON CLI commands.

**Tech Stack:** Python 3.10+, SQLite, existing MCP server wrapper, pytest, existing JSON CLI conventions.

## Global Constraints

- No subagents for this implementation.
- Release version is `0.9.0`.
- Planning must be read-only and must not download papers or call live arXiv.
- Plans use only stored workspace evidence.
- Output order must be deterministic.
- CLI output must be one JSON payload on success.
- Existing v0.8 reading session and reading queue APIs remain compatible.

---

## File Structure

- Modify `src/papergraph/workspace.py`: planner APIs, evidence collection helpers, candidate grouping helpers.
- Modify `src/papergraph/server.py`: MCP wrappers and argparse commands.
- Add `tests/test_workspace_external_import_planner.py`: workspace behavior tests.
- Add `tests/test_workspace_external_import_planner_server.py`: MCP wrapper tests.
- Add `tests/test_cli_external_import_planner.py`: CLI tests.
- Modify `README.md`: document v0.9.0 and workflow.
- Modify `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `src/papergraph/arxiv.py`, `scripts/check_onboarding.py`, `.agents/skills/setting-up-papergraph/SKILL.md`, `.agents/skills/setting-up-papergraph/references/client-configuration.md`: release pins.
- Modify existing repository/onboarding/diagnostics tests for v0.9.0 and new tool names.

---

### Task 1: Workspace Planner

**Files:**
- Modify: `src/papergraph/workspace.py`
- Test: `tests/test_workspace_external_import_planner.py`

**Interfaces:**
- Consumes: `get_result_reading_path(result_id, recursive)`, `get_reading_queue(queue_id)`, `list_results(paper_id)`, `get_proof_dependencies(result_id)`, `get_citations(paper_id, direction, include_unresolved)`.
- Produces:
  - `Workspace.plan_external_imports_for_result(result_id: str, recursive: bool = True) -> dict`
  - `Workspace.plan_external_imports_for_queue(queue_id: str) -> dict`
  - `Workspace.plan_external_imports_for_paper(paper_id: str) -> dict`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/test_workspace_external_import_planner.py` with tests that:

```python
from pathlib import Path

import pytest

from papergraph.workspace import Workspace


def write_pdf_fixture(path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.drawString(72, 720, "Lemma 1.2. Local bootstrap lemma.")
    pdf.drawString(72, 700, "Proof. This is local.")
    pdf.drawString(72, 660, "Theorem 1.1. Main theorem.")
    pdf.drawString(
        72,
        640,
        "Proof. By Lemma 1.2, Lemma 9.9, and [12, Theorem 3.5], the claim follows.",
    )
    pdf.drawString(72, 600, "References")
    pdf.drawString(72, 580, "[12] A. Author, arXiv:2401.12345v2.")
    pdf.save()


def import_fixture(workspace: Workspace, tmp_path: Path) -> str:
    pdf = tmp_path / "paper.pdf"
    write_pdf_fixture(pdf)
    workspace.import_pdf(pdf, "local:paper")
    return "local:paper::pdf:theorem:1.1"


def test_result_plan_groups_external_mentions_by_arxiv(tmp_path: Path):
    with Workspace.open(tmp_path / "workspace.sqlite3") as workspace:
        result_id = import_fixture(workspace, tmp_path)

        plan = workspace.plan_external_imports_for_result(result_id)

        assert plan["plan_schema_version"] == 1
        assert plan["scope"]["kind"] == "result_id"
        assert plan["summary"]["candidate_count"] == 1
        assert plan["summary"]["import_candidate_count"] == 1
        candidate = plan["candidates"][0]
        assert candidate["candidate_id"] == "external-import:arxiv:2401.12345"
        assert candidate["status"] == "import_candidate"
        assert candidate["source"]["recommended_paper_id"] == "arxiv:2401.12345"
        assert candidate["source"]["arxiv_version"] == "v2"
        assert {item["kind"] for item in candidate["evidence"]} >= {
            "external_result_mention",
            "citation_mention",
            "bibliography_entry",
        }
        assert plan["summary"]["blocked_count"] == 1
        assert plan["blocked"][0]["reason"] == "missing_arxiv_id"


def test_result_plan_marks_imported_arxiv_candidates(tmp_path: Path):
    with Workspace.open(tmp_path / "workspace.sqlite3") as workspace:
        result_id = import_fixture(workspace, tmp_path)
        target = tmp_path / "target.tex"
        target.write_text(
            r"\\documentclass{article}\\newtheorem{theorem}{Theorem}\\begin{document}\\begin{theorem}\\label{t}Imported.\\end{theorem}\\end{document}",
            encoding="utf-8",
        )
        workspace.import_paper(target, "arxiv", "2401.12345")

        candidate = workspace.plan_external_imports_for_result(result_id)["candidates"][0]

        assert candidate["status"] == "already_imported"
        assert candidate["source"]["recommended_paper_id"] == "arxiv:2401.12345"


def test_queue_plan_uses_saved_queue_caution_items(tmp_path: Path):
    with Workspace.open(tmp_path / "workspace.sqlite3") as workspace:
        result_id = import_fixture(workspace, tmp_path)
        queue = workspace.create_reading_queue(result_id)

        plan = workspace.plan_external_imports_for_queue(queue["queue_id"])

        assert plan["scope"]["kind"] == "queue_id"
        assert plan["summary"]["candidate_count"] == 1
        assert plan["summary"]["blocked_count"] == 1
        assert all(
            evidence["source"].startswith("reading_queue")
            or evidence["source"].startswith("result")
            for candidate in plan["candidates"]
            for evidence in candidate["evidence"]
        )


def test_paper_plan_includes_citation_evidence_without_queue(tmp_path: Path):
    with Workspace.open(tmp_path / "workspace.sqlite3") as workspace:
        import_fixture(workspace, tmp_path)

        plan = workspace.plan_external_imports_for_paper("local:paper")

        assert plan["scope"] == {
            "kind": "paper_id",
            "value": "local:paper",
            "paper_id": "local:paper",
            "recursive": None,
        }
        assert plan["candidates"][0]["source"]["arxiv_id"] == "2401.12345"


def test_plan_rejects_non_boolean_recursive(tmp_path: Path):
    with Workspace.open(tmp_path / "workspace.sqlite3") as workspace:
        result_id = import_fixture(workspace, tmp_path)

        with pytest.raises(ValueError, match="recursive must be a boolean"):
            workspace.plan_external_imports_for_result(result_id, recursive="yes")
```

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace_external_import_planner.py -v
```

Expected: fail because planner methods are not defined.

- [ ] **Step 3: Implement planner methods and helpers**

Add methods in `Workspace` near reading queue APIs:

```python
@_synchronized
def plan_external_imports_for_result(self, result_id: str, recursive: bool = True) -> dict:
    if not isinstance(recursive, bool):
        raise ValueError("recursive must be a boolean")
    result = self.get_result(result_id)
    collector = _ExternalImportPlanCollector(self)
    path = self.get_result_reading_path(result_id, recursive=recursive)
    for mention in path["external_stops"]:
        collector.add_external_mention(mention["mention_id"], "reading_path.external_stops")
    for stop in path["unresolved_stops"]:
        collector.add_blocked(
            "missing_arxiv_id",
            [
                {
                    "kind": "unresolved_stop",
                    "id": f"{stop['result_id']}:{stop['kind']}",
                    "paper_id": result["paper_id"],
                    "result_id": stop["result_id"],
                    "proof_id": None,
                    "citation_key": None,
                    "raw_text": stop["kind"],
                    "source": "reading_path.unresolved_stops",
                }
            ],
        )
    return collector.payload(
        {
            "kind": "result_id",
            "value": result_id,
            "paper_id": result["paper_id"],
            "recursive": recursive,
        }
    )
```

Implement analogous queue and paper methods, plus a private collector that:

- fetches `external_result_mentions`, `citation_mentions`, and `bibliography_entries` rows by ID
- groups candidates by bibliography/citation arXiv ID
- checks `self._connection.execute("SELECT 1 FROM papers WHERE paper_id = ?", (f"arxiv:{arxiv_id}",))`
- emits stable IDs and sorted payloads

- [ ] **Step 4: Run workspace tests to verify green**

Run the same test command. Expected: all planner workspace tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/workspace.py tests/test_workspace_external_import_planner.py
git commit -m "feat: add external import planning workspace api"
```

---

### Task 2: MCP and CLI Exposure

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_workspace_external_import_planner_server.py`
- Test: `tests/test_cli_external_import_planner.py`

**Interfaces:**
- Consumes:
  - `Workspace.plan_external_imports_for_result(result_id, recursive=True)`
  - `Workspace.plan_external_imports_for_queue(queue_id)`
  - `Workspace.plan_external_imports_for_paper(paper_id)`
- Produces:
  - MCP wrappers `workspace_plan_external_imports_for_result`, `workspace_plan_external_imports_for_queue`, `workspace_plan_external_imports_for_paper`
  - CLI commands `plan-external-imports-for-result`, `plan-external-imports-for-queue`, `plan-external-imports-for-paper`

- [ ] **Step 1: Write failing MCP and CLI tests**

Create server tests that open a workspace, import the PDF fixture from Task 1, call the wrappers, and assert candidate counts. Also test missing workspace and unknown IDs produce `ToolError`.

Create CLI tests that run `server.main([...])` with the new commands and assert JSON output.

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
uv run pytest tests/test_workspace_external_import_planner_server.py tests/test_cli_external_import_planner.py -v
```

Expected: fail because wrappers and commands are not defined.

- [ ] **Step 3: Add MCP wrappers**

Add wrappers in `src/papergraph/server.py` next to reading queue tools. Follow the existing `_serialized_workspace_tool` and `_WORKSPACE_TOOL_ERRORS` pattern.

- [ ] **Step 4: Add CLI parsers and handlers**

Add argparse subcommands near reading queue commands, with `--direct` for result planning. Use `_run_workspace_cli_command` and `_print_json`.

- [ ] **Step 5: Run MCP/CLI tests to verify green**

Run the same focused command. Expected: all new MCP/CLI tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/papergraph/server.py tests/test_workspace_external_import_planner_server.py tests/test_cli_external_import_planner.py
git commit -m "feat: expose external import planner tools"
```

---

### Task 3: v0.9 Documentation and Release Pins

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Modify: `src/papergraph/arxiv.py`
- Modify: `scripts/check_onboarding.py`
- Modify: `.agents/skills/setting-up-papergraph/SKILL.md`
- Modify: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_onboarding.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: new MCP and CLI names from Task 2.
- Produces: release-ready `0.9.0` docs and tests.

- [ ] **Step 1: Update tests first**

Update repository/onboarding/diagnostics tests from v0.8.0 to v0.9.0 and add README expectations for:

```text
workspace_plan_external_imports_for_result
workspace_plan_external_imports_for_queue
workspace_plan_external_imports_for_paper
plan-external-imports-for-result
plan-external-imports-for-queue
plan-external-imports-for-paper
```

- [ ] **Step 2: Run docs tests to verify red**

Run:

```powershell
uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v
```

Expected: fail until docs and pins are updated.

- [ ] **Step 3: Update docs and version pins**

Update:

- package version to `0.9.0`
- pinned install commands to `v0.9.0`
- user agent to `PaperGraph/0.9.0`
- CI smoke expected output to `papergraph-mcp 0.9.0`
- README feature list and tool table
- README External Import Planner workflow

- [ ] **Step 4: Run docs tests to verify green**

Run the same docs test command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add README.md pyproject.toml uv.lock .github/workflows/ci.yml .github/ISSUE_TEMPLATE/bug_report.yml src/papergraph/arxiv.py scripts/check_onboarding.py .agents/skills/setting-up-papergraph/SKILL.md .agents/skills/setting-up-papergraph/references/client-configuration.md tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py
git commit -m "docs: prepare v0.9.0 release"
```

---

### Task 4: Final Verification, PR, and Release

**Files:**
- No code files expected unless verification exposes a bug.

**Interfaces:**
- Consumes: complete branch from Tasks 1-3.
- Produces: PR, merge to main, `v0.9.0` tag, GitHub Release.

- [ ] **Step 1: Run full local verification**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest
```

Expected: all tests pass with one skipped.

- [ ] **Step 2: Self-review branch state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate --max-count=12
rg -n 'papergraph-mcp\.git@v0\.8\.0|papergraph-mcp 0\.8\.0|PaperGraph/0\.8\.0|version = "0\.8\.0"' README.md pyproject.toml uv.lock .github scripts src tests .agents/skills/setting-up-papergraph
```

Expected: clean worktree and no active v0.8 install pins outside historical README text.

- [ ] **Step 3: Push and create PR**

Run:

```powershell
git push -u origin feature/v0.9-external-import-planner
```

Create a PR from `feature/v0.9-external-import-planner` to `main` titled `Add External Import Planner for v0.9.0`.

- [ ] **Step 4: Wait for PR CI**

Wait for GitHub Actions CI on the PR head SHA. Expected: success.

- [ ] **Step 5: Merge PR**

Squash merge after PR CI passes.

- [ ] **Step 6: Wait for main CI**

Fetch `origin/main`, confirm merge commit, and wait for push CI on main. Expected: success.

- [ ] **Step 7: Tag and verify pinned install**

Create and push:

```powershell
git tag -a v0.9.0 <main-merge-sha> -m "PaperGraph MCP v0.9.0"
git push origin v0.9.0
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.0 papergraph-mcp --version
```

Expected: `papergraph-mcp 0.9.0`.

- [ ] **Step 8: Create GitHub Release**

Create GitHub Release `PaperGraph MCP v0.9.0` on tag `v0.9.0` with highlights and verification evidence.
