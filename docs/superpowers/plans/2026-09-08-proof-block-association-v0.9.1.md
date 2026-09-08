# Proof Block Association v0.9.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build conservative TeX proof environment extraction and adjacent result association for v0.9.1.

**Architecture:** Extend `papergraph.parser` so LaTeX imports emit proof source spans and `ProofEvidence` records instead of an empty proof tuple. Reuse and extend proof-local mention and citation extractors so downstream reading paths and external import planning begin working for TeX projects without schema changes.

**Tech Stack:** Python 3.10+, existing LaTeX parser regex approach, existing evidence dataclasses, SQLite workspace import path, pytest.

## Global Constraints

- Release version is `0.9.1`.
- No subagents for this implementation.
- No SQLite schema changes.
- No live arXiv calls while extracting proofs.
- TeX proof association must be conservative and deterministic.
- v0.9.1 does not implement roadmap extraction or citation-level import planning.

---

## File Structure

- Modify `src/papergraph/parser.py`: parse TeX proof environments, build proof spans, associate proofs to adjacent results, and reuse evidence extractors.
- Modify `src/papergraph/evidence_extractors.py`: resolve proof-local LaTeX label refs to stored local result labels.
- Modify `tests/test_project.py`: cover TeX proof extraction at evidence-document level.
- Modify `tests/test_workspace_evidence.py`: cover workspace proof and dependency behavior for TeX imports.
- Modify `tests/test_workspace_external_import_planner.py`: cover planner visibility after TeX proof extraction.
- Modify `README.md`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `src/papergraph/arxiv.py`, `scripts/check_onboarding.py`, `.agents/skills/setting-up-papergraph/SKILL.md`, `.agents/skills/setting-up-papergraph/references/client-configuration.md`, and version-pinned tests for `v0.9.1`.

---

### Task 1: TeX Proof Extraction

**Files:**
- Modify: `src/papergraph/parser.py`
- Modify: `src/papergraph/evidence_extractors.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Consumes: `LoadedProject.text`, `LoadedProject.spans`, existing `ResultEvidence` records.
- Produces: proof `SourceSpanEvidence` records and `ProofEvidence` records inside `latex_project_to_evidence_document(...)`.

- [ ] **Step 1: Write failing parser tests**

Add tests that create a temporary TeX project and call:

```python
document = latex_project_to_evidence_document(
    "local:paper",
    "local",
    str(tex_path),
    None,
    load_project(tex_path),
)
```

Assert:

- one theorem and one immediately following proof produce `len(document.proofs) == 1`
- the proof has `result_id == "local:paper::th:main"`
- the proof has `association_basis == "immediately_follows_result"`
- the proof uses `method == "latex_proof_environment"`
- proof-local `\cref{lem:base}` produces a resolved local result mention
- a second proof after the same theorem remains unresolved with `result_id is None`

- [ ] **Step 2: Run parser tests to verify red**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_project.py -v
```

Expected: new tests fail because TeX imports currently emit no proof records.

- [ ] **Step 3: Implement TeX proof blocks**

In `src/papergraph/parser.py`:

- import `ProofEvidence`
- import `extract_local_result_mentions`, `extract_citation_mentions`, and `extract_external_result_mentions`
- extend `extract_local_result_mentions` to parse `\ref`, `\eqref`, `\autoref`, `\cref`, and `\Cref` labels against `ResultEvidence.label`
- add a `ParsedProofBlock` dataclass or tuple carrying `position`, `body`, and optional title
- parse `\begin{proof}...\end{proof}` over `project.text`
- sort result nodes and proof blocks by source offset when associating
- add proof spans after result spans so result span indices stay stable
- create proof IDs as `f"{paper_id}::proof:{n}"`
- for each proof, associate with nearest preceding result if that result has not already been associated and no proof block intervenes
- use `association_confidence=0.8` for adjacent TeX proof association and `0.0` for unresolved proofs
- use `confidence=1.0` for the environment extraction itself

- [ ] **Step 4: Run parser tests to verify green**

Run the same parser test command. Expected: all `tests/test_project.py` tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/parser.py tests/test_project.py
git commit -m "feat: extract tex proof environments"
```

---

### Task 2: Workspace Proof Dependencies From TeX

**Files:**
- Modify: `tests/test_workspace_evidence.py`
- Modify: `tests/test_workspace_external_import_planner.py`

**Interfaces:**
- Consumes: Task 1's TeX `ProofEvidence` records and existing workspace import.
- Produces: verified `get_result_proof`, `get_proof_dependencies`, and external import planner behavior for TeX proof evidence.

- [ ] **Step 1: Write failing workspace tests**

Add tests that import TeX projects through `Workspace.import_project(...)`.

Test local dependency:

```latex
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}
\begin{lemma}\label{lem:base}
Base lemma.
\end{lemma}
\begin{theorem}\label{th:main}
Main theorem.
\end{theorem}
\begin{proof}
By \cref{lem:base}.
\end{proof}
```

Assert:

- `get_result_proof("local:paper::th:main")` has a known proof
- `get_proof_dependencies(..., recursive=False)` includes `local:paper::lem:base` in `known.resolved_local_results`
- the reading path has an edge from theorem to lemma

Test external dependency:

```latex
\begin{theorem}\label{th:main}
Main theorem.
\end{theorem}
\begin{proof}
We apply [12, Theorem 3.5].
\end{proof}
```

Import an `EvidenceDocument` or workspace fixture that includes bibliography entry `[12] ... arXiv:2401.12345v2` if the TeX project path does not yet parse `.bib` entries into bibliography evidence. Assert `plan_external_imports_for_result` reports one candidate `2401.12345`.

- [ ] **Step 2: Run workspace tests to verify red**

Run:

```powershell
uv run pytest tests/test_workspace_evidence.py tests/test_workspace_external_import_planner.py -v
```

Expected: local proof/dependency tests fail before Task 1 implementation, then pass after Task 1; external planner test may require adding bibliography evidence support through the existing import path or scoped fixture.

- [ ] **Step 3: Adjust implementation only if workspace integration exposes gaps**

If local dependencies do not resolve:

- confirm `extract_local_result_mentions` runs over Task 1 proofs
- confirm proof span indices point to proof text
- confirm result labels are visible in `_result_lookup`

If external planner cannot see `[12, Theorem 3.5]` because TeX bibliography evidence is absent, keep v0.9.1 focused and test citation mention extraction only when a bibliography entry is present through existing evidence document fixtures. Do not implement full BibTeX parsing in this patch.

- [ ] **Step 4: Run workspace tests to verify green**

Run the same command. Expected: all selected workspace tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_workspace_evidence.py tests/test_workspace_external_import_planner.py src/papergraph/parser.py
git commit -m "test: cover tex proof dependency integration"
```

---

### Task 3: v0.9.1 Release Pins and Docs

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
- Consumes: Task 1-2 behavior.
- Produces: release-ready docs and version metadata for `v0.9.1`.

- [ ] **Step 1: Update version tests first**

Change tests from `0.9.0`/`v0.9.0` to `0.9.1`/`v0.9.1`. Add a README expectation mentioning TeX proof environment association.

- [ ] **Step 2: Run docs tests to verify red**

Run:

```powershell
uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v
```

Expected: failures until release pins and README are updated.

- [ ] **Step 3: Update docs and pins**

Update all active release pins and README language to v0.9.1. Add a concise README note that TeX proof environments are associated to immediately preceding results and feed proof dependency extraction.

- [ ] **Step 4: Run docs tests to verify green**

Run the same docs test command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add README.md pyproject.toml uv.lock .github/workflows/ci.yml .github/ISSUE_TEMPLATE/bug_report.yml src/papergraph/arxiv.py scripts/check_onboarding.py .agents/skills/setting-up-papergraph/SKILL.md .agents/skills/setting-up-papergraph/references/client-configuration.md tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py
git commit -m "docs: prepare v0.9.1 release"
```

---

### Task 4: Final Verification, PR, and Release

**Files:**
- No expected code changes unless verification exposes a bug.

**Interfaces:**
- Consumes: completed v0.9.1 branch.
- Produces: PR, merge to main, `v0.9.1` tag, GitHub Release.

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
rg -n 'papergraph-mcp\.git@v0\.9\.0|papergraph-mcp 0\.9\.0|PaperGraph/0\.9\.0|placeholder: "0\.9\.0"' README.md pyproject.toml uv.lock .github scripts src tests .agents/skills/setting-up-papergraph
```

Expected: clean worktree and no active v0.9.0 release pins.

- [ ] **Step 3: Push and create PR**

Run:

```powershell
git push -u origin feature/v0.9.1-proof-block-association
```

Create a PR from `feature/v0.9.1-proof-block-association` to `main` titled `Add TeX proof block association for v0.9.1`.

- [ ] **Step 4: Wait for PR CI**

Wait for GitHub Actions CI on the PR head SHA. Expected: success.

- [ ] **Step 5: Merge PR**

Squash merge after PR CI passes.

- [ ] **Step 6: Wait for main CI**

Fetch `origin/main`, confirm merge commit, and wait for push CI on main. Expected: success.

- [ ] **Step 7: Tag and verify pinned install**

Create and push:

```powershell
git tag -a v0.9.1 <main-merge-sha> -m "PaperGraph MCP v0.9.1"
git push origin v0.9.1
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.1 papergraph-mcp --version
```

Expected: `papergraph-mcp 0.9.1`.

- [ ] **Step 8: Create GitHub Release**

Create GitHub Release `PaperGraph MCP v0.9.1` on tag `v0.9.1` with highlights and verification evidence.
