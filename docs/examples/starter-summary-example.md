# PaperGraph Reading Project: Example Starter

This is a compact example artifact showing the shape of a Workspace Starter summary. It is not generated from a real unpublished paper.

## Project

- Workspace: `C:/Users/me/papergraph-projects/example/workspace.sqlite3`
- Papers: 2

## Papers Loaded

- `local:example-a`
  - Title: Example Paper A
  - Source type: `pdf`
  - Evidence status: `usable`
  - Results: 3
- `local:example-b`
  - Title: Example Paper B
  - Source type: `local`
  - Evidence status: `sparse`
  - Results: 1

## Start Here

- Evidence triage: `sparse_dependencies`.
- Candidate starting point: `local:example-a::pdf:theorem:1.1` (automatic candidate).
- Read `local:example-a::pdf:lemma:1.2` before `local:example-a::pdf:theorem:1.1`.
- Review `Evidence Triage` in each Reading Report before interpreting dependencies.
- Review `cross-paper-reading-plan.md` before treating citation evidence as a logical dependency.

## Reading Artifacts

- `starter_summary`: [START_HERE.md](START_HERE.md)
- `starter_manifest`: [papergraph-starter-manifest.json](papergraph-starter-manifest.json)
- `reading_report`: [local-example-a-reading-report.md](local-example-a-reading-report.md)
- `cross_paper_reading_plan`: [cross-paper-reading-plan.md](cross-paper-reading-plan.md)

## Reading Queue And Session

- No reading queue or session was created.

## Evidence Quality

- `sparse_paper`: one loaded paper has sparse extracted evidence.

## External Reading Risks

- Review Paper Map and Cross-Paper Reading Plan risk sections before importing external papers.

## Evidence Boundaries

- PaperGraph does not verify proofs.
- PaperGraph does not infer hidden mathematical prerequisites.
- PaperGraph does not perform semantic theorem matching.

## Next Commands

```powershell
papergraph-mcp get-paper-map --workspace C:/Users/me/papergraph-projects/example/workspace.sqlite3 --paper-id local:example-a
papergraph-mcp export-paper-reading-report --workspace C:/Users/me/papergraph-projects/example/workspace.sqlite3 --paper-id local:example-a
```
