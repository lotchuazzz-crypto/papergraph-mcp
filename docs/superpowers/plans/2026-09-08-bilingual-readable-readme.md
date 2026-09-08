# Bilingual Readable README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite README into a clearer single-file English/Chinese guide while preserving tested setup, tool, safety, and release content.

**Architecture:** Edit `README.md` only for user-facing documentation, then run the repository's README/onboarding tests and full suite. Keep existing docs and tests unchanged unless a test exposes an outdated readability assumption.

**Tech Stack:** GitHub-flavored Markdown, pytest.

## Global Constraints

- Keep one `README.md`.
- Provide language anchors for English and 中文.
- Preserve v0.9.3 install pins.
- Preserve all tested tool names and workflow command names.
- Do not push until local verification passes.

---

### Task 1: Rewrite README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: current README content and tested strings.
- Produces: clearer bilingual README with grouped sections.

- [ ] Replace the current README with the bilingual structure from the spec.
- [ ] Keep all command examples and tested tool names present.
- [ ] Keep safety limits and limitations present.

### Task 2: Verify And Push

**Files:**
- No planned source edits unless tests fail.

- [ ] Run `uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_readme_local_workspace_walkthrough.py -v`.
- [ ] Run `uv run pytest`.
- [ ] Clean `.tmp` safely.
- [ ] Commit README/spec/plan.
- [ ] Push `feature/v0.9.3-external-citation-evidence`.
