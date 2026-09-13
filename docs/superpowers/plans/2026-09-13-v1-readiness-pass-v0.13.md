# v1.0 Readiness Pass v0.13 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents for this implementation.

**Goal:** Build v0.13.0 as the v1.0 readiness pass: stable contract docs, first-use walkthrough, example artifacts, README links, and release pins.

**Architecture:** This is documentation and contract stabilization only. It adds no new runtime tools, database schema, or extraction logic. Tests enforce that the docs exist, link from README, and preserve core evidence boundaries.

**Tech Stack:** Markdown docs, pytest repository tests, existing Python packaging/version files.

## Global Constraints

- Release version is `0.13.0`.
- No new extraction logic, MCP tools, CLI commands, schema migrations, PDF rendering, global discovery, or symbol indexing.
- Preserve evidence-first language: no proof verification, no semantic theorem matching, no hidden prerequisite inference.
- Example artifacts must be compact, static Markdown examples.

---

### Task 1: Contract, Walkthrough, and Examples

**Files:**
- Create: `docs/reference/v1-core-contract.md`
- Create: `docs/walkthroughs/first-workspace.md`
- Create: `docs/examples/reading-report-example.md`
- Create: `docs/examples/cross-paper-reading-plan-example.md`
- Test: `tests/test_v1_readiness_docs.py`

**Interfaces:**
- Produces documentation files that README and repository tests rely on.

- [ ] **Step 1: Write failing documentation tests**

Add tests asserting that the four docs exist, contain required headings, define evidence statuses, include stable tool names, include evidence boundaries, and contain no placeholder markers.

- [ ] **Step 2: Run RED**

Run `uv run pytest tests/test_v1_readiness_docs.py -q -p no:cacheprovider --basetemp .pytest-tmp`.

Expected: fail because docs do not exist.

- [ ] **Step 3: Add docs**

Write the four Markdown files with concise content matching the v0.13 design.

- [ ] **Step 4: Run GREEN**

Run the same test command and expect pass.

- [ ] **Step 5: Commit**

Commit as `docs: add v1 readiness docs and examples`.

### Task 2: README, Version Pins, and Repository Tests

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/papergraph/arxiv.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Modify: `.agents/skills/setting-up-papergraph/SKILL.md`
- Modify: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Modify: `scripts/check_onboarding.py`
- Modify: version-pinned tests under `tests/`

**Interfaces:**
- Produces release version `0.13.0`.
- Produces README links to contract, walkthrough, and examples.

- [ ] **Step 1: Update failing repository tests first**

Change version assertions to `0.13.0`, require README links to the new docs, and require a v0.13.0 release highlight.

- [ ] **Step 2: Run RED**

Run `uv run pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider --basetemp .pytest-tmp`.

Expected: fail until version/docs are updated.

- [ ] **Step 3: Update docs/version files**

Update version pins, README docs links, release highlights, onboarding pins, and `uv.lock`.

- [ ] **Step 4: Run GREEN**

Run the same focused test command and expect pass.

- [ ] **Step 5: Commit**

Commit as `docs: prepare v0.13 v1 readiness release`.

### Task 3: Full Verification and Push

**Files:**
- No new files expected beyond previous tasks.

- [ ] **Step 1: Run full tests**

Run `uv run pytest -q -p no:cacheprovider --basetemp .pytest-tmp`.

- [ ] **Step 2: Confirm clean status**

Run `git status --short --branch`.

- [ ] **Step 3: Push**

Push branch `design/v0.13-v1-readiness-pass`.
