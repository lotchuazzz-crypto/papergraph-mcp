# Cross-Paper Reading Plan: fixed point

This is a compact example artifact showing the shape of a PaperGraph Cross-Paper Reading Plan. It is not generated from a real unpublished paper.

## Scope

- Paper count: 2
- Paper IDs: `local:example-a`, `arxiv:2401.12345`
- Focus: `fixed point`
- Plan format: `markdown`
- Plan schema version: 1

## Paper Set

- `local:example-a`
  - Title: Example Main Paper
  - Evidence status: `usable`
  - Recommended start result: `local:example-a::pdf:theorem:1.1`
- `arxiv:2401.12345`
  - Title: Example Context Paper
  - Evidence status: `usable`
  - Recommended start result: `arxiv:2401.12345::tex:theorem:main`

## Recommended Reading Sequence

1. `local:example-a` / `local:example-a::pdf:theorem:1.1` start - selected_main_candidate
2. `arxiv:2401.12345` context - selected_paper_citation

## Cross-Paper Evidence

- `local:example-a` cites selected paper `arxiv:2401.12345`.
  - Mention: `local:example-a::external-mention:1`
  - Citation key: `12`
  - Raw text: [12, Theorem 3.5]

This is selected-paper citation evidence. Citation evidence does not imply logical dependency unless supported by reading-path evidence.

## Per-Paper Main Candidates

- `local:example-a::pdf:theorem:1.1`, score 7
- `arxiv:2401.12345::tex:theorem:main`, score 6

## Per-Paper Reading Reports

```powershell
papergraph-mcp --workspace <WORKSPACE> export-paper-reading-report --paper-id local:example-a
papergraph-mcp --workspace <WORKSPACE> export-paper-reading-report --paper-id arxiv:2401.12345
```

## External Reading Risks

- `local:example-a` has one unresolved bibliography item outside the selected set.

## Evidence Quality

- `unresolved_references`: Unresolved references remain in the selected evidence.

## Evidence Boundaries

- PaperGraph does not verify proofs.
- PaperGraph does not infer hidden mathematical prerequisites.
- PaperGraph does not perform semantic theorem matching.
- Citation evidence does not imply logical dependency unless supported by reading-path evidence.
- Empty cross-paper edges mean no supported extraction evidence was found, not that no relationship exists.

## Next Commands

```powershell
papergraph-mcp --workspace <WORKSPACE> get-paper-map local:example-a
papergraph-mcp --workspace <WORKSPACE> plan-external-imports-for-paper local:example-a
```
