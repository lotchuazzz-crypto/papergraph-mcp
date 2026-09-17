# PaperGraph v1.1.3 Scholarly Reference Resolver Design

## Goal

PaperGraph v1.1.3 turns unresolved external references into ranked scholarly
identity candidates. It should help a reader move from "citation [17] is a
blocker" to "these are the most likely papers, with evidence and limits" without
pretending that search results are mathematical or bibliographic certainty.

The release builds on v1.1.2 Reference Import Closure:

1. v1.1.1 shows blocked external references in Evidence Triage.
2. v1.1.2 lets users confirm a target and records or imports it.
3. v1.1.3 searches scholarly sources, ranks candidates, and lets the user apply
   a selected candidate through the v1.1.2 resolution flow.

This is a more proactive release than v1.1.2. PaperGraph should search, rank,
cache, and report candidates without interrupting the user for every low-risk
step. It should require explicit confirmation only before a candidate becomes a
durable resolution, import, download, overwrite, or recursive expansion.

## Context

First-use reading showed that blocked references often lack arXiv IDs and cannot
be imported automatically. v1.1.2 lets a user fill the gap manually with an
arXiv ID, local PDF, DOI, URL, or published metadata. The next bottleneck is
finding those identifiers in the first place.

The important product insight is that published papers matter at least as much
as arXiv papers. A resolver that only searches arXiv would miss journal versions,
older references, books, proceedings papers, and DOI-first records.

v1.1.3 should therefore search across public scholarly metadata sources, with
published metadata as a first-class path rather than a fallback.

## Users

- A first-time user reading a PDF who sees blocked citations such as `[17]`.
- An agent that wants to resolve external blockers before building a reading
  project.
- A researcher tracing a dependency chain where paper A cites B, B cites C, and
  C cites D.
- A maintainer checking whether PaperGraph is honest about what was found, what
  was guessed, and where the literature trail stops.

## Design Principles

- **Search is allowed; final identity is not assumed.** PaperGraph may search
  and rank candidates automatically, but it must label candidates as candidates
  until applied through a resolution step.
- **Published literature is first-class.** DOI and journal/proceedings metadata
  are not secondary to arXiv.
- **Do not over-confirm low-risk work.** Searching providers, caching candidate
  results, rendering reports, and ranking candidates do not need user
  confirmation.
- **Confirm high-consequence actions.** Applying a candidate as the resolved
  reference, importing a paper, downloading a file, overwriting an existing
  resolution, or expanding a recursive queue requires explicit user intent.
- **Boundaries are part of the output.** If a chain stops because a source is
  too old, paywalled, undigitized, ambiguous, metadata-only, or unavailable,
  PaperGraph should say that plainly.
- **No scholarly laundering.** A high score is search evidence, not a proof that
  the candidate is the cited work.

## Approaches Considered

### Option 1: Crossref + OpenAlex + arXiv Resolver

Search Crossref for DOI/published metadata, OpenAlex for broad publication
metadata and open-access signals, and arXiv for preprints. Merge duplicate
candidates by DOI, arXiv ID, normalized title, and known links.

This is the recommended v1.1.3 scope. It covers published and preprint paths,
keeps provider complexity manageable, and leaves room for Semantic Scholar or
specialized math sources later.

### Option 2: Include Semantic Scholar In The First Release

Add Semantic Scholar as a fourth provider for citation graph and abstract
metadata.

This may improve ranking, but it adds another provider surface, rate-limit
behavior, and optional API-key story. It is better as a follow-up once the core
resolver model is stable.

### Option 3: Provider Framework Only

Build the abstraction and a mock provider, with minimal real search.

This is too conservative for the user problem. The next release should be useful
on real blocked references, not just prepare architecture.

## Scope

### In Scope

- Search unresolved external references using:
  - Crossref for DOI and published-work metadata;
  - OpenAlex for broad scholarly metadata, publication venue, OA location, and
    DOI/arXiv links when available;
  - arXiv for preprint identifiers and versions.
- Build a normalized `ReferenceCandidate` model.
- Rank candidates using deterministic evidence:
  - citation key and local context;
  - raw bibliography text;
  - title similarity;
  - author overlap;
  - year proximity;
  - venue/publisher hints;
  - DOI/arXiv exact matches;
  - provider agreement.
- Merge candidates across providers and preserve per-provider provenance.
- Cache search runs and candidate lists in the workspace.
- Expose search and apply flows through Python, MCP, and CLI.
- Render candidates and search limits in Evidence Triage and Reading Reports.
- Apply a chosen candidate through v1.1.2 Reference Import Closure.
- Support bounded forward tracing over newly resolved/imported papers when the
  user explicitly asks for iterative resolution.
- Explain boundary cases where the chain cannot continue.

### Out Of Scope

- Google Scholar scraping.
- Publisher PDF download by default.
- Bypassing paywalls or access controls.
- Claiming complete bibliography recovery.
- Automatic recursive literature crawling without an explicit depth or queue.
- Semantic theorem matching between cited statements and target-paper results.
- Proof verification.
- Choosing a candidate as final identity solely because it has the highest
  score.
- Resolving references that require private databases unavailable to the user.

## Core Concepts

### Search Run

A search run records an attempt to resolve one blocked external reference:

```json
{
  "search_run_id": "reference-search:...",
  "source_paper_id": "local:source",
  "blocked_id": "external-import:blocked:abc123",
  "query": {
    "citation_keys": ["17"],
    "raw_citation_texts": ["By [17, Theorem 2.1]"],
    "raw_bibliography_text": "...",
    "title_hint": null,
    "author_hints": [],
    "year_hint": null
  },
  "providers": ["crossref", "openalex", "arxiv"],
  "created_at": "..."
}
```

Search runs are evidence artifacts. They do not modify reference resolutions by
themselves.

### Reference Candidate

A reference candidate is a possible identity for the blocked citation:

```json
{
  "candidate_id": "reference-candidate:...",
  "target": {
    "kind": "doi",
    "doi": "10.1000/example",
    "title": "Published paper title",
    "authors": ["Ada Lovelace", "Emmy Noether"],
    "year": "2020",
    "venue": "Journal Name",
    "url": "https://doi.org/10.1000/example",
    "arxiv_id": null
  },
  "score": 0.91,
  "confidence": "strong",
  "evidence": [
    "title_exact_match",
    "author_overlap:2",
    "year_exact_match",
    "crossref_openalex_agree_on_doi"
  ],
  "warnings": []
}
```

Candidates may have `kind = "arxiv"`, `"doi"`, `"url"`, or `"metadata"`.
`pdf` remains a user-supplied or later download target, not a default search
result.

### Confidence Labels

Use deterministic labels:

- `strong`: exact DOI/arXiv match, or strong title/author/year agreement across
  at least two providers.
- `plausible`: one strong metadata match or multiple partial matches.
- `weak`: insufficient or conflicting metadata, useful only for manual review.
- `ambiguous`: multiple candidates are too close to choose safely.
- `unavailable`: metadata suggests a work exists but no stable electronic
  target or importable source is available.

Confidence labels are workflow labels. They are not truth claims.

### Search Boundary

A search boundary is a reason PaperGraph cannot continue a reference trail:

- `no_electronic_record_found`: likely old or undigitized work.
- `metadata_only`: title/authors/year found, but no DOI, arXiv ID, or stable URL.
- `paywalled_or_restricted`: record exists, but accessible content is limited.
- `ambiguous_candidates`: several candidates remain plausible.
- `version_unclear`: preprint and published versions differ or cannot be linked.
- `provider_unavailable`: provider failed, timed out, or rate limited.
- `unsupported_source_type`: book, thesis, lecture notes, proceedings volume, or
  private manuscript needs manual handling.

Boundary records should appear in reports so users understand why a chain such
as A -> B -> C -> D may stop at D.

## Public API

### Workspace Python API

Add:

```python
def search_external_reference(
    self,
    paper_id: str,
    blocked_id: str,
    *,
    providers: list[str] | None = None,
    max_candidates: int = 10,
    refresh: bool = False,
) -> dict: ...

def list_external_reference_searches(
    self,
    paper_id: str | None = None,
    blocked_id: str | None = None,
) -> dict: ...

def resolve_external_reference_candidate(
    self,
    paper_id: str,
    blocked_id: str,
    candidate_id: str,
    *,
    import_target: bool = False,
    artifact_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict: ...
```

`search_external_reference` may contact network providers unless tests install
mock providers. It returns candidates and boundaries, but does not create a
resolution.

`resolve_external_reference_candidate` uses the selected candidate target as the
input to v1.1.2 `resolve_external_reference`. It is the point where a candidate
becomes durable.

Default `import_target` is false for search-applied candidates. This avoids
turning a metadata choice into an import attempt unless the caller asks for it.

### MCP Tools

Add:

- `workspace_search_external_reference(paper_id, blocked_id, providers = null, max_candidates = 10, refresh = false) -> dict`
- `workspace_list_external_reference_searches(paper_id = null, blocked_id = null) -> dict`
- `workspace_resolve_external_reference_candidate(paper_id, blocked_id, candidate_id, import_target = false, artifact_dir = null, overwrite = false) -> dict`

MCP tools should return structured provider warnings instead of hiding partial
provider failures.

### CLI Commands

Add:

```powershell
papergraph-mcp search-external-reference `
  --workspace .\papergraph.sqlite3 `
  --paper-id local:source `
  --blocked-id external-import:blocked:abc123 `
  --max-candidates 10

papergraph-mcp list-external-reference-searches `
  --workspace .\papergraph.sqlite3 `
  --paper-id local:source

papergraph-mcp resolve-external-reference-candidate `
  --workspace .\papergraph.sqlite3 `
  --paper-id local:source `
  --blocked-id external-import:blocked:abc123 `
  --candidate-id reference-candidate:... `
  --import-target
```

The search command does not require a confirmation flag. The resolve command is
the explicit confirmation.

## Provider Design

Create:

```text
src/papergraph/reference_search.py
src/papergraph/reference_providers/
  __init__.py
  base.py
  crossref.py
  openalex.py
  arxiv.py
```

Provider interface:

```python
class ReferenceSearchProvider(Protocol):
    name: str

    def search(self, query: ReferenceSearchQuery) -> ReferenceProviderResult:
        ...
```

Each provider returns raw records plus normalized candidates. The aggregator
performs ranking and merging so provider modules stay small.

### Crossref

Primary use:

- DOI discovery;
- title/author/year/venue metadata;
- published versions.

Crossref failures are non-fatal. A timeout should return a provider warning and
allow OpenAlex/arXiv results to render.

### OpenAlex

Primary use:

- broad scholarly metadata;
- DOI links;
- open access URL hints;
- venue and publication year;
- links to arXiv when present.

OpenAlex should help detect `metadata_only`, `paywalled_or_restricted`, and
published/preprint linkage.

### arXiv

Primary use:

- arXiv ID discovery;
- title/author matching for preprints;
- version hints.

arXiv candidates can become importable targets through existing arXiv import.

## Ranking And Merging

Ranking uses additive deterministic evidence, not an LLM:

- exact DOI match: very strong;
- exact arXiv ID match: very strong;
- normalized title match: strong;
- author overlap: strong to moderate depending on count;
- year proximity: moderate;
- venue/publisher match: moderate;
- citation-context term overlap: weak to moderate;
- provider agreement on DOI/arXiv/title: strong;
- conflicting year/author/title: penalty;
- retracted/withdrawn metadata when provided: warning and penalty.

Candidates merge when:

- DOI matches exactly;
- arXiv ID matches exactly;
- one provider links DOI and arXiv for the same work;
- normalized title and first author match with compatible year.

When preprint and published versions appear related but not identical, render one
candidate group with separate target options:

- published DOI target;
- arXiv importable target;
- metadata warning about version choice.

## Confirmation Boundary

No user confirmation is needed for:

- searching providers;
- caching search runs;
- ranking candidates;
- rendering candidate tables in reports;
- adding search boundary notes;
- listing previous searches.

Explicit user intent is required for:

- applying a candidate as a resolution;
- importing an arXiv candidate;
- importing a local PDF target;
- downloading any remote file;
- overwriting an existing resolution;
- recursively searching or importing references from newly resolved papers;
- increasing search depth beyond one hop.

In CLI, explicit intent is expressed by running the apply/import command and by
flags such as `--import-target`, `--overwrite`, and future
`--recursive-depth`.

In MCP, explicit intent is the tool call itself from the controlling agent.
Tool descriptions must state the consequence clearly.

## Forward Literature Tracing

v1.1.3 should support bounded forward tracing as a search plan, not an
unbounded crawler.

Example:

1. Source paper A has blocked reference B.
2. User searches B and applies candidate B.
3. If B is imported or has enough metadata, PaperGraph can search blockers in B.
4. The process may identify C, then D.

The system must report where and why the chain stops:

- D may be too old to have a DOI.
- D may be a book or proceedings volume with only catalog metadata.
- D may be behind a publisher page with no accessible PDF.
- D may be cited under a translated title or abbreviated journal name.
- D may have multiple editions or versions.
- Provider rate limits may leave the chain incomplete.

The reading report should phrase this as:

> The reference trail currently stops at D because PaperGraph found only
> metadata and no importable electronic source. This does not mean D is
> mathematically irrelevant or unavailable elsewhere.

## Persistence

Add a schema migration for two tables:

```sql
CREATE TABLE reference_search_runs (
    search_run_id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL,
    query_json TEXT NOT NULL,
    provider_json TEXT NOT NULL,
    boundary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE reference_search_candidates (
    candidate_id TEXT PRIMARY KEY,
    search_run_id TEXT NOT NULL REFERENCES reference_search_runs(search_run_id) ON DELETE CASCADE,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL,
    target_json TEXT NOT NULL,
    score REAL NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    provider_record_json TEXT NOT NULL,
    warning_json TEXT NOT NULL,
    rank INTEGER NOT NULL
);
```

Candidate IDs are deterministic from source paper, blocked ID, canonical target,
and merged provider identifiers. Re-running with `refresh = false` returns the
latest cached run. `refresh = true` creates a new run.

## Data Flow

### Search

1. Recompute or load the blocked reference evidence for `paper_id`.
2. Find `blocked_id`.
3. Build query terms from:
   - citation keys;
   - raw citation snippets;
   - bibliography text;
   - title/author/year/venue hints if extractable.
4. Query Crossref, OpenAlex, and arXiv with bounded timeouts.
5. Normalize provider records.
6. Merge and rank candidates.
7. Detect boundary conditions.
8. Persist search run and candidates.
9. Return ranked candidates, provider warnings, and boundaries.

### Apply Candidate

1. Load candidate by `candidate_id`.
2. If an existing resolution exists and differs, require `overwrite = true`.
3. Convert candidate target to a v1.1.2 resolution target.
4. Call `resolve_external_reference(...)`.
5. If `import_target = true` and the target is importable, attempt import.
6. Return the v1.1.2 resolution payload plus candidate provenance.

### Report Rendering

Evidence Triage gains:

```json
{
  "searchable_external_references": 2,
  "candidate_resolved_references": 1,
  "ambiguous_external_references": 1,
  "search_boundaries": [
    {
      "blocked_id": "external-import:blocked:abc123",
      "kind": "metadata_only",
      "message": "Found a likely old proceedings paper, but no DOI or importable electronic source."
    }
  ]
}
```

Reading Reports render a subsection under External Import Plan:

```markdown
### Scholarly Reference Candidates

- `[17]`: strongest candidate is "Title..." (DOI: ..., confidence: strong).
  Evidence: title match, author overlap, Crossref/OpenAlex agreement.
- `[3]`: ambiguous. Two candidates have similar title and year; manual review is needed.

### Search Boundaries

- `[21]`: PaperGraph found metadata for an older proceedings item but no DOI,
  arXiv ID, stable URL, or local PDF. The trail stops here until the user
  supplies a source.
```

## Error Handling

- Unknown `paper_id`: workspace error.
- Unknown `blocked_id`: workspace error that lists available blocked IDs.
- All providers unavailable: persist a search run with provider warnings and no
  candidates.
- One provider fails: return partial candidates with a provider warning.
- Rate limit: return `provider_unavailable` or provider-specific warning.
- Malformed provider response: skip that provider record and record warning.
- Duplicate candidates: merge, do not duplicate.
- Existing different resolution: refuse apply unless `overwrite = true`.
- Candidate lacks importable target: applying still records DOI/URL/metadata
  resolution, but `import_target` returns a clear not-importable reason.

## Determinism

- Tests use mock providers only.
- Provider timeouts and result limits are configurable.
- Candidate sort order is by confidence bucket, score descending, target kind,
  normalized title, then candidate ID.
- JSON persistence uses sorted keys.
- Report rendering never depends on provider response order.
- Network-backed tests are opt-in and excluded from the default suite.

## Documentation

Update:

- `README.md`: introduce Scholarly Reference Resolver and explain that search
  candidates are not final identities until applied.
- `docs/reference/v1-core-contract.md`: add online scholarly search as a
  v1.1.3 extension with explicit evidence boundaries.
- `docs/walkthroughs/first-workspace.md`: show search -> candidate review ->
  apply candidate -> optional import.
- `.agents/skills/setting-up-papergraph/SKILL.md`: teach agents when to search,
  when to apply, and how to explain search boundaries.
- examples: add a candidate search payload and a report snippet with an old
  metadata-only reference boundary.

## Release Notes Shape

Release as `v1.1.3`.

Emphasize:

- scholarly search for blocked external references;
- published-paper support through Crossref/OpenAlex, not arXiv-only search;
- ranked candidates with evidence and warnings;
- fewer unnecessary user interruptions;
- explicit search boundaries for old, unavailable, ambiguous, or metadata-only
  references;
- integration with v1.1.2 Reference Import Closure.

Avoid claiming:

- complete bibliography resolution;
- automatic proof dependency recovery across papers;
- paywall access;
- publisher PDF downloading by default;
- correctness of the top candidate without user/application confirmation;
- unlimited recursive literature crawling.

## Tests

Add focused tests for:

- search combines Crossref, OpenAlex, and arXiv mock results into ranked
  candidates;
- DOI/published candidate outranks arXiv-only candidate when published metadata
  better matches the bibliography;
- arXiv candidate remains importable through v1.1.2 apply flow;
- ambiguous close candidates are labeled `ambiguous`;
- metadata-only old reference produces a clear `metadata_only` or
  `no_electronic_record_found` boundary;
- provider failure returns partial results with warnings;
- applying a candidate creates a v1.1.2 resolution;
- applying a different candidate over an existing resolution requires
  `overwrite = true`;
- Reading Report renders candidates and boundaries;
- default tests use mock providers and do not require network access.

Run before PR:

```powershell
uv run pytest tests\test_reference_search.py tests\test_reference_search_server.py tests\test_cli_reference_search.py tests\test_workspace_reference_resolution.py tests\test_workspace_reading_report.py tests\test_evidence_triage.py -q -p no:cacheprovider --basetemp .pytest-tmp
uv run pytest -q -p no:cacheprovider --basetemp .pytest-tmp
git diff --check
```

## Acceptance Criteria

v1.1.3 is ready when:

- a blocked external reference can be searched across Crossref, OpenAlex, and
  arXiv;
- ranked candidates preserve provider provenance and evidence;
- published DOI/OpenAlex candidates are first-class, not secondary to arXiv;
- low-risk search/report steps do not require user confirmation;
- applying a candidate routes through v1.1.2 Reference Import Closure;
- unresolved old or unavailable references produce clear boundary messages;
- bounded forward tracing can explain where a citation chain stops;
- MCP and CLI cover search, list, and apply flows;
- docs teach users that candidates are evidence-backed suggestions, not final
  truth;
- focused tests and the full deterministic suite pass.
