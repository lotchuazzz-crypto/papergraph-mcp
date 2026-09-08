# Researcher-Focused README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the README into a researcher-focused, visually cleaner bilingual project page while preserving tested setup and reference details.

**Architecture:** Keep the README as one GitHub-rendered Markdown file. Put the product narrative first, mirror a compact Chinese section, and move dense tool/reference material into `<details>` blocks.

**Tech Stack:** Markdown, GitHub HTML support, Mermaid, pytest repository documentation checks.

## Global Constraints

- Do not add external visual assets, scripts, or GitHub-unsupported styling.
- Preserve all current tested version pins, onboarding text, tool names, CLI names, evidence boundary phrases, walkthrough phrases, and safety limits from the design spec.
- Keep full bilingual navigation at the top.
- Avoid burying the main product value below technical tool lists.

---

### Task 1: Lock The README Presentation Contract

**Files:**
- Modify: `tests/test_repository.py`

**Interfaces:**
- Consumes: `README.md` as UTF-8 text.
- Produces: a regression test that fails when the README lacks a researcher-facing overview before reference material.

- [x] **Step 1: Add a failing test**

Add `test_readme_presents_researcher_focused_overview_before_reference` asserting the tagline, main feature section, researcher section, flow section, `Complete Tool Reference`, and `<details>`.

- [x] **Step 2: Run the test**

Run:

```powershell
uv run pytest tests/test_repository.py::test_readme_presents_researcher_focused_overview_before_reference -v
```

Expected: FAIL because the current README does not contain the new tagline or structure.

### Task 2: Rewrite The README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the existing tested README strings.
- Produces: a bilingual README with narrative overview first and dense technical material in reference details.

- [ ] **Step 1: Replace the top section**

Use a centered GitHub Markdown title block with badges, tagline, short value paragraph, and language anchors.

- [ ] **Step 2: Add researcher-facing English sections**

Create `What PaperGraph Helps You Do`, `Why Researchers Use It`, `Quick Start`, `Ask your agent to set it up`, `A Typical Reading Flow`, and `What PaperGraph Does Not Do`.

- [ ] **Step 3: Add compact Chinese mirror sections**

Create the Chinese equivalent with the same reader journey and without duplicating the entire tool reference.

- [ ] **Step 4: Move dense details into reference blocks**

Create `Reference` with `<details>` blocks for complete tool reference, CLI shortcuts, evidence notes, local walkthrough, safety/privacy, release highlights, development, limitations, and contributing/license.

### Task 3: Verify And Publish

**Files:**
- Modify: `README.md`
- Modify: `tests/test_repository.py`
- Create: `docs/superpowers/specs/2026-09-08-researcher-focused-readme-design.md`
- Create: `docs/superpowers/plans/2026-09-08-researcher-focused-readme.md`

**Interfaces:**
- Consumes: pytest documentation tests.
- Produces: a committed, pushed, and merged README update.

- [ ] **Step 1: Run targeted documentation tests**

```powershell
uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_readme_local_workspace_walkthrough.py -v
```

Expected: all pass.

- [ ] **Step 2: Run full test suite**

```powershell
uv run pytest
```

Expected: `423 passed, 1 skipped` or the updated count with no failures.

- [ ] **Step 3: Commit and push**

Commit the README, test, spec, and plan. Push the feature branch, merge into `main`, and push `main`.
