# External Import Planner v0.9 Design

## Goal

PaperGraph v0.9 adds an evidence-first External Import Planner. Given a result, reading queue, or whole paper, PaperGraph will collect external and unresolved reading stops, group them into deterministic import candidates, and report which arXiv papers should be imported next, which references are already locally covered, and which stops remain non-actionable.

The planner does not download papers, resolve theorem equivalence, or verify proofs. It produces a reviewable import plan that a reading agent can inspect before calling existing import tools.

## Context

PaperGraph v0.8 can build reading queues from local proof-dependency paths. Queue items classify the selected result and proof as `required`, local dependencies as `recommended`, and external or unresolved stops as `caution`.

The next gap is that a `caution` item often points to a bibliography-backed external theorem mention such as `[12, Theorem 3.5]`. The workspace already stores citation mentions, bibliography entries, arXiv identifiers, external result mentions, and source spans. v0.9 should turn that evidence into an ordered next-import plan without inventing missing metadata.

## Users

- A paper-reading agent that wants to continue after a reading path reaches external stops.
- A human or agent maintaining a local workspace and deciding which cited papers to import next.
- A CI or terminal workflow that wants a JSON report before mutating the workspace.

## Scope

### In Scope

- Generate import plans from:
  - `result_id`
  - `queue_id`
  - `paper_id`
- Include only evidence already stored in the workspace.
- Group actionable external mentions and citation evidence by normalized arXiv paper ID.
- Mark candidates already present in the workspace as `already_imported`.
- Mark candidates with arXiv IDs not yet imported as `import_candidate`.
- Preserve non-actionable evidence as `blocked` items when no arXiv ID is known.
- Include source evidence:
  - external result mention IDs
  - citation mention IDs
  - bibliography entry IDs
  - raw text / citation key / result context where available
- Expose MCP tools and CLI commands for create/list/get/apply-style read-only planning.
- Update README, diagnostics/release pins, and onboarding pins for v0.9.0.

### Out of Scope

- Automatically importing arXiv papers.
- Calling the live arXiv API while planning.
- DOI, Crossref, Semantic Scholar, or web search resolution.
- Theorem-level matching between a local result and an external theorem mention.
- Persistent schema changes. Plans can be recomputed deterministically from stored evidence.
- Removing or deprecating existing CLI commands.

## Public API

### Workspace Python API

Add these methods to `Workspace`:

```python
def plan_external_imports_for_result(
    self,
    result_id: str,
    recursive: bool = True,
) -> dict: ...

def plan_external_imports_for_queue(
    self,
    queue_id: str,
) -> dict: ...

def plan_external_imports_for_paper(
    self,
    paper_id: str,
) -> dict: ...
```

All three return the same payload shape:

```python
{
    "plan_schema_version": 1,
    "scope": {
        "kind": "result_id" | "queue_id" | "paper_id",
        "value": "...",
        "paper_id": "...",
        "recursive": True | False | None,
    },
    "candidates": [
        {
            "candidate_id": "external-import:arxiv:2401.12345",
            "status": "import_candidate" | "already_imported",
            "source": {
                "type": "arxiv",
                "arxiv_id": "2401.12345",
                "arxiv_version": "v2" | None,
                "recommended_paper_id": "arxiv:2401.12345",
            },
            "evidence": [...],
            "counts": {
                "external_mentions": 1,
                "citation_mentions": 1,
                "bibliography_entries": 1,
            },
        },
    ],
    "blocked": [
        {
            "blocked_id": "external-import:blocked:<stable-slug>",
            "reason": "missing_arxiv_id",
            "evidence": [...],
        },
    ],
    "summary": {
        "candidate_count": 1,
        "import_candidate_count": 1,
        "already_imported_count": 0,
        "blocked_count": 1,
    },
    "warnings": [],
}
```

### MCP Tools

Add:

- `workspace_plan_external_imports_for_result(result_id: str, recursive: bool = True) -> dict`
- `workspace_plan_external_imports_for_queue(queue_id: str) -> dict`
- `workspace_plan_external_imports_for_paper(paper_id: str) -> dict`

These tools require an active workspace. They convert workspace validation errors into MCP `ToolError`, following existing workspace tool patterns.

### CLI Commands

Add JSON-only commands:

```powershell
papergraph-mcp plan-external-imports-for-result --workspace C:/Temp/papergraph.sqlite3 --result-id local:paper::pdf:theorem:1.1
papergraph-mcp plan-external-imports-for-result --workspace C:/Temp/papergraph.sqlite3 --result-id local:paper::pdf:theorem:1.1 --direct
papergraph-mcp plan-external-imports-for-queue --workspace C:/Temp/papergraph.sqlite3 --queue-id queue:...
papergraph-mcp plan-external-imports-for-paper --workspace C:/Temp/papergraph.sqlite3 --paper-id local:paper
```

`--direct` means `recursive=False`, matching the existing reading path and reading queue conventions.

## Evidence Model

### Candidate Evidence Records

Every evidence record has a deterministic shape:

```python
{
    "kind": "external_result_mention" | "citation_mention" | "bibliography_entry",
    "id": "...",
    "paper_id": "...",
    "result_id": "..." | None,
    "proof_id": "..." | None,
    "citation_key": "..." | None,
    "raw_text": "..." | None,
    "source": "reading_path.external_stops" | "reading_queue.external_stop" | "paper.citation_evidence",
}
```

When an external result mention references a citation mention or bibliography entry, the planner follows those stored IDs to gather arXiv metadata. If no arXiv ID exists, the original mention remains in `blocked`.

### Candidate Grouping

The planner groups by normalized arXiv ID only. Different versions of the same arXiv ID become one candidate. If multiple versions appear, the candidate records:

- `arxiv_version`: the highest evidence version by stable string order when present, otherwise `None`.
- `evidence`: all contributing evidence records in deterministic order.
- `warnings`: include `conflicting_versions` only when two or more distinct non-null versions appear.

The recommended paper ID is always `arxiv:<arxiv_id>`.

### Already Imported

A candidate is `already_imported` when a workspace paper exists with `paper_id == "arxiv:<arxiv_id>"`. It remains in the candidate list because it is still useful evidence, but its status prevents agents from importing it again.

### Blocked Items

Blocked items preserve stops without an arXiv ID:

- bibliography entry with DOI or URL but no arXiv ID
- citation mention with missing bibliography entry
- external result mention without traceable bibliography metadata
- unresolved reading path stop such as unresolved local theorem references

Blocked items should carry enough evidence for a reading agent to ask a human, search manually, or decide that the stop is not importable.

## Data Flow

### Result Scope

1. Validate `result_id`.
2. Compute `get_result_reading_path(result_id, recursive=recursive)`.
3. Collect `external_stops`.
4. Collect `unresolved_stops` into blocked items.
5. For each local result in `top_down`, inspect proof dependencies to gather citation and external mention evidence.
6. Resolve evidence into arXiv candidates or blocked items.

### Queue Scope

1. Validate `queue_id`.
2. Read queue items.
3. For `external_stop` items, resolve the referenced external mention.
4. For `unresolved_stop` items, carry item evidence into blocked items.
5. For `result_id` items, inspect that result's direct proof dependencies so queue plans remain bounded by queue contents rather than recursively expanding beyond the saved queue.

### Paper Scope

1. Validate `paper_id`.
2. Inspect all stored citation evidence rows for the paper.
3. Inspect all external result mentions for the paper.
4. Resolve evidence into candidates or blocked items.
5. Paper scope does not compute recursive reading paths.

## Determinism

Output order is stable:

1. candidates sorted by status (`import_candidate` before `already_imported`), arXiv ID, then candidate ID
2. evidence within candidates sorted by kind, ID
3. blocked items sorted by reason, blocked ID

Generated IDs use only stored IDs and normalized strings, never timestamps.

## Error Handling

- Unknown `result_id`, `queue_id`, or `paper_id` raises `KeyError`.
- Invalid `recursive` type raises `ValueError`.
- Plans with no candidates and no blocked items return an empty plan with zero counts.
- MCP wrappers convert `KeyError`, `ValueError`, and workspace errors into `ToolError`.
- CLI commands print one JSON payload on success and write one error message to stderr with exit code 1 on failure.

## Tests

Add focused tests for:

- Result plan groups bibliography-backed external mentions into arXiv candidates.
- Result plan includes unresolved reading stops as blocked items.
- Already-imported arXiv papers change candidate status to `already_imported`.
- Queue plan uses stored queue caution items and does not recursively expand beyond queue result items.
- Paper plan includes citation evidence even without a reading queue.
- MCP wrappers return payloads and convert workspace errors.
- CLI commands print JSON and report unknown IDs.
- README and repository tests expose v0.9.0 pins and the new tools.

## Release

Release as `v0.9.0`.

Verification before PR:

- `uv run pytest`
- PR CI on Ubuntu and Windows, Python 3.10 and 3.12
- main CI after merge
- pinned install:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.0 papergraph-mcp --version
```
