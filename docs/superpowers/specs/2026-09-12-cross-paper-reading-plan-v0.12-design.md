# Cross-Paper Reading Plan v0.12 Design

## Purpose

PaperGraph v0.10 made one loaded paper orientable through Paper Map. v0.11 made that orientation durable through Markdown Reading Report export.

The next gap is the original PaperGraph use case at small literature scale: a researcher has two to five related papers already loaded and wants to understand how to read them together. Window output and single-paper reports are useful, but they do not yet answer:

> Which paper and result should I read first, how do the selected papers cite or block each other, what external risks remain, and which single-paper reports should I open next?

v0.12 adds **Cross-Paper Reading Plan**: a deterministic Markdown export for an explicit set of stored papers. It composes existing Paper Map, Reading Report, citation, and external-import evidence into a small reading plan without adding new extraction or semantic matching.

## Product Goal

Given a small explicit set of loaded paper IDs, PaperGraph should export a researcher-readable Markdown plan that answers:

- what each paper contributes according to stored evidence;
- which paper/result is the best supported starting point;
- what reading sequence is recommended across the selected papers;
- which selected-paper citation edges are visible;
- which citation/import risks still point outside the selected set;
- what evidence limits prevent stronger claims.

The plan is not a literature-review generator. It should not invent mathematical summaries, infer theorem equivalence, classify hidden prerequisite relations, or claim that a citation edge is a true logical dependency. It should format and connect evidence PaperGraph already has.

## Users

- A mathematical researcher starting from a few known relevant papers.
- A research agent that needs to hand off a multi-paper reading state to another chat or session.
- A local literature-workspace maintainer who wants Markdown artifacts in Git, Obsidian, or project notes.

## Design Principles

- **Explicit paper set first:** v0.12 starts from user-provided paper IDs, not global discovery.
- **Evidence first:** every cross-paper relation must come from stored citation or reading-route evidence, or be clearly marked as missing.
- **No semantic theorem matching:** do not decide that two results are equivalent or that one theorem proves another unless existing evidence says so.
- **No new extraction logic:** consume Paper Map, Reading Report, citations, reading paths, and external import plans.
- **Markdown first:** export deterministic `.md` content; PDF/HTML can render the same model later.
- **Deterministic output:** identical workspace state and inputs produce byte-stable Markdown.
- **Small-set ergonomics:** optimize for two to eight papers, where a human can inspect the whole plan.

## Approaches Considered

### Option 1: Search-First Workspace Discovery

PaperGraph could accept a focus query, search all stored results/citations, select related papers, and emit a plan.

This is powerful but too broad for v0.12. It turns the feature into retrieval and ranking infrastructure, and it risks hiding why papers were selected. It also moves away from the current product direction: helping a reader organize known papers before doing large-scale indexing.

### Option 2: Global Citation-Graph Planner

PaperGraph could build a workspace-wide citation graph and rank papers by graph centrality or citation topology.

This is useful later, but it risks overclaiming that citation structure equals reading dependency. It also needs graph-level UX and filtering decisions that are bigger than one release.

### Option 3: Explicit Cross-Paper Reading Plan

PaperGraph accepts a small explicit set of paper IDs and produces a Markdown reading plan from existing evidence.

This is the v0.12 choice. It is narrow, useful, deterministic, and directly extends v0.10/v0.11. It keeps PaperGraph close to the original design goal: organize a few relevant papers into a logical reading chain with visible evidence boundaries.

## Scope

### In Scope

Add a cross-paper report API:

```python
def export_cross_paper_reading_plan(
    self,
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict: ...
```

Add MCP tool:

```python
workspace_export_cross_paper_reading_plan(
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict
```

Add CLI command:

```powershell
papergraph-mcp --workspace .\papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:paper-a --paper-id local:paper-b
papergraph-mcp --workspace .\papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:paper-a --paper-id local:paper-b --focus "fixed point theorem"
papergraph-mcp --workspace .\papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:paper-a --paper-id local:paper-b --output reading-plan.md
```

Generate a structured payload containing:

- plan schema version;
- format;
- input paper IDs;
- optional focus string;
- per-paper Paper Map summaries;
- per-paper Reading Report references and commands;
- recommended cross-paper reading sequence;
- explicit selected-paper citation edges;
- unresolved or external citation risks;
- evidence-quality warnings;
- generated Markdown text.

Update README/tool tables and release pins for `v0.12.0`.

### Out of Scope

- Automatic discovery of relevant papers.
- Automatic external import.
- Network calls.
- PDF export.
- HTML export.
- New citation extraction, theorem extraction, or notation extraction.
- Semantic theorem matching.
- LLM-authored mathematical summaries.
- Persistent database schema changes.
- Workspace-wide graph centrality or ranking.
- Mutation of reading sessions or reading queues.

## Public API

### Workspace API

Add to `Workspace`:

```python
def export_cross_paper_reading_plan(
    self,
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict:
    ...
```

Validation rules:

- `paper_ids` must contain between 2 and 8 distinct IDs.
- Duplicate paper IDs raise `ValueError`.
- Unknown paper IDs raise `KeyError`.
- `max_candidates_per_paper` must be an integer between `1` and `20`, matching Paper Map validation.
- `focus` may be `None` or a non-empty string after trimming. Empty strings are treated as `None`.
- The method is read-only.
- The method does not write files. File writing belongs to the CLI layer.

The returned payload:

```python
{
    "plan_schema_version": 1,
    "format": "markdown",
    "paper_ids": ["local:paper-a", "local:paper-b"],
    "focus": "fixed point theorem" | None,
    "summary": {
        "paper_count": 2,
        "recommended_start_paper_id": "local:paper-a" | None,
        "recommended_start_result_id": "local:paper-a::pdf:theorem:1.1" | None,
        "main_candidate_count": 4,
        "cross_paper_edge_count": 1,
        "external_risk_count": 2,
        "unresolved_risk_count": 1,
        "evidence_status": "usable" | "sparse" | "limited",
    },
    "papers": [
        {
            "paper_id": "local:paper-a",
            "title": "..." | None,
            "paper_map_summary": {...},
            "main_result_candidates": [...],
            "reading_route_preview": [...],
            "single_paper_report_command": "papergraph-mcp ...",
            "warnings": [...],
        }
    ],
    "cross_paper_edges": [
        {
            "source_paper_id": "local:paper-a",
            "target_paper_id": "local:paper-b",
            "kind": "citation_evidence",
            "citation_key": "12" | None,
            "source_result_id": "..." | None,
            "source_proof_id": "..." | None,
            "mention_id": "...",
            "raw_text": "...",
            "evidence": {...},
        }
    ],
    "recommended_sequence": [
        {
            "position": 1,
            "paper_id": "local:paper-a",
            "result_id": "local:paper-a::pdf:theorem:1.1" | None,
            "role": "start" | "context" | "continue" | "review",
            "reason": "selected_main_candidate" | "selected_paper_citation" | "focus_match" | "input_order",
            "evidence": {...},
        }
    ],
    "external_risks": [...],
    "warnings": [...],
    "evidence_boundaries": [...],
    "markdown": "# Cross-Paper Reading Plan: ...\n...",
}
```

### MCP Tool

Add:

```python
workspace_export_cross_paper_reading_plan(
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict
```

The tool returns the full payload, including Markdown text. It requires an active workspace and converts workspace validation errors into `ToolError`, matching existing workspace tool patterns.

### CLI

Add:

```powershell
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:a --paper-id local:b
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:a --paper-id local:b --focus "fixed point"
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:a --paper-id local:b --max-candidates-per-paper 2
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-cross-paper-reading-plan --paper-id local:a --paper-id local:b --output C:/Temp/plan.md
```

CLI behavior:

- `--paper-id` is repeatable. Do not accept comma-separated IDs in v0.12.
- Without `--output`, print Markdown to stdout.
- With `--output`, write Markdown to that path and print JSON metadata to stdout:

```json
{
  "status": "written",
  "command": "export-cross-paper-reading-plan",
  "paper_ids": ["local:a", "local:b"],
  "format": "markdown",
  "output": "C:/Temp/plan.md",
  "bytes": 12345,
  "plan_schema_version": 1
}
```

- On error, print one JSON error payload to stdout and exit with code `1`, following Reading Report Export conventions.
- `--output` must not create parent directories implicitly.
- `--output` may overwrite an existing file.

## Evidence Sources

The v0.12 implementation should consume only existing evidence:

- `Workspace.get_paper_map(paper_id, max_candidates=max_candidates_per_paper)`
- `Workspace.export_paper_reading_report(paper_id, max_candidates=max_candidates_per_paper)` for report model consistency when needed
- `Workspace.plan_external_imports_for_paper(paper_id)`
- stored citation mentions and external-result mentions
- reading-route evidence already embedded in Paper Map
- optional existing search helpers for focus scoring, if they are already local and deterministic

If focus search would require new extraction or new ranking infrastructure, v0.12 should use focus only as a display label and a conservative text filter over already-returned candidate titles/statements/reasons.

## Cross-Paper Edge Rules

Cross-paper edges are allowed only when stored evidence explicitly connects two selected papers.

Valid evidence:

- a citation mention whose resolved or stored target paper ID is one of the selected paper IDs;
- an external import candidate or already-imported item whose stored paper ID matches one of the selected paper IDs;
- a reading-route external stop whose evidence can be traced to a selected paper through stored citation/import evidence.

Invalid evidence:

- similar titles;
- similar theorem statements;
- shared arXiv IDs found only in raw text without stored resolution;
- bibliography string similarity;
- user-provided paper order alone.

When evidence is insufficient, the plan may say:

```markdown
No selected-paper citation edge was extracted between `local:a` and `local:b`.
```

It must not say that the papers are unrelated.

Edge wording should use "citation evidence connects" or "selected-paper citation edge", not "depends on", unless an existing reading-path record explicitly supports dependency language.

## Recommended Sequence

The sequence is a reading recommendation, not a dependency proof.

Generation rules:

1. Build a Paper Map for every selected paper.
2. Choose the recommended start paper/result:
   - If `focus` is supplied, prefer the highest-scoring main candidate whose title, label, statement preview, or evidence reason contains the focus tokens.
   - Otherwise prefer the highest-scoring main candidate across Paper Maps.
   - Tie-break by input paper order, then source order, then result ID.
3. Add the start item with role `start`.
4. Add selected papers cited by the start paper before or near the citing paper's route with role `context`.
5. Add remaining selected papers in input order with role `continue`.
6. Add papers with no candidates but usable metadata with role `review`.
7. Surface external and unresolved risks after the sequence, not as normal sequence items.

Every sequence item must include evidence:

- `paper_map.main_result_candidates` for selected starts;
- `cross_paper_edges` for selected-paper citation context;
- `paper_ids.input_order` for fallback ordering;
- warning evidence for sparse or limited papers.

## Evidence Quality

Plan-level evidence status:

- `usable`: at least one selected paper has usable Paper Map evidence and every selected paper exists.
- `sparse`: selected papers exist, but most maps are sparse or lack proof/citation evidence.
- `limited`: no selected paper has main-result candidates or usable route evidence.

Warnings should use stable kinds:

- `no_cross_paper_edges`: selected papers have no extracted citation edges between them.
- `sparse_paper`: one or more selected papers has sparse evidence.
- `limited_paper`: one or more selected papers has limited evidence.
- `external_dependencies`: external import candidates remain outside the selected set.
- `unresolved_references`: unresolved references remain.
- `focus_no_match`: focus text did not match candidate titles, previews, labels, or reasons.
- `edge_resolution_limited`: citation evidence exists but cannot be resolved to selected paper IDs.

Warnings should include evidence counts and IDs. Sparse evidence is a warning, not a failure.

## Markdown Content

The Markdown report should use stable headings:

```markdown
# Cross-Paper Reading Plan: <focus or N papers>

## Scope

## Paper Set

## Recommended Reading Sequence

## Cross-Paper Evidence

## Per-Paper Main Candidates

## Per-Paper Reading Reports

## External Reading Risks

## Evidence Quality

## Evidence Boundaries

## Next Commands
```

### Scope

Include:

- selected paper IDs;
- optional focus;
- format and schema version;
- selected paper count.

Do not include timestamps.

### Paper Set

For each paper:

- paper ID;
- title when known;
- result/proof/citation counts from Paper Map;
- evidence status;
- recommended start result when available.

### Recommended Reading Sequence

Render sequence items as an ordered list:

```markdown
1. `local:paper-a` / `local:paper-a::pdf:theorem:1.1` start - selected_main_candidate
2. `local:paper-b` context - selected_paper_citation from `local:paper-a`
3. `local:paper-c` continue - input_order
```

Every item should include concise evidence in prose or compact JSON.

### Cross-Paper Evidence

Render selected-paper citation edges:

```markdown
- `local:paper-a` cites selected paper `local:paper-b`.
  - Mention: `...`
  - Citation key: `12`
  - Raw text: ...
```

If no selected-paper edges exist, state that no edge was extracted. Do not infer absence of relation.

### Per-Paper Main Candidates

For each paper, include the top candidates from its Paper Map:

- result ID;
- kind;
- title or visible number;
- score;
- reason records.

This section should be compact. Full details belong in the single-paper reports.

### Per-Paper Reading Reports

Include commands to export each single-paper report:

```powershell
papergraph-mcp --workspace <WORKSPACE> export-paper-reading-report --paper-id local:paper-a --output local-paper-a-reading-report.md
```

The API cannot know the workspace path, so `<WORKSPACE>` remains a placeholder. CLI may substitute the provided workspace path in the generated Markdown only if this does not break determinism for API calls. The simpler v0.12 rule is to always use `<WORKSPACE>`.

### External Reading Risks

Aggregate external risks from all selected papers:

- import candidates outside the selected set;
- already-imported candidates not in the selected set;
- blocked/unresolved items;
- citation keys and raw snippets when available.

Selected-paper citation edges should be removed from external risk counts where possible, because they are handled in `Cross-Paper Evidence`.

### Evidence Quality

Render plan-level warnings first, then per-paper warnings.

Warnings should stay factual:

```markdown
- `no_cross_paper_edges`: no stored citation edge was extracted between the selected papers.
```

### Evidence Boundaries

Always include:

- PaperGraph does not verify proofs.
- PaperGraph does not infer hidden mathematical prerequisites.
- PaperGraph does not perform semantic theorem matching.
- Citation evidence does not imply logical dependency unless supported by reading-path evidence.
- Empty cross-paper edges mean no supported extraction evidence was found, not that no relationship exists.

### Next Commands

Include copyable commands:

```powershell
papergraph-mcp --workspace <WORKSPACE> get-paper-map local:paper-a
papergraph-mcp --workspace <WORKSPACE> export-paper-reading-report --paper-id local:paper-a
papergraph-mcp --workspace <WORKSPACE> plan-external-imports-for-paper local:paper-a
```

For every selected paper, include one report command. For brevity, include `get-paper-map` and `plan-external-imports-for-paper` commands for the recommended start paper first.

## Architecture

Create:

```text
src/papergraph/cross_paper_reading_plan.py
```

Responsibilities:

- `build_cross_paper_reading_plan(workspace, paper_ids, focus=None, max_candidates_per_paper=3) -> dict`
- `render_cross_paper_reading_plan_markdown(plan_model: dict) -> str`
- input validation helpers;
- cross-paper edge extraction helpers;
- deterministic sequence generation helpers;
- small Markdown escaping/formatting helpers.

`Workspace.export_cross_paper_reading_plan` should be a thin wrapper around this module.

`server.py` should expose MCP and CLI wrappers only. It should not contain plan rendering logic.

No database migration is needed for v0.12.

## Data Flow

1. Normalize and validate input paper IDs.
2. Load each paper through existing workspace methods.
3. Build `get_paper_map` for each paper with `max_candidates_per_paper`.
4. Collect selected-paper citation edges from stored citation/import evidence.
5. Aggregate external and unresolved risks from Paper Map and import plans.
6. Score candidate start results using Paper Map scores and optional focus token matches.
7. Build the recommended sequence with deterministic tie-breaks.
8. Compute plan-level evidence status and warnings.
9. Render deterministic Markdown.
10. Return the payload from Workspace/MCP or write Markdown through CLI `--output`.

## Focus Handling

`focus` is optional and conservative.

Normalize by:

- trimming whitespace;
- lowercasing for matching;
- splitting on whitespace;
- ignoring tokens shorter than three characters.

Use focus only to prefer already-extracted candidates whose:

- label,
- title,
- statement preview,
- or reason evidence

contains at least one focus token.

If no candidates match, keep the normal start selection and add `focus_no_match` warning. Do not call an LLM or infer mathematical relevance.

## Determinism

The plan must not use:

- timestamps;
- random IDs;
- filesystem iteration order;
- live network responses;
- environment-specific absolute paths.

Stable ordering rules:

- papers by input order;
- candidate starts by focus match, descending score, input paper order, source position, result ID;
- cross-paper edges by source paper input order, target paper input order, mention ID;
- warnings by fixed severity order, then kind, then paper ID;
- external risks by source paper input order, then existing planner order.

## Error Handling

- Fewer than two paper IDs raise `ValueError("paper_ids must contain between 2 and 8 distinct IDs")`.
- More than eight paper IDs raise the same `ValueError`.
- Duplicate paper IDs raise `ValueError("paper_ids must be distinct")`.
- Unknown paper ID raises `KeyError`.
- Invalid `max_candidates_per_paper` raises the same validation errors as Paper Map, with the parameter name adjusted where appropriate.
- Papers with no results still appear in the plan with warnings.
- Missing cross-paper edges produce a warning, not a failure.
- CLI output errors:
  - missing parent directory: JSON error, exit `1`;
  - target path is a directory: JSON error, exit `1`;
  - write permission failure: JSON error, exit `1`.

## Testing

Add focused tests for:

- Workspace payload includes schema version, format, paper IDs, summary, papers, sequence, warnings, and Markdown.
- Duplicate, too few, too many, unknown, and invalid candidate-limit inputs fail predictably.
- Per-paper Paper Map summaries are embedded for all selected papers.
- Recommended start is deterministic without focus.
- Focus changes start selection only when an extracted candidate text/reason matches focus tokens.
- `focus_no_match` warning appears when focus matches nothing.
- Cross-paper citation edge appears only when stored evidence explicitly connects selected papers.
- No cross-paper edge warning appears when selected papers have no extracted edge.
- External risks outside the selected set are aggregated.
- Sparse and empty papers are included with warnings.
- Markdown includes all required headings and evidence boundaries.
- MCP wrapper returns the payload and converts errors.
- CLI without `--output` prints Markdown.
- CLI with `--output` writes Markdown and prints JSON metadata.
- CLI reports invalid output paths.
- README/repository tests include `workspace_export_cross_paper_reading_plan`, `export-cross-paper-reading-plan`, and `v0.12.0`.

Run before handoff:

```powershell
uv run pytest -q -p no:cacheprovider
```

## Documentation

README updates should:

- describe Cross-Paper Reading Plan as the way to organize a small explicit set of related papers;
- add `workspace_export_cross_paper_reading_plan` to the complete tool reference;
- add CLI examples with repeated `--paper-id`;
- update release highlights for `v0.12.0`;
- preserve evidence-boundary language.

The README should describe this feature as a reading plan, not as a literature review or automatic survey engine.

## Release

Release as `v0.12.0`.

Release notes should emphasize:

- Markdown Cross-Paper Reading Plan export;
- explicit multi-paper input;
- evidence-backed recommended sequence;
- selected-paper citation edges;
- external and unresolved risk aggregation;
- no proof verification, semantic theorem matching, or automatic discovery.

## v1.0 Implications

Cross-Paper Reading Plan closes one of the largest remaining gaps before v1.0: PaperGraph will support both single-paper orientation and small-set literature reading artifacts.

After v0.12, the remaining v1.0 blockers should be small and stabilizing:

1. Normalize evidence-status vocabulary across Paper Map, Reading Report, and Cross-Paper Reading Plan.
2. Freeze the CLI/MCP contract for the core reading workflow.
3. Improve installation and first-workspace walkthrough documentation.
4. Run one release-candidate pass over error messages, examples, and Markdown output quality.

Notation, symbol indexing, global paper discovery, and PDF rendering should remain post-v1.0 unless a later design keeps them strictly evidence-scoped and clearly useful for the core reading workflow.
