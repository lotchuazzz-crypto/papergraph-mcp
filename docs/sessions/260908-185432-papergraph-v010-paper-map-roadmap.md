The PaperGraph MCP project has reached v0.9.3 with external import review summaries, proof-roadmap extraction, proof-block association, reading queues, reading sessions, and local/PDF/arXiv evidence workflows in place.
The user's latest strategic question was whether the project is close to a tool mathematical researchers truly need, and the answer was that PaperGraph now has the evidence database skeleton but still lacks a researcher-facing reading assistant layer.
The most important proposed next feature is v0.10 Paper Map: a first-load overview that identifies main-result candidates, chapter/result structure, core proof path, external reading risks, and a recommended reading route.
The user explicitly wants future work to stay evidence-first and not let agents guess mathematical dependencies, semantic theorem matches, or hidden prerequisites.
README work was recently redesigned twice and merged to GitHub main, ending at `791a2a2 Merge researcher-focused README polish`, with the homepage now presenting PaperGraph as "Read math papers with evidence, not guesses."
The current feature branch `feature/v0.9.3-external-citation-evidence` is clean and pushed at `d7892dc docs: make README researcher focused`, while `origin/main` is at `791a2a2`.
Full validation after the final README polish passed with `424 passed, 1 skipped in 51.61s`, and the prior v0.9.3 code validation passed with `423 passed, 1 skipped`.
The next conversation should begin from product planning for v0.10 Paper Map rather than another low-level extraction feature, because the main gap is organizing evidence into a researcher-readable paper overview.
High-value follow-on gaps after Paper Map are dependency-role classification, notation/definition indexing, human-readable reading reports, cross-paper local literature graphs, and clearer evidence-quality status.
The next agent should resume from this log, inspect the current `README.md`, `docs/superpowers/specs`, `docs/superpowers/plans`, and tests before writing a v0.10 spec, then implement without subagents if the user repeats that constraint.

session: thread_id=01a06c45-21ff-77f2-b0f6-16c50bf24a56 save_seq=1 mode=full previous=none

# Summary

## Goal

Create a dense conversation handoff package for the next chat, focused on the current PaperGraph MCP project state and the recommended next product direction.

## Context

- Repository: `D:\ai4math\papergraph-mcp`.
- Active development worktree: `D:\ai4math\papergraph-mcp\.worktrees\feature-v0.9.3-external-citation-evidence`.
- Current feature branch: `feature/v0.9.3-external-citation-evidence`.
- Remote default branch: `origin/main`.
- Latest remote main commit observed: `791a2a2 Merge researcher-focused README polish`.
- Latest feature branch commit observed: `d7892dc docs: make README researcher focused`.
- User works primarily in Chinese and prefers the agent to independently spec, implement, push, create PRs/releases, and publish once direction is approved; however, the user has repeatedly specified "do not use subagents" for feature work.

## Key Decisions

- The project's near-term problem is not more raw extraction alone; it is transforming existing evidence into a researcher-readable paper overview.
- Recommended next feature: **v0.10 Paper Map**.
- Paper Map should summarize a loaded paper's structure without claiming proof verification or semantic theorem matching.
- Paper Map should prioritize:
  - main-result candidates,
  - section/chapter structure,
  - result hierarchy,
  - local proof path,
  - external citation/import risk,
  - recommended reading route,
  - evidence-quality warnings.
- Technical details should remain available but should not dominate first-use documentation or user-facing report surfaces.
- The evidence-first contract is central: empty dependencies mean extraction limits, not absence of mathematical dependencies.

## Work Performed

- Earlier v0.9.3 work added external import candidate review summaries so agents can explain which local result, proof, citation key, and cited result text justify importing a cited paper before downloading.
- README was first reorganized into a bilingual English/Chinese guide, then redesigned again into a researcher-focused project homepage.
- The final README design now uses:
  - centered GitHub-rendered title block,
  - tagline: `Read math papers with evidence, not guesses.`,
  - concise researcher-facing value explanation,
  - English/Chinese anchors,
  - capability tables,
  - Mermaid reading-flow diagram,
  - `What PaperGraph Does Not Do`,
  - folded `Reference` sections for tool lists, CLI shortcuts, evidence boundaries, local walkthrough, safety/privacy, release highlights, and development.
- Added a regression test: `test_readme_presents_researcher_focused_overview_before_reference`, which requires the README to expose a researcher-facing overview before dense reference material.
- Merged the README polish into `main` and pushed it to GitHub.
- Discussed remaining product gaps for mathematical researchers.

## Files Changed

- `README.md`
  - Rewritten as a researcher-first bilingual README.
  - Dense technical material moved into `<details>` reference blocks.
- `tests/test_repository.py`
  - Added `test_readme_presents_researcher_focused_overview_before_reference`.
- `docs/superpowers/specs/2026-09-08-bilingual-readable-readme-design.md`
  - Earlier README bilingual readability spec.
- `docs/superpowers/plans/2026-09-08-bilingual-readable-readme.md`
  - Earlier README bilingual implementation plan.
- `docs/superpowers/specs/2026-09-08-researcher-focused-readme-design.md`
  - Final researcher-focused README design spec.
- `docs/superpowers/plans/2026-09-08-researcher-focused-readme.md`
  - Final researcher-focused README implementation plan.

## Validation

- README/onboarding/local walkthrough tests passed after the final README polish:
  - `40 passed in 3.21s`.
- Full test suite passed on the feature branch after final README polish:
  - `424 passed, 1 skipped in 44.82s`.
- Full test suite passed on the merge-to-main candidate:
  - `424 passed, 1 skipped in 51.61s`.
- GitHub `main` was pushed from merge commit:
  - `791a2a2 Merge researcher-focused README polish`.
- Feature branch remained clean afterward:
  - `feature/v0.9.3-external-citation-evidence...origin/feature/v0.9.3-external-citation-evidence`.

## Open Questions / Next Steps

- Start the next chat by designing **v0.10 Paper Map**.
- Suggested v0.10 scope:
  - create a new workspace-level or paper-level API such as `workspace_get_paper_map(paper_id: str) -> dict`;
  - optionally add CLI export such as `papergraph-mcp --workspace ... export-paper-map PAPER_ID`;
  - classify main-result candidates using explicit title/label/abstract/introduction/section evidence, not semantic truth claims;
  - summarize section/result structure in deterministic source order;
  - expose direct evidence for why a result is considered "main candidate," "supporting," or "technical," with uncertainty status;
  - include reading-path highlights from existing proof dependency and reading queue machinery;
  - include external import risks from v0.9.3 planner review summaries;
  - add a human-readable report format that agents can show without dumping raw JSON.
- Later roadmap candidates:
  - dependency-role classifier: distinguish use as statement, method, estimate, construction, notation, or background;
  - notation and definition index: locate where objects and assumptions are introduced and used;
  - researcher-facing reading report: one-page human summary from evidence bundles;
  - cross-paper local literature graph: minimal external reading set for understanding a target result;
  - evidence-quality layer: clearer statuses for proof missing, PDF OCR risk, unresolved citation, inferred dependency, or unsupported semantic inference.
- Preserve constraints:
  - do not use subagents if the user repeats that requirement;
  - write a spec before implementation;
  - keep work evidence-first;
  - run tests before claiming completion;
  - avoid overwriting unrelated local changes or dirty worktrees.
