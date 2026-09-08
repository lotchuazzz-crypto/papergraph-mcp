# External Import Review Summary v0.9.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add additive researcher-readable review summaries to each external import candidate.

**Architecture:** Extend `_ExternalImportPlanCollector._candidate_payload` to derive a deterministic `review` object from the existing per-candidate evidence list. Keep all storage tables and public plan schema version unchanged.

**Tech Stack:** Python 3.10+, pytest, existing PaperGraph workspace and MCP/CLI surfaces.

## Global Constraints

- Do not push, create a remote PR, tag, or publish from this session.
- No database schema migration for v0.9.3.
- Keep `plan_schema_version` at `1`; this is an additive response-field change.
- Do not fetch arXiv metadata during planning.
- Do not rank candidates by inferred mathematical importance.
- Keep unresolved and blocked import entries compatible with existing payloads.
- Release pins and visible version strings must become `v0.9.3` / `0.9.3` locally.

---

### Task 1: Candidate Review Payload

**Files:**
- Modify: `src/papergraph/workspace.py`
- Test: `tests/test_workspace_external_import_planner.py`

**Interfaces:**
- Consumes: `_dedupe_external_import_evidence(items: list[dict]) -> list[dict]`
- Produces: candidate payload field `review: dict` containing `local_result_ids`, `proof_ids`, `citation_keys`, `raw_texts`, and `evidence_summary`

- [ ] **Step 1: Write failing result-plan review test**

```python
def test_result_plan_candidate_review_summarizes_traceable_evidence(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_import_plan_pdf(workspace, tmp_path)

        candidate = workspace.plan_external_imports_for_result(result_id)["candidates"][0]

        assert candidate["review"] == {
            "local_result_ids": ["local:paper::pdf:theorem:1.1"],
            "proof_ids": ["local:paper::proof:2"],
            "citation_keys": ["12"],
            "raw_texts": ["[12, Theorem 3.5]"],
            "evidence_summary": (
                "Needed by 1 local result through 1 proof; citation keys: 12; "
                "cited result evidence: [12, Theorem 3.5]"
            ),
        }
    finally:
        workspace.close()
```

- [ ] **Step 2: Run test to verify RED**

Run: `uv run pytest tests/test_workspace_external_import_planner.py::test_result_plan_candidate_review_summarizes_traceable_evidence -v`

Expected: FAIL with missing `review`.

- [ ] **Step 3: Implement review builder**

Add helpers:

```python
def _external_import_candidate_review(evidence: list[dict]) -> dict:
    ...

def _sorted_present_values(items: list[dict], key: str) -> list[str]:
    ...

def _bounded_raw_texts(items: list[dict], limit: int = 5) -> list[str]:
    ...
```

Use the helper inside `_candidate_payload` after evidence deduplication.

- [ ] **Step 4: Run test to verify GREEN**

Run: `uv run pytest tests/test_workspace_external_import_planner.py::test_result_plan_candidate_review_summarizes_traceable_evidence -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/papergraph/workspace.py tests/test_workspace_external_import_planner.py && git commit -m "feat: summarize external import evidence"`

---

### Task 2: Plan Surface Coverage

**Files:**
- Modify: `tests/test_workspace_external_import_planner.py`
- Modify: `tests/test_cli_external_import_planner.py`

**Interfaces:**
- Consumes: `review` payload produced by Task 1.
- Produces: coverage for result, queue, paper, dedupe, and CLI JSON paths.

- [ ] **Step 1: Write failing/confirming surface tests**

Add assertions that:

- queue-scoped plan candidates include `review.local_result_ids`;
- paper-scoped plan candidates include citation key `12`;
- candidate review deduplicates repeated evidence;
- CLI JSON exposes `review.evidence_summary`.

- [ ] **Step 2: Run surface tests**

Run: `uv run pytest tests/test_workspace_external_import_planner.py tests/test_cli_external_import_planner.py -v`

Expected: PASS after Task 1; if a case fails, fix the review builder without changing the public shape.

- [ ] **Step 3: Commit**

Run: `git add src/papergraph/workspace.py tests/test_workspace_external_import_planner.py tests/test_cli_external_import_planner.py && git commit -m "test: cover external import review surfaces"`

---

### Task 3: v0.9.3 Local Release Preparation

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
- Test: `tests/test_repository.py`
- Test: `tests/test_onboarding.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_diagnostics.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: current v0.9.2 version and pins.
- Produces: local v0.9.3 metadata, docs, and tests.

- [ ] **Step 1: Update tests to expect v0.9.3**

Change release/version tests from `v0.9.2` / `0.9.2` to `v0.9.3` / `0.9.3`.

- [ ] **Step 2: Run release tests to verify RED**

Run: `uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v`

Expected: FAIL on stale v0.9.2 strings.

- [ ] **Step 3: Update local version strings and README**

Update package metadata, lockfile, runtime user-agent, onboarding pins, workflow smoke expected version, and README launch copy to v0.9.3. Add a README note about external import review summaries.

- [ ] **Step 4: Run release tests to verify GREEN**

Run: `uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add README.md pyproject.toml uv.lock .github scripts src tests .agents && git commit -m "docs: prepare v0.9.3 release"`

---

### Task 4: Final Local Verification And User Push Instructions

**Files:**
- No planned source edits after verification unless tests fail.

**Interfaces:**
- Consumes: all local commits on `feature/v0.9.3-external-citation-evidence`.
- Produces: clean local branch plus user-facing push, PR, merge, tag, and release instructions.

- [ ] **Step 1: Run full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 2: Scan for stale v0.9.2 pins**

Run: `rg -n 'papergraph-mcp\.git@v0\.9\.2|papergraph-mcp 0\.9\.2|PaperGraph/0\.9\.2|placeholder: "0\.9\.2"' README.md pyproject.toml uv.lock .github scripts src tests .agents\skills\setting-up-papergraph`

Expected: no output.

- [ ] **Step 3: Verify status and commit list**

Run: `git status --short --branch` and `git log --oneline --decorate origin/main..HEAD`.

Expected: clean local branch with only v0.9.3 commits.

- [ ] **Step 4: Provide push instructions**

Tell the user to run:

```powershell
cd D:\ai4math\papergraph-mcp\.worktrees\feature-v0.9.3-external-citation-evidence
git push -u origin feature/v0.9.3-external-citation-evidence
```

Then open a PR from `feature/v0.9.3-external-citation-evidence` to `main`, wait for CI, squash merge, fetch main, tag the merge commit as `v0.9.3`, run the pinned `uvx` install smoke, and create the GitHub Release.
