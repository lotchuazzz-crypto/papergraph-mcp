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
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.0.0 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.0.0 papergraph-mcp doctor
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

The starter writes `START_HERE.md`, `papergraph-starter-manifest.json`, per-paper Reading Reports, and a Cross-Paper Reading Plan when two or more papers are loaded.

## Paper Map

Start with Paper Map:

```text
workspace_get_paper_map(paper_id="arxiv:2401.12345")
```

or:

```powershell
papergraph-mcp get-paper-map --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345
```

Read `evidence_status`, warnings, main-result candidates, reading route, and external risks before choosing a target theorem.

## Single-Paper Reading Report

Export a durable one-paper report:

```text
workspace_export_paper_reading_report(paper_id="arxiv:2401.12345")
```

or:

```powershell
papergraph-mcp export-paper-reading-report --workspace $env:PAPERGRAPH_WORKSPACE --paper-id arxiv:2401.12345 --output reading-report.md
```

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

PaperGraph does not verify proofs, infer hidden prerequisites, or perform semantic theorem matching.
