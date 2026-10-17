# First PaperGraph Workspace

This walkthrough shows the shortest v1 path from a fresh PaperGraph setup to durable reading artifacts.

## MCP-Capable Agent Path

Give your agent this setup request:

```text
I use an MCP-capable agent/client. Clone https://github.com/lotchuazzz-crypto/papergraph-mcp and help me configure PaperGraph for it. After cloning, read .agents/skills/setting-up-papergraph/SKILL.md and follow it.
```

After configuration, ask the agent to call `get_environment_diagnostics` or run:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp doctor
```

## CLI-Only Path

If you do not use an MCP-capable client yet, run PaperGraph from the CLI:

[PyPI 1.2.2 is published](../reference/v1.2.2-publication.md), with verified
public bytes and Git-free first-use acceptance. GitHub Release assets match
the same approved bytes. The default route needs uv/uvx and index access,
without Git or a checkout:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp --version
uvx --from papergraph-mcp==1.2.2 papergraph-mcp doctor
```

Every CLI example below repeats the full version-pinned launcher: `uvx` does
not install `papergraph-mcp` onto your shell PATH. The first invocation may
download the package and populate the uv cache. Generated artifacts and
[example exports](../examples/reading-report-example.md) use the shorter
`papergraph-mcp` command; prepend `uvx --from papergraph-mcp==1.2.2` to run
those commands with this route.

Optional Git source requires Git and a live check of the exact release tag
against source R in the [artifact record](../reference/v1.2.2-artifact-verification.md),
following the [setup skill](../../.agents/skills/setting-up-papergraph/SKILL.md):

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.2 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.2 papergraph-mcp doctor
```

## Workspace Hygiene

Keep workspace databases outside the Git repository. Use a temporary or project-adjacent data directory, for example:

```powershell
$env:PAPERGRAPH_WORKSPACE = "$env:TEMP\papergraph-workspace.sqlite3"
```

In MCP, first open the workspace:

```text
open_workspace(path=<workspace path outside the Git repository>)
```

## Local Three-Paper Walkthrough

This optional offline demo uses the small public synthetic fixtures in a
repository checkout. Set `$PaperGraphCheckout` to that checkout; all data and
exports go to a unique temporary directory outside the Git repository. No
arXiv or external-reference downloads are needed. The default package launch
above still works without these optional fixtures.

Run this PowerShell sequence after reviewing the paths. Planning validates each
main `.tex` file without creating the workspace, directories or artifacts;
`ready` means file preflight passed, not that parsing/import succeeded.
Bootstrap then imports the three papers and writes the artifacts.

```powershell
$PaperGraphCheckout = 'C:\path\to\papergraph-mcp'
$demo = Join-Path ([IO.Path]::GetTempPath()) ('papergraph-demo-' + [guid]::NewGuid())
$env:PAPERGRAPH_WORKSPACE = Join-Path $demo 'papergraph.sqlite3'
$artifacts = Join-Path $demo 'starter'
$a = Join-Path $PaperGraphCheckout 'tests/fixtures/workspace/paper_a/main.tex'
$b = Join-Path $PaperGraphCheckout 'tests/fixtures/workspace/paper_b/main.tex'
$c = Join-Path $PaperGraphCheckout 'tests/fixtures/workspace/paper_c/main.tex'
$plan = uvx --from papergraph-mcp==1.2.2 papergraph-mcp plan-starter-project --workspace $env:PAPERGRAPH_WORKSPACE --artifact-dir $artifacts --tex "${a}=local:paper-a" --tex "${b}=local:paper-b" --tex "${c}=local:paper-c" --no-queue --no-session | ConvertFrom-Json
$plan
```

Inspect the plan before continuing. With these unchanged fixtures it is ready:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp bootstrap-reading-project --workspace $env:PAPERGRAPH_WORKSPACE --artifact-dir $artifacts --tex "${a}=local:paper-a" --tex "${b}=local:paper-b" --tex "${c}=local:paper-c" --no-queue --no-session
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-paper-map --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-reading-bundle --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-result-reading-context --workspace $env:PAPERGRAPH_WORKSPACE --result-id local:paper-a::thm:main
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-source-slice --workspace $env:PAPERGRAPH_WORKSPACE --result-id local:paper-a::thm:main
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-result-reading-path --workspace $env:PAPERGRAPH_WORKSPACE --result-id local:paper-a::thm:main
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-dependency-reading $env:PAPERGRAPH_WORKSPACE local:paper-a --target-result-id local:paper-a::thm:main --detail compact
$session = uvx --from papergraph-mcp==1.2.2 papergraph-mcp create-reading-session --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a | ConvertFrom-Json
$queue = uvx --from papergraph-mcp==1.2.2 papergraph-mcp create-reading-queue --workspace $env:PAPERGRAPH_WORKSPACE --result-id local:paper-a::thm:main | ConvertFrom-Json
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-reading-queue --workspace $env:PAPERGRAPH_WORKSPACE --queue-id $queue.queue_id
uvx --from papergraph-mcp==1.2.2 papergraph-mcp apply-reading-queue-to-session --workspace $env:PAPERGRAPH_WORKSPACE --queue-id $queue.queue_id --session-id $session.session_id
uvx --from papergraph-mcp==1.2.2 papergraph-mcp record-reading-checkpoint --workspace $env:PAPERGRAPH_WORKSPACE --session-id $session.session_id --target-kind result_id --target-id local:paper-a::thm:main --status reviewed
uvx --from papergraph-mcp==1.2.2 papergraph-mcp add-reading-note --workspace $env:PAPERGRAPH_WORKSPACE --session-id $session.session_id --text 'Check the cited fixed point theorem.'
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-reading-session-summary --workspace $env:PAPERGRAPH_WORKSPACE --session-id $session.session_id
uvx --from papergraph-mcp==1.2.2 papergraph-mcp plan-external-imports-for-paper --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-paper-reading-report --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a --output (Join-Path $demo 'reading-report.md')
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-cross-paper-reading-plan --workspace $env:PAPERGRAPH_WORKSPACE --paper-id local:paper-a --paper-id local:paper-b --paper-id local:paper-c --output (Join-Path $demo 'cross-paper-plan.md')
```

Open `START_HERE.md` under `$artifacts` and read Evidence Triage first. With MCP,
the same imported fixtures support these checks:

- `workspace_list_papers()` lists `local:paper-a`, `local:paper-b`, and `local:paper-c`.
- `workspace_search_theorems("fixed point", limit=10)` returns `local:paper-a::thm:main`, `local:paper-b::thm:main`, and `local:paper-c::thm:main`.
- `workspace_get_citations("local:paper-a", direction="outgoing", include_unresolved=True)` reports keys `absent`, `missing`, and `paper-b`.
- The `paper-b` citation has cited arXiv ID `2401.12346`, but it does not resolve to `local:paper-b`; the row retains `target_paper_id: null`.
- Only when the cited arXiv ID is imported with `workspace_add_arxiv_paper` can it resolve to that imported target. A similar bibliography entry is insufficient: resolution uses explicit cited arXiv identity, not semantic matching. Do not download the synthetic IDs in this demo.

`workspace_list_results` is paginated: `limit` is 1..100 (default 50), and
`offset` is nonnegative (default 0). Advance by the returned count until a page
contains fewer than `limit` rows, keeping the workspace stable between calls.
Generated PowerShell commands quote paths as single-quoted literals (doubling
embedded apostrophes); POSIX commands use POSIX quoting.

## First Paper

For raw user requests, Markdown links, URLs, or prose, prefer `load_arxiv_request` or validate first with `validate_arxiv_request`.

With MCP, load a known arXiv paper after validation:

```text
workspace_add_arxiv_paper(arxiv_id="2401.12345")
```

For your own chosen arXiv paper, use the validated CLI request path (replace
the illustrative ID). This standalone load does not add a paper to the durable
workspace; use starter inputs `--arxiv ID` or `workspace_add_arxiv_paper` for that:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp load-arxiv-request "2401.12345"
```

## Workspace Starter

For a first real project, preview the starter plan before writing artifacts:

```text
workspace_plan_starter_project(
  workspace_path=<workspace path outside the Git repository>,
  artifact_dir=<starter artifact directory>,
  papers=[{"kind": "pdf", "path": "paper-a.pdf", "paper_id": "local:paper-a"}],
  create_queue=false,
  create_session=false
)
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp plan-starter-project `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --artifact-dir .\papergraph-starter `
  --pdf .\paper-a.pdf=local:paper-a `
  --no-queue `
  --no-session
```

When the plan looks right, bootstrap the reading project:

```text
workspace_bootstrap_reading_project(
  workspace_path=<workspace path outside the Git repository>,
  artifact_dir=<starter artifact directory>,
  papers=[{"kind": "pdf", "path": "paper-a.pdf", "paper_id": "local:paper-a"}],
  create_queue=false,
  create_session=false
)
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp bootstrap-reading-project `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --artifact-dir .\papergraph-starter `
  --pdf .\paper-a.pdf=local:paper-a `
  --no-queue `
  --no-session
```

The starter writes `START_HERE.md`, `papergraph-starter-manifest.json`, per-paper Reading Reports, and a Cross-Paper Reading Plan when two or more papers are loaded. Start with the Evidence Triage entry in `START_HERE.md` before treating any route or dependency output as a reading order.

## Paper Map

Start with Paper Map:

```text
workspace_get_paper_map(paper_id="arxiv:2401.12345")
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp get-paper-map --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345
```

Read `evidence_status`, warnings, main-result candidates, reading route, and external risks before choosing a target theorem. If a later Reading Report includes Evidence Triage, use it as the higher-level summary of sparse evidence, candidate starts, blockers, and next actions.

## Single-Paper Reading Report

Export a durable one-paper report:

```text
workspace_export_paper_reading_report(paper_id="arxiv:2401.12345")
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-paper-reading-report --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345 --output reading-report.md
```

Open the report's `Evidence Triage` section first. It tells you whether extracted dependencies are sparse, whether proofs are missing or fragmentary, whether external references block interpretation, and what manual checks should happen next. A candidate starting point is only a supported extracted route candidate, not a claim that the paper's main theorem has been identified.

## Scholarly Reference Resolver

When Evidence Triage reports a blocked external reference, first inspect the planner output:

```text
workspace_plan_external_imports_for_paper(paper_id="local:paper-a")
```

Then search for candidates for the specific `blocked_id`. Search is a low-risk metadata lookup and can be run without asking the user to confirm every query:

```text
workspace_search_external_reference(
  paper_id="local:paper-a",
  blocked_id="external-import:blocked:..."
)
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp search-external-reference `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a `
  --blocked-id external-import:blocked:...

uvx --from papergraph-mcp==1.2.2 papergraph-mcp list-external-reference-searches `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a
```

Review the candidate confidence, provider evidence, DOI, arXiv ID, URLs, and warnings. A candidate is not a final identity claim. Apply a selected candidate through Reference Import Closure only after reviewing and approving its import; ambiguous, weak, or metadata-only candidates should be reported as boundaries unless the user supplies a source or explicitly chooses one.

After explicit approval to import the selected external target, apply it in MCP:

```text
workspace_resolve_external_reference_candidate(
  paper_id="local:paper-a",
  blocked_id="external-import:blocked:...",
  candidate_id="candidate:...",
  import_target=true
)
```

For CLI:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp resolve-external-reference-candidate `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a `
  --blocked-id external-import:blocked:... `
  --candidate-id candidate:... `
  --import-target
```

If you already know the exact target, you can still resolve the `blocked_id` manually. In MCP:

```text
workspace_resolve_external_reference(
  paper_id="local:paper-a",
  blocked_id="external-import:blocked:...",
  target={"kind": "doi", "doi": "10.1000/example", "title": "Published target"}
)
```

For CLI:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp resolve-external-reference `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a `
  --blocked-id external-import:blocked:... `
  --doi 10.1000/example `
  --title "Published target"

uvx --from papergraph-mcp==1.2.2 papergraph-mcp list-external-reference-resolutions `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a
```

Use `--pdf .\reference.pdf=local:reference` or an arXiv target when you have an importable source. DOI, URL, and published metadata are recorded as resolved but not imported until a local source is supplied.

Some trails stop even after search. For example, A may cite B, B may cite C, and C may cite an older D that has no DOI, no arXiv record, no stable URL, and no accessible PDF. In that case PaperGraph records the metadata boundary and tells the reader what is missing instead of pretending it can continue.

## Cross-Paper Reading Plan

After two or more related papers are loaded, export a cross-paper plan:

```text
workspace_export_cross_paper_reading_plan(
  paper_ids=["arxiv:2401.12345", "arxiv:2401.12346"],
  focus="fixed point"
)
```

or:

```powershell
uvx --from papergraph-mcp==1.2.2 papergraph-mcp export-cross-paper-reading-plan `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id arxiv:2401.12345 `
  --paper-id arxiv:2401.12346 `
  --focus "fixed point" `
  --output cross-paper-plan.md
```

Treat selected-paper citation evidence as evidence to inspect, not proof of logical dependency.

## Next Steps

Back up existing workspaces before upgrading to schema 9; older versions cannot
open the upgraded file. Search defaults to `deterministic_v2` and stores parsing
evidence, matching reasons, source availability and next actions. Use
`--resolver-version legacy_v1` only when explicitly requesting old matching.
New expansion tasks use `unique_strong_v2`; existing v1 tasks remain v1. Reports
read saved assessments without network access. Provider failures are not evidence
of nonexistence, and missing sources do not establish a paywall.

Use reading queues and sessions when you want to track a longer reading process:

```text
workspace_create_reading_queue(result_id=<target result id>)
workspace_create_reading_session(paper_id=<paper id>)
```

PaperGraph does not verify proofs, infer hidden prerequisites, perform semantic theorem matching, bypass paywalls, or perform unlimited crawling. The standalone scholarly resolver only imports or records a target when a candidate is explicitly applied. v1.1.5 additionally offers [bounded reference expansion](bounded-reference-expansion.md): an explicitly approved finite policy permits unique strong imports, with ambiguous branches waiting for review. The commands target published v1.2.2; immutable source R, tag and published package files retain their historical build-time guidance. Use `uv run papergraph-mcp` only when deliberately testing a checkout in its locked development environment.


## Inspecting Evidence and Limits

For a born-digital PDF, import with `workspace_add_pdf_paper` or the starter's
`--pdf` input. Inspect `workspace_get_result`, `workspace_get_result_proof`,
`workspace_get_proof_dependencies`, and `workspace_get_source_slice` before
interpreting known, inferred, or unresolved references. Scanned PDFs and OCR-heavy
files may yield sparse evidence. Complex LaTeX projects may need `main_file`.
The [core contract](../reference/v1-core-contract.md) defines stable tools and
output statuses; the [release notes](../reference/v1.2.2-release-notes.md) describe
version-specific behavior.

PDF `text_coverage.status: unverified`, `statement_complete: false`, and
`proof_complete: false` report unverified completeness, not necessarily truncation.
Use `text_coverage.continuation_source` and `workspace_read_source_blocks` with
its `next` handle for bounded raw reading. New automatic PDF proof evidence is
limited to the first physical line carrying an explicit proof heading. It does
not automatically join later lines or blocks. An unnamed heading needs a directly
preceding result; ambiguous, compound or unsupported headings leave ownership
unknown. Heading goals are not proof-body references. The
`automatic_ownership_policy` identifies the extraction policy; stored excerpts
retain their original policy until explicit reimport. Late references remain
unknown even when raw continuation is readable. Raw context is not additional
dependency evidence, and PaperGraph does not verify proofs.

The legacy statement graph uses `statement_explicit_latex_refs_only`; empty
edges do not establish mathematical independence. TeX proof environments and
supported proof-adjacent spans provide separately scoped evidence. `raw_kind`,
`display_kind` and `normalized_kind` distinguish extraction from display/grouping.
Unknown prerequisites, cycles and external blockers remain visible rather than
being silently promoted into a complete reading order.

arXiv source archives are bounded to 100 MiB compressed, 500 MiB expanded and
10,000 members; unsafe paths and special files are rejected. Discovered public
HTTPS PDF candidates have public-address/redirect checks, pin the validated
connection address and are bounded to 50 MiB, 8 seconds per socket operation
and a 60-second elapsed budget (synchronous DNS cannot be interrupted by it).
External-reference discovery does not download full text. A reviewed root import
does not authorize recursive external downloads or bypass paywalls.
