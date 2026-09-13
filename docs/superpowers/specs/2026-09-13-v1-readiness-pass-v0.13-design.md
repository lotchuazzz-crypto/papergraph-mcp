# v1.0 Readiness Pass v0.13 Design

## Purpose

PaperGraph v0.12 closes the core reading loop: single-paper Paper Map, durable Reading Report, and explicit-set Cross-Paper Reading Plan. v0.13 should not add a new research feature. It should make the existing workflow ready for a v1.0 release candidate.

v0.13 adds **v1.0 Readiness Pass**: stable contract documentation, first-use walkthroughs, and example artifacts that show how the current tools should be used and interpreted.

## Product Goal

Given a new user or an integrating agent, PaperGraph should make the v1.0 workflow obvious:

- how to start with either MCP or CLI;
- which tools form the stable core workflow;
- what `usable`, `sparse`, and `limited` mean;
- what warning payloads mean;
- what PaperGraph explicitly does not claim;
- what Reading Report and Cross-Paper Reading Plan artifacts look like.

## Scope

### In Scope

- Add `docs/reference/v1-core-contract.md`.
- Add `docs/walkthroughs/first-workspace.md`.
- Add `docs/examples/reading-report-example.md`.
- Add `docs/examples/cross-paper-reading-plan-example.md`.
- Update README links and release highlight for `v0.13.0`.
- Update version pins to `0.13.0`.
- Add repository tests that enforce the v1.0 contract docs, walkthrough, and examples.

### Out of Scope

- New extraction logic.
- New MCP tools.
- New CLI commands.
- PDF rendering.
- Global paper discovery.
- Symbol or notation indexing.
- Database migrations.

## Contract Requirements

The contract doc must define:

- stable core tools;
- evidence statuses: `usable`, `sparse`, `limited`;
- standard warning record shape: `kind`, `message`, `evidence`;
- CLI error payload shape: `status`, `action`, `command`, `message`;
- durable Markdown artifacts: Reading Report and Cross-Paper Reading Plan;
- explicit evidence boundaries.

## Walkthrough Requirements

The first-workspace walkthrough must include:

- MCP-capable agent/client setup path;
- CLI-only fallback path;
- `doctor` check;
- workspace creation/opening;
- loading one paper;
- Paper Map;
- Reading Report export;
- Cross-Paper Reading Plan export;
- guidance to keep workspace databases outside the Git repository.

## Example Artifact Requirements

The examples must be static, compact Markdown artifacts. They must include headings and evidence-boundary text but must not pretend to be generated from a real unpublished paper.

## Release

Release as `v0.13.0`.

This should be the last feature/documentation release before `v1.0.0-rc.1`.
