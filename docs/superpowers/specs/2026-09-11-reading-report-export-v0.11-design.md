# Reading Report Export v0.11 Design

## Purpose

PaperGraph v0.10 added Paper Map: an evidence-first first-load overview for one stored paper. It helps a researcher see main-result candidates, local structure, reading route, external risks, and evidence-quality warnings.

The next gap is persistence. Window output is useful during an agent conversation, but it is too ephemeral for mathematical reading. A researcher needs a report that can be saved, shared, checked into notes, attached to a reading session, or reopened later without rerunning the whole conversation.

v0.11 adds **Reading Report Export**: a deterministic Markdown report generated from existing PaperGraph evidence. The report should summarize a paper's logical reading chain, external reading risks, and evidence boundaries in a form that is useful outside the MCP chat window.

## Product Goal

Given a loaded paper, PaperGraph should export a researcher-readable Markdown report that answers:

> What should I read first, what local results and proofs support it, which external papers may be needed, and what evidence limits should I keep in mind?

The report is not a mathematical summary engine. It should not invent prose explanations of proof ideas, verify proofs, infer unstated prerequisites, or perform semantic theorem matching. It should format and explain the evidence PaperGraph already has.

## Users

- A mathematical researcher who wants a saved reading handout after loading a paper.
- A research agent that needs to hand off its reading state to another chat or session.
- A local literature-workspace maintainer who wants Markdown artifacts in Git, Obsidian, or a project notes folder.

## Design Principles

- **Markdown first:** v0.11 exports deterministic `.md` content only. PDF can come later by rendering the Markdown/report model.
- **Evidence first:** every claim in the report must be grounded in existing PaperGraph evidence or marked as an extraction limit.
- **No new extraction logic:** the feature consumes Paper Map, reading path, source slices, and external import plans; it does not add new theorem/proof/citation extractors.
- **No semantic inference:** do not classify mathematical meaning beyond already-supported evidence labels, result kinds, priorities, warnings, and source traces.
- **Portable artifact:** the output should be useful in GitHub, Obsidian, plain text editors, and terminal workflows.
- **Deterministic output:** repeated exports from the same workspace state should produce byte-stable Markdown except for an optional user-supplied output path.

## Scope

### In Scope

- Add a paper-level report API:

```python
def export_paper_reading_report(
    self,
    paper_id: str,
    max_candidates: int = 5,
) -> dict: ...
```

- Add MCP tool:

```python
workspace_export_paper_reading_report(
    paper_id: str,
    max_candidates: int = 5,
) -> dict
```

- Add CLI command:

```powershell
papergraph-mcp --workspace .\papergraph.sqlite3 export-paper-reading-report local:paper-a
papergraph-mcp --workspace .\papergraph.sqlite3 export-paper-reading-report local:paper-a --output report.md
papergraph-mcp --workspace .\papergraph.sqlite3 export-paper-reading-report local:paper-a --max-candidates 3
```

- Generate a structured report payload containing:
  - report schema version;
  - paper metadata;
  - Paper Map summary;
  - main-result candidates and evidence reasons;
  - recommended reading route;
  - local logic chain;
  - external reading risks;
  - evidence-quality warnings;
  - evidence boundaries;
  - generated Markdown text.
- Provide deterministic Markdown rendering from that payload.
- Support CLI `--output` to write the Markdown report to a user-chosen file.
- Print JSON metadata from the CLI even when writing a Markdown file.
- Update README/tool tables and release pins for `v0.11.0`.

### Out of Scope

- PDF export.
- HTML export.
- LLM-authored natural-language summaries.
- New definition/notation indexing.
- Dependency-role classification beyond existing route priorities and evidence kinds.
- Automatic external paper import.
- Reading-session mutation.
- Persistent database schema changes.
- Live network calls.

## Public API

### Workspace API

Add to `Workspace`:

```python
def export_paper_reading_report(
    self,
    paper_id: str,
    max_candidates: int = 5,
) -> dict:
    ...
```

The returned payload:

```python
{
    "report_schema_version": 1,
    "format": "markdown",
    "paper_id": "local:paper-a",
    "title": "..." | None,
    "summary": {
        "recommended_start_result_id": "...",
        "main_candidate_count": 2,
        "reading_route_count": 6,
        "external_risk_count": 1,
        "unresolved_risk_count": 1,
        "evidence_status": "usable" | "sparse" | "limited",
    },
    "sections": [
        {
            "id": "paper-map",
            "title": "Paper Map",
            "items": [...],
        }
    ],
    "markdown": "# Reading Report: ...\n...",
    "warnings": [],
}
```

Validation rules:

- Unknown `paper_id` raises `KeyError`.
- Invalid `max_candidates` follows `get_paper_map` validation.
- The method is read-only.
- The method does not write files. File writing belongs to the CLI layer.

### MCP Tool

Add:

```python
workspace_export_paper_reading_report(
    paper_id: str,
    max_candidates: int = 5,
) -> dict
```

The tool returns the full payload, including Markdown text. It requires an active workspace and converts workspace validation errors into `ToolError`, matching existing workspace tool patterns.

### CLI

Add:

```powershell
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-paper-reading-report local:paper
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-paper-reading-report local:paper --output C:/Temp/report.md
papergraph-mcp --workspace C:/Temp/papergraph.sqlite3 export-paper-reading-report local:paper --max-candidates 3
```

CLI behavior:

- Without `--output`, print the Markdown report to stdout by default.
- With `--output`, write Markdown to that path and print JSON metadata to stdout:

```json
{
  "status": "written",
  "command": "export-paper-reading-report",
  "paper_id": "local:paper",
  "format": "markdown",
  "output": "C:/Temp/report.md",
  "bytes": 12345,
  "report_schema_version": 1
}
```

- On error, print one JSON error payload to stdout and exit with code `1`, following existing CLI workspace command conventions.
- `--output` must not create parent directories implicitly. If the parent directory does not exist, return an error.
- `--output` may overwrite an existing file; this is normal CLI behavior and should be documented.

## Report Content

The Markdown report should use stable headings:

```markdown
# Reading Report: <paper title or paper_id>

## Paper

## Paper Map

## Main-Result Candidates

## Recommended Reading Route

## Local Logic Chain

## External Reading Risks

## Evidence Quality

## Evidence Boundaries

## Next Commands
```

### Paper

Include:

- paper ID;
- source type;
- title when known;
- result/proof/citation counts;
- report format and schema version.

Do not include timestamps, because they break deterministic output.

### Paper Map

Summarize the Paper Map payload:

- recommended start result ID;
- evidence status;
- number of main candidates;
- number of external risks;
- number of unresolved risks.

### Main-Result Candidates

For each candidate from `get_paper_map`:

- result ID;
- kind;
- title/visible number when available;
- statement preview;
- score;
- explicit evidence reasons.

Reason text should be copied or lightly formatted from Paper Map reason records, not rewritten into stronger mathematical claims.

### Recommended Reading Route

Render route items as an ordered list:

```markdown
1. `result_id` start - selected_main_candidate
2. `proof_id` required - proof_evidence
3. `result_id` recommended - local_dependency
4. `external_stop` caution - external_risk
```

Every item should include:

- target kind;
- target ID;
- priority;
- reason;
- concise evidence reference.

### Local Logic Chain

This section should be derived from the reading route and reading path evidence already embedded in Paper Map.

It should describe local result dependencies as evidence records:

```markdown
- `local:paper::pdf:theorem:1.1` uses local evidence involving:
  - `local:paper::pdf:lemma:1.2`
```

If no local dependency evidence is available, say:

```markdown
No local dependency evidence was extracted for the recommended route.
```

This is an extraction statement, not a mathematical statement.

### External Reading Risks

Embed the existing `external_risks` plan:

- import candidates;
- already-imported candidates;
- blocked items;
- candidate review summaries;
- citation keys;
- raw cited-result text snippets when available.

Do not recommend downloading anything automatically. The report should phrase candidates as review targets:

```markdown
Review candidate: arXiv:2401.12345
```

### Evidence Quality

Render warnings from `paper_map["evidence_quality"]["warnings"]`:

- missing proof evidence;
- no main candidate;
- external dependencies;
- unresolved references;
- sparse/limited extraction.

Warnings should keep their evidence counts or IDs.

### Evidence Boundaries

Always include:

- PaperGraph does not verify proofs.
- PaperGraph does not infer hidden mathematical prerequisites.
- PaperGraph does not perform semantic theorem matching.
- Empty dependencies mean no supported extraction evidence was found, not that no mathematical dependencies exist.

### Next Commands

Include copyable commands that continue from the report:

```powershell
papergraph-mcp --workspace <WORKSPACE> get-paper-map <PAPER_ID>
papergraph-mcp --workspace <WORKSPACE> create-reading-queue <RESULT_ID>
papergraph-mcp --workspace <WORKSPACE> plan-external-imports-for-paper <PAPER_ID>
```

Because the workspace path may not be known inside `Workspace`, the API should use `<WORKSPACE>` as a placeholder. CLI output may substitute the actual workspace path when available, but this is optional for v0.11.

## Data Flow

1. Validate `paper_id` and `max_candidates`.
2. Call `get_paper_map(paper_id, max_candidates=max_candidates)`.
3. Build a report payload from the Paper Map.
4. Render deterministic Markdown from the payload.
5. Return the payload from Workspace/MCP.
6. CLI either prints Markdown or writes it to `--output`.

This keeps report export as a formatting layer over evidence that already exists.

## Architecture

Create a focused module:

```text
src/papergraph/reading_report.py
```

Responsibilities:

- `build_paper_reading_report(workspace, paper_id, max_candidates=5) -> dict`
- `render_paper_reading_report_markdown(report_model: dict) -> str`
- small Markdown escaping/formatting helpers

`Workspace.export_paper_reading_report` should be a thin wrapper around this module.

`server.py` should expose MCP and CLI wrappers only. It should not contain report rendering logic.

## Markdown Rendering Rules

- Use GitHub-flavored Markdown.
- Use ATX headings (`#`, `##`, `###`).
- Use fenced code blocks for commands.
- Wrap IDs and tool names in backticks.
- Use bullet lists and ordered lists only; no tables in v0.11. Tables are harder to read in narrow terminal output and harder to maintain deterministically.
- Escape Markdown-sensitive characters in paper titles and free text where needed.
- Keep statement previews bounded to the previews already provided by Paper Map.
- Do not include timestamps.

## Error Handling

- Unknown paper ID raises `KeyError`.
- Invalid `max_candidates` raises `ValueError`.
- Report generation should return valid Markdown for papers with no results.
- Papers with sparse evidence should produce warnings, not failures.
- CLI `--output` errors:
  - missing parent directory: JSON error, exit `1`;
  - target path is a directory: JSON error, exit `1`;
  - write permission failure: JSON error, exit `1`.

## Determinism

The report must be deterministic:

- no timestamps;
- no random IDs;
- no environment-specific absolute paths unless explicitly supplied by CLI output metadata;
- stable ordering inherited from Paper Map;
- stable warning order.

## Testing

Add focused tests for:

- Workspace report payload includes schema version, format, paper ID, summary, sections, Markdown, and warnings.
- Markdown includes all required headings.
- Markdown includes main-result candidates and their explicit reasons.
- Markdown includes recommended reading route items.
- Markdown includes external import candidate review summaries.
- Markdown includes evidence boundaries.
- Sparse/empty papers still export a report.
- MCP wrapper returns the payload and converts errors.
- CLI without `--output` prints Markdown.
- CLI with `--output` writes Markdown and prints JSON metadata.
- CLI reports invalid output paths.
- README/repository tests include `workspace_export_paper_reading_report`, `export-paper-reading-report`, and `v0.11.0`.

Run before handoff:

```powershell
uv run pytest -q -p no:cacheprovider
```

## Documentation

README updates should:

- describe Reading Report Export as the way to save and share PaperGraph's evidence-backed reading route;
- add `workspace_export_paper_reading_report` to the tool reference;
- add CLI examples with and without `--output`;
- update release highlights for `v0.11.0`;
- preserve evidence-boundary language.

## Release

Release as `v0.11.0`.

Release notes should emphasize:

- Markdown Reading Report export;
- persistent reading artifacts;
- main-result candidates, reading route, external risks, and evidence warnings in one file;
- no proof verification, semantic theorem matching, or hidden dependency inference.

## v1.0 Implications

Reading Report Export is a v1.0 milestone because it turns PaperGraph from an interactive tool surface into a reusable research artifact generator.

After v0.11, the remaining v1.0 blockers are likely:

1. Cross-paper reading plans for a small set of related papers.
2. More explicit evidence-quality statuses across reports and maps.
3. A stable CLI/MCP contract with documented examples and migration expectations.
4. A final release candidate pass on documentation, installation, and local walkthroughs.

Notation/definition indexing should remain post-v1.0 unless a later design can keep it strictly evidence-scoped.
