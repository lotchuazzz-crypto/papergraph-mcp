# Bounded Reference Expansion

v1.1.4 follows extracted references, not mathematical prerequisites. It does not
verify proofs, bypass paywalls, scrape arbitrary publishers, or find every
reference in a paper. The existing resolver remains manual; this separate
workflow executes automatic imports only under a saved, explicitly approved policy.

## Offline acceptance example

From the repository root, with Python 3.10+ and uv:

```powershell
uv run python scripts/reproduce_reference_expansion.py --output-dir ./expansion-demo
uv run pytest tests/test_reference_expansion.py tests/test_reference_expansion_api.py -q
```

The runner uses temporary SQLite storage, real LaTeX parsing and real expansion
APIs. Only arXiv acquisition is replaced by MIT synthetic files; unexpected
network access fails. Never download the fixture's illustrative arXiv IDs.
The generated JSON and Markdown match the checked-in
[JSON](../examples/reference-expansion-example.json) and
[tree](../examples/reference-expansion-example.md): three papers, two new imports,
five citation edges, no provider searches, a shared target and terminating cycles.
Output files are never overwritten. The tests additionally replay recorded
synthetic provider responses, ambiguous/manual and metadata-only branches,
interruptions, exact budget boundaries, migration and actual MCP stdio calls.

## Real workspace: approve, advance, review

Use `uv run papergraph-mcp` in this checkout. After v1.1.4 is published, the same
commands can be launched with
`uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.4 papergraph-mcp`.
Keep workspaces and exports outside your source checkout and back up existing
SQLite files before upgrading to schema 8. Import your own root paper first.

```powershell
uv run papergraph-mcp create-reference-expansion --workspace D:/reading/papers.sqlite3 --root-paper-id local:root --max-depth 2 --max-new-papers 10
```

Creating a run does not search or import. Save its returned `run_id`; substitute
it for `RUN_ID` below. Explicitly advancing authorizes metadata requests, arXiv
downloads, imports and resolution records within that saved policy:

```powershell
uv run papergraph-mcp advance-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID --max-steps 10 --time-budget-seconds 20
uv run papergraph-mcp get-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID
uv run papergraph-mcp list-reference-expansions --workspace D:/reading/papers.sqlite3
```

`ready` / `continuation_required: true` means call advance again. There is no
background worker. `waiting` means review `next_actions`; independent runnable
branches run before the final wait. `completed` means the extracted frontier was
exhausted within the current depth, not that the literature or proof is complete.
Depth-limited nodes and metadata boundaries remain visible in the saved report.
Time limits are checked between steps: an in-flight provider call/download can
finish after the requested time. Pause/cancel are likewise cooperative.

Automatic selection requires an exact source identifier or matching normalized
title, author and year corroborated by multiple providers. A ranking score alone
is insufficient. Conflicting versions, identities, retractions and ambiguity
require review. Metadata-only records remain boundaries. Local PDFs always
require an explicit decision. An existing paper is reused, never replaced.
LaTeX citation records without an extracted identifier may lack bibliography
text in older workspaces; supply a target when metadata search cannot identify it.

## Decisions and budgets

Use an `edge_id` from the run and a `candidate_id` from that edge's saved search,
not a later refreshed search. Decisions save intent; advance executes it.

```powershell
uv run papergraph-mcp decide-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID --edge-id EDGE_ID --decision '{"candidate_id":"CANDIDATE_ID"}'
uv run papergraph-mcp advance-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID
```

Other decision objects (exactly one key): `{"skip":true}`, `{"retry":true}`,
`{"existing_paper_id":"local:known"}`, or
`{"target":{"kind":"pdf","path":"D:/reading/source.pdf"}}`.
PowerShell versions differ in native-command JSON quoting; use the MCP object
form if your shell strips quotes. Retry is only for a retryable failure.

| Limit | Default | Allowed range |
| --- | --- | --- |
| `max_depth` | 2 | 1–10 |
| `max_new_papers` | 10 | 1–100 |
| `max_searches` | 100 | 1–1000 |
| `max_edges` | 500 | 1–10000 |

Repeated roots use their minimum depth. Usage is cumulative; revising a limit or
retrying never resets it. A limit cannot be lowered below consumed usage.
CLI limit flags use hyphens. Each advance permits 1–100 steps and 1–60 seconds.

```powershell
uv run papergraph-mcp update-reference-expansion-policy --workspace D:/reading/papers.sqlite3 --run-id RUN_ID --max-new-papers 20
uv run papergraph-mcp pause-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID
uv run papergraph-mcp advance-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID
uv run papergraph-mcp cancel-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID
```

Pause is resumable. Cancel permanently stops that run without deleting imported
papers. Only one workspace expansion holds the execution lease at a time; after
a killed process, wait up to 120 seconds for expiry. A paper committed before an
interruption is reconciled on resume without a duplicate import or budget debit.
Replaced/deleted source evidence is `stale_source`: create a new run rather than
applying an old decision. External acquisition failures remain explicit and retryable.

## Refresh artifacts after progress

After each advance or manual decision, export the saved expansion and regenerate
reading artifacts for `affected_paper_ids` using existing report APIs. Previously
exported files are not automatically updated.

```powershell
uv run papergraph-mcp export-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID --format markdown --output D:/reading/expansion.md
uv run papergraph-mcp export-reference-expansion --workspace D:/reading/papers.sqlite3 --run-id RUN_ID --format json --output D:/reading/expansion.json
uv run papergraph-mcp export-paper-reading-report --workspace D:/reading/papers.sqlite3 --paper-id local:root --output D:/reading/root-report.md
```

Expansion export refuses existing files unless `--overwrite` is supplied. Use a
new filename for each Reading Report snapshot (the older reading export can overwrite).
For cross-paper summaries call `workspace_export_cross_paper_reading_plan` with
the run's selected paper IDs. Reading Reports and Evidence Triage include saved
expansion progress, but do not label policy-selected targets as proof verification.

## MCP parity

All nine commands have matching `workspace_` tools with underscores instead of
hyphens. Pass `root_paper_ids` and `policy` objects at creation, `run_id` to
advance/read/export, `edge_id` plus `decision` to decide, and `limits` to revise.
Open the workspace with `open_workspace` first. Markdown export returns a
`markdown` field; the client owns file writes. See the
[client matrix and common prompt](../reference/client-compatibility.md).
