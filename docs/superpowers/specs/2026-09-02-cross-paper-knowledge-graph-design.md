# PaperGraph v0.4.0 Cross-Paper Knowledge Graph Design

## Goal

Extend PaperGraph from a single-paper theorem graph into a persistent,
queryable knowledge graph spanning multiple LaTeX papers. Version 0.4.0 must
let an MCP client collect local and arXiv papers in one workspace, preserve each
paper's internal theorem dependencies, derive explainable paper-to-paper
citation edges from LaTeX and BibTeX, and search theorem nodes across the
collection.

The release remains deterministic and local-first. It does not use embeddings,
an LLM, or heuristic semantic equivalence to invent relationships between
theorems.

## Product outcome

After v0.4.0, an agent can:

1. Open a durable PaperGraph workspace.
2. Add several local or arXiv LaTeX projects without replacing earlier papers.
3. List the papers and theorem counts in the workspace.
4. Search theorem statements across every imported paper.
5. Traverse theorem dependencies inside a paper using globally unique IDs.
6. Ask which imported papers cite, or are cited by, a selected paper.
7. Inspect the citation key and bibliographic evidence behind every cross-paper
   edge.
8. See unresolved citations instead of silently losing them.

The public claim is deliberately narrow: PaperGraph builds a multi-paper
theorem and citation knowledge graph from explicit LaTeX evidence. It does not
claim to understand that two differently worded theorems are equivalent.

## Approaches considered

### In-memory collection

Keep several `PaperGraph` instances in a dictionary inside the MCP server. This
is the smallest change, but the collection disappears when the server exits,
cannot be inspected independently, and is a weak foundation for a knowledge
graph product.

### JSON workspace

Serialize papers, theorem nodes, and edges into one JSON document. This is easy
to inspect, but every update rewrites the whole collection, transaction safety
is poor, and indexed cross-paper search becomes increasingly awkward.

### SQLite workspace — selected

Store papers, theorem nodes, internal references, citations, and import metadata
in SQLite. SQLite is included with Python, supports transactions and indexes,
requires no service, and keeps the local-first installation model unchanged.
It also provides a clean storage boundary so a future release can add full-text
or semantic indexes without changing the MCP contract.

## Scope

v0.4.0 includes:

- A versioned SQLite workspace created or opened from an explicit local path.
- Multiple local and arXiv papers in one workspace.
- Stable paper IDs and globally unique theorem IDs.
- Paper metadata extracted from source when available.
- Theorem containment, internal dependency, and paper citation edges.
- Citation extraction from common LaTeX citation commands.
- BibTeX discovery and arXiv-identifier resolution for imported papers.
- Explicit unresolved-citation records with their source evidence.
- Cross-paper theorem search and graph queries through new MCP tools.
- Atomic paper replacement when a source is refreshed.
- Schema migration/version checks suitable for later releases.
- Deterministic tests, cross-platform CI, packaging validation, documentation,
  and a v0.4.0 release-readiness update.

v0.4.0 excludes:

- Embeddings or vector databases.
- LLM-generated links, theorem equivalence, contradiction, or generalization.
- PDF citation extraction or PDF fallback.
- Citation resolution through arbitrary web searches.
- DOI, Crossref, Semantic Scholar, or OpenAlex network calls.
- Automatic recursive downloading of every cited paper.
- Collaborative or hosted workspaces.
- A browser-based graph visualization.

## Identity model

### Paper IDs

Every stored paper has a stable, caller-visible `paper_id`.

- arXiv papers use `arxiv:<base-id>`, for example
  `arxiv:2401.12345`. The optional arXiv version is stored separately so that
  importing `v2` refreshes the same logical paper rather than creating a second
  node.
- Local papers require an explicit portable ID from the caller, such as
  `local:my-preprint`. IDs must match a conservative lowercase slug grammar.
  PaperGraph does not derive identity from an absolute path because paths are
  machine-specific, and it does not derive identity from content because normal
  edits would unexpectedly create a new paper.

Adding an existing paper ID replaces that paper only after the new source has
been loaded, parsed, validated, and written successfully inside one database
transaction.

### Theorem IDs

The existing parser continues to produce a paper-local theorem ID. The
workspace ID is:

```text
<paper_id>::<local_theorem_id>
```

For example:

```text
arxiv:2401.12345::thm:main
local:my-preprint::lemma:2
```

The workspace rejects duplicate local theorem IDs within one paper instead of
silently overwriting them. Unlabelled theorem counters remain deterministic for
the same expanded source order, but labelled nodes are the preferred stable
identity.

## Graph model

The workspace exposes three explicit relationship types:

```text
Paper --CONTAINS--> Theorem
Theorem --DEPENDS_ON--> Theorem
Paper --CITES--> Paper
```

`DEPENDS_ON` edges remain intra-paper in v0.4.0 because LaTeX `\ref` labels are
normally scoped to one project. A missing internal reference is recorded as an
unresolved theorem reference and is never converted into a guessed cross-paper
edge.

Every `CITES` edge stores provenance:

- source paper ID;
- LaTeX citation key;
- citation command;
- matched bibliography file and entry type when available;
- normalized cited arXiv ID;
- resolved target paper ID, or `null` when the cited paper is not in the
  workspace.

Multiple citation keys may support the same paper-to-paper edge. Query results
retain all evidence records rather than collapsing away their origin.

## Project loading and provenance

The current `load_latex_project()` string-returning API remains supported. A new
structured loader result is added for workspace imports. It contains:

- root file;
- expanded text;
- included source files in deterministic traversal order;
- bibliography files referenced by `\bibliography{...}` or
  `\addbibresource{...}`;
- source spans sufficient to associate parsed nodes and citations with files.

The implementation reuses the existing path resolution, comment handling,
cycle detection, arXiv extraction, main-file selection, and cache safety rules.
It must not read files outside the project root through bibliography commands.
Missing or unsafe bibliography paths become explicit import errors.

Paper metadata is extracted locally when present:

- title from `\title{...}`;
- authors from `\author{...}`;
- arXiv base ID and requested version from the import request;
- root file relative path;
- source type and source reference;
- import timestamp and parser version.

Title and author extraction is best-effort. Missing metadata does not prevent an
otherwise valid graph import.

## Citation extraction and resolution

The citation extractor recognizes comma-separated keys in common commands,
including `\cite`, `\citep`, `\citet`, `\autocite`, `\parencite`, and
`\textcite`, while ignoring commented commands.

Referenced BibTeX resources are parsed into entries keyed by their citation
keys. An entry resolves to an arXiv paper when a valid arXiv identifier can be
obtained from, in priority order:

1. `eprint` together with an arXiv `archivePrefix`;
2. an `arxiv` field;
3. an arXiv URL in the `url` field;
4. an `arXiv:` identifier in the `note` field.

Resolution normalizes versioned identifiers to the base paper ID while
preserving the cited version as evidence. A citation is marked unresolved when
the key has no bibliography entry, the entry has no supported arXiv identifier,
or the identified arXiv paper has not been added to the workspace. These cases
are distinguishable in query results.

The parser uses `pybtex>=0.25,<0.27`, whose public parsing API accepts files or
strings and returns bibliography entries and fields. It is a runtime dependency
because workspace imports need it outside the test environment. The supported
range is locked and exercised on Python 3.10 and 3.12 in CI rather than
attempting to implement the BibTeX grammar with regular expressions.

## SQLite schema

The initial schema uses normalized tables and foreign keys:

- `workspace_meta(key, value)` stores `schema_version` and application metadata.
- `papers(paper_id, source_type, source_ref, source_version, title, authors_json,
  main_file, imported_at, parser_version)`.
- `theorems(global_id, paper_id, local_id, kind, title, label, content,
  source_file, position)`.
- `theorem_refs(source_global_id, ref_label, target_global_id)` where the target
  is nullable for unresolved internal references.
- `citation_evidence(id, source_paper_id, citation_key, command, bib_file,
  bib_entry_type, cited_arxiv_id, cited_version, target_paper_id,
  resolution_status)`.

Indexes cover theorem `paper_id`, theorem `kind`, normalized title/content
search fields, citation source, citation target, and cited arXiv ID. Foreign
keys use cascading deletion so transactional paper replacement cannot leave
orphaned theorem or citation rows.

Search in v0.4.0 is deterministic case-insensitive substring matching over
title and content with optional `paper_id`, `kind`, and result-limit filters.
SQLite FTS and semantic search are deferred until a measured need exists.

The database enables foreign keys, uses parameterized statements, and performs
imports within explicit transactions. A newer unknown schema version fails
closed with an actionable error; an empty database is initialized automatically.
No destructive migration is performed in v0.4.0.

## Components and boundaries

### `project.py`

Defines the structured loaded-project representation and composes the existing
loader with safe bibliography discovery. It depends on filesystem loading but
not on SQLite or MCP.

### `citations.py`

Extracts LaTeX citation uses, parses referenced BibTeX files, normalizes arXiv
identifiers, and emits citation evidence records. It is a pure domain layer apart
from reading already-approved project files.

### `workspace.py`

Owns paper/global identity, graph assembly, transactional import, schema
initialization, replacement, and query operations. It depends on the domain
models and SQLite but not on MCP.

### `server.py`

Translates MCP inputs and domain errors. It keeps existing single-paper tools
unchanged and adds thin workspace tools. SQL, BibTeX parsing, and graph logic do
not live in the server module.

These boundaries allow citation parsing, persistence, and protocol behavior to
be tested independently.

## MCP interface

Existing tools and return values remain compatible:

- `load_paper`
- `load_arxiv_paper`
- `list_theorems`
- `get_theorem`
- `get_dependencies`
- `where_used`

New tools use a separate workspace namespace in their names:

### `open_workspace(path: str) -> dict`

Open an existing SQLite workspace or initialize a new one. Returns the resolved
path, schema version, paper count, and theorem count. A successful call replaces
the active workspace only after validation.

### `workspace_add_local_paper(path: str, paper_id: str) -> dict`

Load a local root `.tex` file into the active workspace. Returns paper metadata,
theorem counts, citation counts, and unresolved counts.

### `workspace_add_arxiv_paper(arxiv_id: str, main_file: str | None = None,
refresh: bool = False) -> dict`

Reuse the existing safe arXiv preparation pipeline, then transactionally add or
replace the normalized arXiv paper.

### `workspace_list_papers() -> list[dict]`

List stored papers with metadata and graph counts in stable paper-ID order.

### `workspace_get_paper(paper_id: str) -> dict`

Return one paper's metadata, theorem summary counts, outgoing/incoming resolved
citation counts, and unresolved citation count.

### `workspace_search_theorems(query: str, paper_id: str | None = None,
kind: str | None = None, limit: int = 20) -> list[dict]`

Search across theorem titles and bodies. Results contain global ID, paper ID,
local ID, kind, title, source file, and a bounded content excerpt. An empty query
is rejected; `limit` is bounded from 1 through 100.

### `workspace_get_dependencies(global_theorem_id: str,
recursive: bool = False) -> list[dict]`

Traverse stored theorem dependencies using globally unique IDs. Recursion is
cycle-safe and deterministically ordered.

### `workspace_get_citations(paper_id: str, direction: str = "outgoing",
include_unresolved: bool = True) -> list[dict]`

Return incoming or outgoing paper citation evidence. Incoming results are
necessarily resolved. Direction accepts only `incoming` or `outgoing`.

No removal tool is included in v0.4.0. Re-import replaces a known paper; manual
deletion is deferred so this release does not add an avoidable destructive MCP
operation.

## State and compatibility

The server maintains two independent optional states:

- the existing active single-paper `PaperGraph`;
- an active persistent `Workspace` connection.

Using an existing load tool does not mutate the workspace. Adding a paper to the
workspace does not replace the active single-paper graph. This separation keeps
existing clients predictable and prevents a partially failed workspace import
from corrupting either state.

Workspace query tools fail with a concise instruction to call `open_workspace`
when no workspace is active. Closing or switching workspaces happens internally
only after the replacement workspace has passed schema validation.

## Error handling

Domain exceptions distinguish:

- invalid paper IDs or global theorem IDs;
- missing or unsafe local project paths;
- loader/include failures;
- missing, unsafe, or malformed bibliography files;
- duplicate theorem IDs;
- unsupported or newer workspace schemas;
- unavailable or unwritable workspace paths;
- transaction and database integrity failures;
- unknown papers or theorems;
- invalid query filters.

MCP tools translate these exceptions into `ToolError` messages without exposing
SQL statements, cache internals, or traceback details. A failed import rolls
back completely and leaves the previous stored version intact. A failed
workspace open leaves the previously active workspace usable.

Unresolved citations are data, not import failures. They are counted in import
results and returned through citation queries with a resolution reason.

## Testing strategy

### Identity and models

- Normalize modern, legacy, and versioned arXiv IDs into stable paper IDs.
- Validate local paper slugs and global theorem ID parsing.
- Reject duplicate local theorem IDs within one paper.

### Structured loading and provenance

- Preserve deterministic include order and source-file provenance.
- Discover `\bibliography` and `\addbibresource` files relative to the declaring
  file.
- Ignore commented commands and accept omitted `.bib` suffixes.
- Reject traversal, symlinks escaping the project root, missing files, and
  malformed resource declarations.

### Citations

- Extract supported citation commands and comma-separated keys.
- Parse representative BibTeX strings including nested braces and multiline
  fields through the selected library.
- Resolve each supported arXiv field pattern and preserve cited versions.
- Distinguish missing entries, unsupported identifiers, and absent workspace
  targets.
- Preserve multiple evidence records for one resolved paper edge.

### Workspace persistence

- Initialize and reopen a workspace across independent connections.
- Import multiple papers with colliding local theorem labels without collision.
- Query containment, internal dependencies, incoming/outgoing citations, and
  unresolved citations.
- Replace one paper atomically while retaining other papers.
- Roll back simulated parser, citation, and database failures.
- Enforce foreign keys, schema versions, deterministic ordering, and bounded
  search results.
- Verify paths and content with quotes or non-ASCII characters.

### MCP behavior

- Require an open workspace for all workspace operations.
- Verify every new tool delegates to the domain layer and translates errors.
- Prove existing single-paper state is independent and all old tool payloads
  remain unchanged.

### Acceptance

- Keep all 113 v0.3.1 tests passing.
- Add deterministic multi-paper fixtures with at least three papers, duplicate
  local labels, a citation cycle, one unresolved key, and one BibTeX entry for a
  paper not yet imported.
- Run the complete suite on Windows and Linux with Python 3.10 and 3.12.
- Build and clean-install the wheel.
- In a temporary workspace, import three fixtures, reopen the database, search
  across all three, and traverse both directions of the citation graph.
- Run a manual live acceptance with two public arXiv source packages only after
  deterministic tests pass. The live check is not part of CI.

## Documentation and launch message

The README gains a concise multi-paper example showing:

```text
open workspace
    -> add paper A
    -> add paper B
    -> search all theorems
    -> explain A --CITES--> B with citation evidence
```

The architecture diagram distinguishes project loading, citation extraction,
workspace persistence, and MCP queries. Documentation clearly labels citation
edges as explicit source-derived evidence and avoids semantic-understanding
claims.

The primary v0.4.0 message is:

> Build a local, explainable theorem-and-citation knowledge graph from a
> collection of LaTeX papers, then query it through MCP.

## Release model

Development occurs on `feature/v0.4-cross-paper-graph`, based on the `v0.3.1`
commit on `main`. Implementation is delivered through a pull request. The
implementation workflow may push the feature branch and create the pull request
after validation, but it does not merge `main`, create `v0.4.0`, or publish a
Release without explicit user authorization at that time.

## Acceptance criteria

v0.4.0 is ready for review when:

- At least three papers coexist in one reopened SQLite workspace.
- Paper and theorem IDs remain unique despite colliding LaTeX labels.
- Internal theorem dependencies retain their current behavior.
- Supported `\cite` commands and BibTeX entries yield evidence-backed citation
  records.
- Imported arXiv targets resolve to paper-to-paper edges and unknown targets
  remain visibly unresolved.
- Cross-paper theorem search and citation traversal are available through MCP.
- Re-import and workspace switching are atomic on failure.
- Existing MCP tools and payloads remain compatible.
- No test requires network access, and all supported CI environments pass.
- The wheel installs cleanly and the documented multi-paper example matches the
  implemented tool schemas.
