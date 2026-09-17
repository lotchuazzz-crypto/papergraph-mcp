# First PaperGraph Workspace

This walkthrough shows the shortest v1 path from a fresh PaperGraph setup to durable reading artifacts.

## MCP-Capable Agent Path

Give your agent this setup request:

```text
I use an MCP-capable agent/client. Clone https://github.com/lotchuazzz-crypto/papergraph-mcp and help me configure PaperGraph for it. After cloning, read .agents/skills/setting-up-papergraph/SKILL.md and follow it.
```

After configuration, ask the agent to call `get_environment_diagnostics` or run:

```powershell
papergraph-mcp doctor
```

## CLI-Only Path

If you do not use an MCP-capable client yet, run PaperGraph from the CLI:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.3 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.3 papergraph-mcp doctor
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

## First Paper

For raw user requests, Markdown links, URLs, or prose, prefer `load_arxiv_request` or validate first with `validate_arxiv_request`.

With MCP, load a known arXiv paper after validation:

```text
workspace_add_arxiv_paper(arxiv_id="2401.12345")
```

With CLI, use the validated request path:

```powershell
papergraph-mcp load-arxiv-request "2401.12345"
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
papergraph-mcp plan-starter-project `
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
papergraph-mcp bootstrap-reading-project `
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
papergraph-mcp get-paper-map --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345
```

Read `evidence_status`, warnings, main-result candidates, reading route, and external risks before choosing a target theorem. If a later Reading Report includes Evidence Triage, use it as the higher-level summary of sparse evidence, candidate starts, blockers, and next actions.

## Single-Paper Reading Report

Export a durable one-paper report:

```text
workspace_export_paper_reading_report(paper_id="arxiv:2401.12345")
```

or:

```powershell
papergraph-mcp export-paper-reading-report --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345 --output reading-report.md
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
papergraph-mcp search-external-reference `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a `
  --blocked-id external-import:blocked:...

papergraph-mcp list-external-reference-searches `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a
```

Review the candidate confidence, provider evidence, DOI, arXiv ID, URLs, and warnings. A candidate is not a final identity claim. Strong candidates can usually be applied directly through Reference Import Closure; ambiguous, weak, or metadata-only candidates should be reported as boundaries unless the user supplies a source or explicitly chooses one.

To apply a selected candidate in MCP:

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
papergraph-mcp resolve-external-reference-candidate `
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
papergraph-mcp resolve-external-reference `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id local:paper-a `
  --blocked-id external-import:blocked:... `
  --doi 10.1000/example `
  --title "Published target"

papergraph-mcp list-external-reference-resolutions `
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
papergraph-mcp export-cross-paper-reading-plan `
  --workspace $env:PAPERGRAPH_WORKSPACE `
  --paper-id arxiv:2401.12345 `
  --paper-id arxiv:2401.12346 `
  --focus "fixed point" `
  --output cross-paper-plan.md
```

Treat selected-paper citation evidence as evidence to inspect, not proof of logical dependency.

## Next Steps

Use reading queues and sessions when you want to track a longer reading process:

```text
workspace_create_reading_queue(result_id=<target result id>)
workspace_create_reading_session(paper_id=<paper id>)
```

PaperGraph does not verify proofs, infer hidden prerequisites, perform semantic theorem matching, bypass paywalls, or recursively import newly discovered literature. v1.1.3 can search scholarly metadata for blocked references, but it only imports or records a target when a candidate is explicitly applied.
