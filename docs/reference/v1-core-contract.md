# PaperGraph v1 Core Contract

This document describes the stable v1 surface for PaperGraph's core reading workflow. It is a user and agent contract, not a promise that every internal evidence field is frozen forever.

## Stable Core Workflow

The v1 workflow is:

1. Open or create a workspace outside the Git repository.
2. Add arXiv, local LaTeX, or born-digital PDF papers.
3. Start each paper with Paper Map.
4. Inspect proof evidence, citations, source slices, and external import plans.
5. Export a Reading Report for a single paper.
6. Export a Cross-Paper Reading Plan for a small explicit set of related papers.

v1.1 adds a Workspace Starter layer that composes this workflow: it plans or bootstraps a first reading project from explicit paper inputs and writes starter artifacts without changing extraction semantics.

v1.1.1 adds Evidence Triage to Reading Reports and Workspace Starter artifacts. Triage summarizes extraction status, supported local chains, candidate starts, external blockers, and next actions before a reader interprets dependency output.

v1.1.2 adds Reference Import Closure: a blocked external reference can be resolved to a user-confirmed arXiv ID, local PDF, DOI, URL, or published metadata target. arXiv and local PDF targets can be imported; DOI, URL, and metadata targets are recorded as resolved but not imported until the user supplies a local source.

## Stable MCP Tools

These MCP tools form the v1 core:

- `open_workspace`
- `workspace_add_local_paper`
- `workspace_add_arxiv_paper`
- `workspace_add_pdf_paper`
- `workspace_list_papers`
- `workspace_get_paper`
- `workspace_plan_starter_project`
- `workspace_bootstrap_reading_project`
- `workspace_get_paper_map`
- `workspace_export_paper_reading_report`
- `workspace_export_cross_paper_reading_plan`
- `workspace_get_result`
- `workspace_get_result_proof`
- `workspace_get_proof_dependencies`
- `workspace_get_source_slice`
- `workspace_get_result_reading_path`
- `workspace_plan_external_imports_for_paper`
- `workspace_plan_external_imports_for_result`
- `workspace_plan_external_imports_for_queue`
- `workspace_resolve_external_reference`
- `workspace_list_external_reference_resolutions`
- `workspace_create_reading_queue`
- `workspace_create_reading_session`

Additional tools may expose lower-level evidence, diagnostics, or legacy single-paper behavior. The tools above are the recommended v1 path.

## Stable CLI Commands

The v1 CLI mirrors the same workflow:

- `papergraph-mcp doctor`
- `papergraph-mcp validate-arxiv-request`
- `papergraph-mcp load-arxiv-request`
- `papergraph-mcp plan-starter-project`
- `papergraph-mcp bootstrap-reading-project`
- `papergraph-mcp get-paper-map`
- `papergraph-mcp export-paper-reading-report`
- `papergraph-mcp export-cross-paper-reading-plan`
- `papergraph-mcp plan-external-imports-for-paper`
- `papergraph-mcp resolve-external-reference`
- `papergraph-mcp list-external-reference-resolutions`
- `papergraph-mcp create-reading-queue`
- `papergraph-mcp create-reading-session`

CLI commands that write Markdown use `--output` for files and print Markdown to stdout when no output path is supplied.

## Evidence Status

PaperGraph uses three evidence-status values:

- `usable`: enough extracted evidence exists to guide reading. This does not mean the paper is mathematically verified.
- `sparse`: some evidence exists, but proof, citation, source-span, or route evidence is thin.
- `limited`: extraction found little or no usable theorem-like or proof evidence.

These statuses describe extraction quality, not mathematical truth.

## Warning Records

Warning records use this stable shape:

```json
{
  "kind": "external_dependencies",
  "message": "External import candidates are visible from stored evidence.",
  "evidence": {
    "import_candidate_count": 1
  }
}
```

Stable keys:

- `kind`: machine-readable warning kind.
- `message`: short human-readable explanation.
- `evidence`: structured counts, IDs, or source references supporting the warning.

Consumers should ignore unknown warning kinds gracefully.

## Evidence Triage

Evidence Triage is a stable reader-facing summary layer. It may be present in Reading Report JSON, rendered Reading Reports, Starter Summary, and Starter Manifest artifacts.

Stable triage fields:

- `status`: one of `external_blocked`, `proofs_missing_or_fragmentary`, `sparse_dependencies`, `usable_with_cautions`, or `needs_manual_review`.
- `counts`: extracted result, theorem-like result, proof, dependency, and external-blocker counts.
- `supported_local_chains`: local dependency chains that are supported by extracted proof evidence.
- `candidate_starting_point`: the best available extracted route candidate, if any. This is not a claim that the result is mathematically central.
- `extraction_limits`: plain-language caveats about missing proofs, fragments, sparse dependencies, and extraction boundaries.
- `external_blockers`: references that appear relevant but cannot yet be imported automatically.
- `next_actions`: concrete review steps for the reader.

Evidence Triage describes the state of available evidence, not the state of the mathematics. Empty dependencies mean no supported extraction evidence was found, not that no mathematical dependencies exist.

## Reference Import Closure

Reference Import Closure records user-confirmed identities for blocked external references.

Stable resolution statuses:

- `resolved_imported`: the user supplied an importable arXiv ID or local PDF and PaperGraph imported it.
- `resolved_not_imported`: the user supplied DOI, URL, or published metadata, but no local source is available for PaperGraph analysis yet.
- `failed_import`: the user supplied an importable target, but import failed and the failure is preserved.

Reference resolutions supplement extraction evidence. They do not rewrite original citation, bibliography, or proof evidence.

## CLI Error Payloads

Workspace CLI failures use this shape:

```json
{
  "status": "error",
  "action": "inspect_error",
  "command": "export-cross-paper-reading-plan",
  "message": "Unknown paper id: local:missing"
}
```

Stable keys:

- `status`
- `action`
- `command`
- `message`

## Durable Markdown Artifacts

PaperGraph v1 has two durable Markdown artifacts and v1.1 starter artifacts:

- Reading Report: one paper, one saved evidence-backed reading route.
- Cross-Paper Reading Plan: a small explicit paper set, selected-paper citation evidence, recommended sequence, external risks, and boundaries.
- Starter Summary: `START_HERE.md`, a first-project index of loaded papers, generated artifacts, warnings, and next commands.
- Starter Manifest: `papergraph-starter-manifest.json`, a deterministic machine-readable handoff with artifact paths and exact follow-up commands.

Markdown artifacts must avoid timestamps, random IDs, and environment-specific absolute paths unless the user explicitly supplies them at the CLI layer.

## Evidence Boundaries

PaperGraph does not verify proofs.

PaperGraph does not infer hidden mathematical prerequisites.

PaperGraph does not perform semantic theorem matching.

PaperGraph does not search the web to identify ambiguous references or recursively import newly discovered literature in v1.1.2.

Citation evidence does not imply logical dependency unless supported by reading-path evidence.

Empty dependencies or empty cross-paper edges mean no supported extraction evidence was found, not that no mathematical relationship exists.

## Post-v1 Scope

These features are intentionally outside the v1 core contract:

- global paper discovery;
- semantic theorem equivalence;
- notation or symbol indexing;
- PDF rendering of reports;
- online reference search and recursive external-paper import;
- proof checking.
