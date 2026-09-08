# Proof Roadmap Extraction v0.9.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract conservative proof-roadmap mentions of local results and feed them into existing proof dependency and reading-path APIs.

**Architecture:** Add roadmap extraction to `papergraph.evidence_extractors` as an additional producer of `LocalResultMentionEvidence`. Keep storage and query behavior unchanged by reusing the existing `local_result_mentions` table and dependency traversal.

**Tech Stack:** Python 3.10+, pytest, existing PaperGraph evidence dataclasses and workspace APIs.

## Global Constraints

- No database schema migration for v0.9.2.
- Only extract explicit local result names inside bounded proof-roadmap windows.
- Do not infer unstated mathematical dependencies.
- Keep unresolved and ambiguous roadmap mentions as reviewable evidence.
- Do not use subagents.
- Release pins and visible version strings must become `v0.9.2` / `0.9.2`.

---

### Task 1: Roadmap Mention Extraction

**Files:**
- Modify: `src/papergraph/evidence_extractors.py`
- Test: `tests/test_evidence_extractors.py`

**Interfaces:**
- Consumes: `extract_local_result_mentions(paper_id: str, proofs: tuple[ProofEvidence, ...], results: tuple[ResultEvidence, ...]) -> tuple[LocalResultMentionEvidence, ...]`
- Produces: `LocalResultMentionEvidence` records with `method="proof_roadmap_result_regex"` and `confidence=0.72`

- [ ] **Step 1: Write the failing grouped-roadmap test**

```python
def test_extracts_grouped_proof_roadmap_mentions():
    spans = (
        span("Lemma 1.1. Base estimate.", 0),
        span("Lemma 1.2. Bootstrap estimate.", 1),
        span("Theorem 1.3. Main result.", 2),
        span("Proof. It remains to prove Lemmas 1.1 and 1.2.", 3),
    )

    document = build_pdf_evidence_document("local:paper-a", "paper.pdf", spans)

    roadmap_mentions = [
        mention
        for mention in document.local_result_mentions
        if mention.method == "proof_roadmap_result_regex"
    ]
    assert [(mention.kind, mention.visible_number, mention.target_result_id) for mention in roadmap_mentions] == [
        ("lemma", "1.1", "local:paper-a::pdf:lemma:1.1"),
        ("lemma", "1.2", "local:paper-a::pdf:lemma:1.2"),
    ]
```

- [ ] **Step 2: Run the new test to verify RED**

Run: `uv run pytest tests/test_evidence_extractors.py::test_extracts_grouped_proof_roadmap_mentions -v`

Expected: FAIL because no `proof_roadmap_result_regex` mentions exist.

- [ ] **Step 3: Implement bounded roadmap extraction**

Add helper regexes for roadmap triggers and plural/singular result names. Add an internal helper that scans only a short post-trigger window and resolves mentions through the existing result lookup.

- [ ] **Step 4: Run the extraction test to verify GREEN**

Run: `uv run pytest tests/test_evidence_extractors.py::test_extracts_grouped_proof_roadmap_mentions -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/papergraph/evidence_extractors.py tests/test_evidence_extractors.py && git commit -m "feat: extract proof roadmap mentions"`

---

### Task 2: Reading Path Integration And Deduplication

**Files:**
- Modify: `src/papergraph/evidence_extractors.py`
- Test: `tests/test_workspace_evidence.py`
- Test: `tests/test_workspace_reading.py`

**Interfaces:**
- Consumes: roadmap mentions stored through existing import flow.
- Produces: direct proof dependencies and reading path edges without duplicate targets.

- [ ] **Step 1: Write failing integration tests**

Add a LaTeX import test where a theorem proof says `It remains to prove Lemmas 1.1 and 1.2.` and assert that `get_proof_dependencies(..., recursive=False)` returns both lemma result IDs.

Add a reading path test where the same theorem depends on those lemmas and assert `get_result_reading_path` contains theorem-to-lemma edges.

Add a dedupe test where the proof has both `\cref{lem:base}` and `It remains to prove Lemma 1.1.` for the same target and assert dependencies contain the target once.

- [ ] **Step 2: Run the integration tests to verify RED**

Run: `uv run pytest tests/test_workspace_evidence.py::test_latex_import_populates_proof_roadmap_dependencies tests/test_workspace_reading.py::test_get_result_reading_path_uses_proof_roadmap_dependencies tests/test_workspace_evidence.py::test_latex_import_dedupes_roadmap_and_label_dependency -v`

Expected: FAIL because roadmap extraction is not yet connected or deduped.

- [ ] **Step 3: Connect and dedupe roadmap mentions**

Ensure `extract_local_result_mentions` appends roadmap mentions after TeX label and plain result mentions, while suppressing duplicate resolved targets already seen in stronger mention methods.

- [ ] **Step 4: Run the integration tests to verify GREEN**

Run: `uv run pytest tests/test_workspace_evidence.py::test_latex_import_populates_proof_roadmap_dependencies tests/test_workspace_reading.py::test_get_result_reading_path_uses_proof_roadmap_dependencies tests/test_workspace_evidence.py::test_latex_import_dedupes_roadmap_and_label_dependency -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/papergraph/evidence_extractors.py tests/test_workspace_evidence.py tests/test_workspace_reading.py && git commit -m "test: cover proof roadmap reading paths"`

---

### Task 3: v0.9.2 Release Pins And Documentation

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
- Consumes: current v0.9.1 pins and version strings.
- Produces: v0.9.2 package metadata and onboarding references.

- [ ] **Step 1: Write/update release pin tests to expect v0.9.2**

Change onboarding, CLI, diagnostics, and server tests so stale v0.9.1 pins fail.

- [ ] **Step 2: Run release pin tests to verify RED**

Run: `uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v`

Expected: FAIL with stale version and pin references.

- [ ] **Step 3: Update version strings and docs**

Update all visible install pins and package metadata from v0.9.1 to v0.9.2. Add a README note that proof-roadmap phrases can now contribute to reading paths.

- [ ] **Step 4: Run release pin tests to verify GREEN**

Run: `uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add README.md pyproject.toml uv.lock .github scripts src tests .agents && git commit -m "docs: prepare v0.9.2 release"`

---

### Task 4: Full Verification, PR, And Release

**Files:**
- No planned source edits after verification unless tests fail.

**Interfaces:**
- Consumes: completed implementation commits.
- Produces: PR, merged main, tag `v0.9.2`, GitHub Release.

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 2: Check for stale v0.9.1 pins**

Run: `rg -n 'papergraph-mcp\.git@v0\.9\.1|papergraph-mcp 0\.9\.1|PaperGraph/0\.9\.1|placeholder: "0\.9\.1"' README.md pyproject.toml uv.lock .github scripts src tests .agents\skills\setting-up-papergraph`

Expected: no output.

- [ ] **Step 3: Push and create PR**

Run: `git push -u origin feature/v0.9.2-proof-roadmap-extraction`

Create PR titled `Add proof roadmap extraction for v0.9.2`.

- [ ] **Step 4: Wait for PR CI and merge**

Expected: all PR CI jobs pass before merge.

- [ ] **Step 5: Verify main CI, tag, smoke-test, and create release**

After merge, wait for main CI success. Then create and push annotated tag `v0.9.2`, verify:

`uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.2 papergraph-mcp --version`

Expected: `papergraph-mcp 0.9.2`.

Create GitHub Release `PaperGraph MCP v0.9.2`.
