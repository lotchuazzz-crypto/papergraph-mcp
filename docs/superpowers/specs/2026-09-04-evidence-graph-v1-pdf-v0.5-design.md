# PaperGraph v0.5 Evidence Graph v1 and PDF Ingestion Design

## Goal

Upgrade PaperGraph from a theorem-label dependency graph over LaTeX sources into
the first version of an evidence-first proof-logic assistant. Version 0.5 should
import born-digital PDFs, extract theorem/proof/citation evidence with page and
span provenance, and store TeX-derived and PDF-derived records in one
source-agnostic evidence graph.

The release remains conservative. It may report explicit textual evidence,
bounded heuristic associations, confidence, and unresolved mentions. It must not
claim that a mathematical dependency exists unless that claim is supported by
stored source text, citation evidence, or a clearly identified extraction rule.

## Product Outcome

After v0.5, an MCP client can:

1. Open a local PaperGraph workspace.
2. Add an existing local or arXiv LaTeX paper as before.
3. Add a local born-digital PDF with an explicit `paper_id`.
4. List result-like blocks from either TeX or PDF sources.
5. Inspect the page/file/span evidence behind a result, proof, mention, or edge.
6. Ask for the proof associated with a result when PaperGraph has strong
   evidence for that association.
7. Ask which local result mentions occur inside a proof body.
8. Ask which external cited-result mentions occur inside a proof body, including
   unresolved bibliography references.
9. Receive diagnostics that separate known evidence, heuristic inference, and
   unresolved cases.

The public claim is deliberately narrow: PaperGraph v0.5 extracts and stores
proof-adjacent textual evidence from TeX and born-digital PDFs. It does not
verify proofs, perform semantic theorem matching, or recursively download the
literature.

## Current Architecture Constraints

PaperGraph v0.4.4 has a small and useful architecture, but several choices now
limit the proof-logic roadmap:

- `TheoremNode` represents theorem-like results but has no first-class source
  span, page, proof, mention, bibliography entry, or evidence-edge model.
- `parser.py` extracts theorem-like LaTeX environments and explicit references
  inside their bodies. It does not parse proof environments.
- `graph.py` treats theorem dependencies as resolved `\ref`, `\eqref`,
  `\autoref`, `\cref`, or `\Cref` labels in theorem statements only.
- `citations.py` records LaTeX citation commands and BibTeX resolution evidence,
  but not citation mentions inside proof bodies as proof-local evidence.
- `workspace.py` schema version 2 accepts only `source_type IN ('local',
  'arxiv')` and imports only `LoadedProject` TeX projects.
- MCP workspace tools expose theorem search, dependency traversal, and citation
  evidence, but not proof blocks, external result mentions, or evidence records.

The v0.5 design should preserve these working surfaces while adding a new
evidence layer underneath future proof-logic tools.

## Approaches Considered

### Evidence-first schema expansion with a PyMuPDF PDF adapter -- selected

Add a source-agnostic `EvidenceDocument` domain model, a born-digital PDF
extractor, and workspace schema v3 tables for evidence nodes, source spans,
result blocks, proof blocks, bibliography entries, mentions, and evidence-backed
edges. Existing TeX import continues to populate v0.4-compatible tables and also
emits Evidence Graph v1 records. PDF import emits Evidence Graph records
directly.

This route has the best product-to-risk ratio. It creates a real PDF capability
in v0.5 without forcing the old theorem graph to carry proof and PDF concepts it
was not designed for. PyMuPDF is the preferred PDF backend because it exposes
page text, blocks, words, and coordinates from born-digital PDFs through a
single local dependency.

### PDF layout prototype with pdfplumber

Build a strong standalone PDF extraction prototype before changing the
workspace. This may produce faster experiments around block boundaries and
layout heuristics, and pdfplumber is pleasant for char/word-level analysis.

The weakness is that PaperGraph would still not have a unified product model.
If the prototype sits outside the workspace, every MCP feature would have to be
integrated later. This is useful for isolated research, but not as the v0.5
release spine.

### Flatten PDF text into the existing theorem parser

Convert PDF text into a pseudo-TeX-like stream and reuse the existing
`TheoremNode` and `theorem_refs` model as much as possible.

This is the smallest implementation, but it pushes page spans, proof blocks,
citation mentions, external result mentions, and uncertainty into fields that
do not naturally represent them. It would make v0.6 and v0.7 harder. This route
is not recommended.

## Scope

v0.5 includes:

- Workspace schema v3 with source-agnostic evidence graph tables.
- Backward-compatible v0.4 theorem, dependency, and citation tools.
- `source_type='pdf'` for explicit local PDF imports.
- A new `workspace_add_pdf_paper(path: str, paper_id: str) -> dict` tool.
- Born-digital PDF text extraction with page number, text order, block order,
  optional bounding boxes, extraction method, and confidence.
- PDF result-block extraction for theorem, lemma, proposition, corollary,
  definition, claim, conjecture, example, remark, and proof-like headings.
- Proof-block extraction and conservative association to a nearby result.
- Proof-local local result mention extraction, such as `Lemma 2.4`,
  `Proposition 3.1`, `Theorem A`, and `Corollary 5.2`.
- Proof-local citation mention extraction, such as `[12]`, `[12, Theorem 3.5]`,
  `[HM10, Theorem B]`, and simple author-key styles when visible in text.
- Bibliography-region detection and conservative bibliography-entry extraction
  from PDF text.
- ArXiv ID, DOI, URL, year, raw label/index, and raw entry text preservation
  when extractable from PDF bibliography entries.
- External result mention records that combine a citation marker and visible
  result designator, without claiming semantic resolution.
- MCP tools to list results, fetch result/proof/evidence records, return
  proof-local dependencies, and list external result mentions.
- Deterministic fixtures and tests using small generated or checked-in
  born-digital PDFs.

v0.5 excludes:

- Scanned PDF OCR.
- LLM-only result, proof, or dependency extraction.
- Automatic cited-paper download.
- Recursive literature tracing beyond reporting explicit external-result
  mentions and possible identifiers.
- Semantic theorem equivalence.
- Proof verification.
- Main theorem detection as a product claim.
- Crossref, Semantic Scholar, OpenAlex, MathSciNet, zbMATH, or arbitrary web
  lookup.
- A graph visualization UI.

## Evidence Model

Introduce a source-agnostic domain model that TeX and PDF importers can both
produce before storage:

```text
EvidenceDocument
  paper
  spans[]
  results[]
  proofs[]
  bibliography_entries[]
  local_result_mentions[]
  citation_mentions[]
  external_result_mentions[]
  edges[]
```

### Source locations

Every extracted object refers to one or more source spans. A span is a precise
source location:

- TeX span: source file, start offset, end offset, and text excerpt.
- PDF span: page number, block index, optional bbox, text offset within page or
  block, and text excerpt.

Spans carry:

- extraction method, for example `latex_environment`, `latex_command`,
  `pdf_text_block`, `pdf_heading_regex`, or `pdf_proof_association`;
- confidence from `0.0` through `1.0`;
- a bounded source excerpt suitable for MCP responses;
- raw extracted text preserved locally in the workspace.

### Result blocks

A result block represents a visible theorem-like statement. Fields include:

- `result_id`, globally unique and caller-visible;
- `paper_id`;
- `kind`, `raw_kind`, `display_kind`, and `normalized_kind`;
- `label` for TeX labels when available;
- `visible_number` for PDF numbering such as `1.3`, `A`, or `2.1`;
- `title`;
- `statement`;
- source span IDs;
- extraction method and confidence.

For TeX, existing theorem local IDs remain stable and should map to result IDs.
For PDF, result IDs should be deterministic from paper ID, normalized kind,
visible number when present, and occurrence order. If two PDF results collide,
append a deterministic occurrence suffix instead of overwriting.

### Proof blocks

A proof block represents visible proof text. Fields include:

- `proof_id`;
- `paper_id`;
- `result_id` when associated;
- `association_basis`;
- `association_confidence`;
- proof text;
- source span IDs.

Strong association examples:

- A `Proof.` block immediately follows a result block before the next result or
  section heading.
- A heading such as `Proof of Theorem 1.1.` matches an existing visible result
  number.

Ambiguous proof blocks remain stored with `result_id = null` and an unresolved
diagnostic.

### Mentions

Mentions are not dependencies by themselves. They are textual evidence that may
support an edge.

Local result mentions store:

- raw text;
- normalized kind;
- visible number or label-like target hint;
- proof ID or result ID context;
- resolved target result ID when a unique local result matches;
- `resolution_status`, such as `resolved_unique`, `ambiguous`, or
  `unresolved`.

Citation mentions store:

- raw citation marker;
- citation style guess, such as numeric or author-year;
- raw key/index;
- source span IDs;
- resolved bibliography entry ID when a unique entry matches;
- `resolution_status`.

External result mentions store:

- raw text;
- citation mention ID;
- visible external result kind and number/title;
- bibliography entry ID when available;
- optional target paper ID when the bibliography entry resolves to an already
  imported paper;
- `resolution_status`.

## Graph Model

Evidence Graph v1 introduces explicit node and edge types:

```text
paper
source_span
result
proof
local_result_mention
citation_mention
bibliography_entry
external_result_mention
```

Edges include:

```text
paper --has_result--> result
paper --has_bibliography_entry--> bibliography_entry
result --has_proof--> proof
proof --mentions_local_result--> local_result_mention
local_result_mention --resolves_to_result--> result
proof --mentions_citation--> citation_mention
citation_mention --resolves_to_bibliography_entry--> bibliography_entry
citation_mention --mentions_external_result--> external_result_mention
external_result_mention --resolves_to_paper--> paper
```

Every edge stores:

- evidence span IDs;
- evidence text;
- extraction basis;
- confidence;
- resolution status;
- whether the edge is `source_evidence`, `heuristic_association`, or
  `model_inference`.

v0.5 should not create `model_inference` edges by default. The enum exists so
future LLM-assisted workflows have a safe place to put clearly labeled
non-source-derived suggestions.

## SQLite Schema

Schema version 3 should preserve existing v2 tables and add new tables rather
than deleting or renaming the current public model.

Keep existing tables:

- `workspace_meta`
- `papers`
- `theorems`
- `theorem_refs`
- `citation_evidence`

Change `papers.source_type` to accept `local`, `arxiv`, and `pdf`. Because
SQLite cannot easily alter a `CHECK` constraint in place, the implementation
plan should choose either a clean v3 initialization path plus explicit
unsupported-v2 error, or a careful v2-to-v3 table rebuild migration. The design
prefers a v2-to-v3 migration because users may already have v0.4 workspaces.

Add tables:

- `source_spans(id, paper_id, source_type, source_ref, page, block_index,
  start_offset, end_offset, bbox_json, text, excerpt, method, confidence)`.
- `results(result_id, paper_id, local_id, kind, raw_kind, display_kind,
  normalized_kind, label, visible_number, title, statement, method,
  confidence)`.
- `result_spans(result_id, span_id)`.
- `proofs(proof_id, paper_id, result_id, text, association_basis,
  association_confidence, method, confidence)`.
- `proof_spans(proof_id, span_id)`.
- `bibliography_entries(entry_id, paper_id, raw_label, raw_text, entry_type,
  title, authors_json, year, arxiv_id, arxiv_version, doi, url, method,
  confidence)`.
- `local_result_mentions(mention_id, paper_id, proof_id, raw_text, kind,
  visible_number, target_result_id, resolution_status, method, confidence)`.
- `citation_mentions(mention_id, paper_id, proof_id, raw_text, raw_key,
  entry_id, resolution_status, method, confidence)`.
- `external_result_mentions(mention_id, paper_id, proof_id, citation_mention_id,
  raw_text, external_kind, external_number, entry_id, target_paper_id,
  resolution_status, method, confidence)`.
- `evidence_edges(edge_id, source_type, source_id, edge_type, target_type,
  target_id, evidence_text, basis, confidence, resolution_status)`.
- `edge_spans(edge_id, span_id)`.

The implementation may adjust exact SQL names for clarity, but it must preserve
the conceptual boundaries above and keep every public MCP result traceable to
source spans.

## Import Flow

### TeX import

The existing `workspace_add_local_paper` and `workspace_add_arxiv_paper` tools
continue to behave as before. Internally, the TeX import flow should additionally
produce an `EvidenceDocument`:

1. Load the structured `LoadedProject`.
2. Parse theorem-like environments as today.
3. Create result records from theorem nodes.
4. Create source spans from TeX file offsets and excerpts.
5. Preserve existing `theorems` and `theorem_refs` rows for compatibility.
6. Convert existing citation evidence into bibliography/citation records where
   possible.

Proof extraction from TeX may be minimal in v0.5. If implemented, it should
detect explicit `proof` environments and `Proof of ...` headings conservatively.
If not implemented, TeX result records can still participate in Evidence Graph
queries with empty proof diagnostics.

### PDF import

`workspace_add_pdf_paper(path, paper_id)`:

1. Resolve the local PDF path and reject missing files, directories, and
   non-`.pdf` suffixes.
2. Extract born-digital page text, text blocks, block order, and coordinates.
3. Reject or warn on empty-text pages as likely scanned/OCR-required pages.
4. Detect section headings and bibliography region.
5. Detect result-like headings and collect statement text until the next result,
   proof, section, or bibliography boundary.
6. Detect proof headings and collect proof text until QED marker, next result,
   next proof, section boundary, or end of local block range.
7. Associate proof blocks with result blocks only when the evidence is strong.
8. Extract local result mentions and resolve only unique visible-number matches.
9. Extract citation mentions and map them to bibliography entries when possible.
10. Extract external result mentions from citation contexts.
11. Insert all records transactionally. A failed import must leave the previous
    version of that paper intact.

## PDF Extraction Heuristics

v0.5 should start simple and measurable:

- Normalize whitespace but preserve page boundaries.
- Treat each page as a sequence of text blocks in extracted reading order.
- Detect result starts with anchored headings such as `Theorem 1.1.`,
  `Lemma 2.3`, `Proposition A`, and `Corollary B.2`.
- Detect proof starts with `Proof.`, `Proof of Theorem 1.1.`, and similar
  anchored headings.
- Detect proof ends with common QED markers, the next result/proof heading, the
  next section heading, or bibliography start.
- Detect bibliography starts from headings such as `References` and
  `Bibliography`.
- Parse numeric bibliography entries like `[12] ...` first.
- Preserve unresolved and ambiguous cases instead of forcing a match.

The extraction basis must be reported in diagnostics. A result or proof can have
confidence below `1.0`; confidence is not a mathematical truth score, only an
extraction confidence.

## MCP Interface

Keep all existing tools compatible:

- `open_workspace`
- `workspace_add_local_paper`
- `workspace_add_arxiv_paper`
- `workspace_list_papers`
- `workspace_get_paper`
- `workspace_search_theorems`
- `workspace_get_dependencies`
- `workspace_get_dependency_diagnostics`
- `workspace_get_citations`
- all single-paper tools

Add:

### `workspace_add_pdf_paper(path: str, paper_id: str) -> dict`

Imports or replaces a local PDF paper. Returns paper metadata and counts:

- result count;
- proof count;
- bibliography entry count;
- local mention count;
- external mention count;
- unresolved count;
- scanned or empty-text page warnings.

### `workspace_list_results(paper_id: str | None = None, kind: str | None = None, limit: int = 50) -> list[dict]`

Lists source-agnostic result summaries from TeX and PDF papers. Results include
result ID, paper ID, kind metadata, label or visible number, title, source type,
first page/file location, confidence, and bounded excerpt.

### `workspace_get_result(result_id: str) -> dict`

Returns full result text, metadata, confidence, and source spans.

### `workspace_get_result_proof(result_id: str) -> dict`

Returns associated proof text and evidence when available. If no proof is
available, returns a diagnostic rather than an empty success that could be
misread.

### `workspace_get_proof_dependencies(result_id: str, recursive: bool = False) -> dict`

Returns proof-local local result mentions, resolved local dependencies,
external result mentions, unresolved mentions, extraction basis, and warnings.
For v0.5, `recursive=True` should recurse only through resolved local result
mentions inside the same workspace. It must not import cited papers.

### `workspace_get_external_result_mentions(result_id: str) -> list[dict]`

Returns external cited-result mentions found in the associated proof, including
raw citation marker, raw external result designator, bibliography evidence, and
target paper ID only when already resolved through stored identifiers.

### `workspace_get_evidence(node_or_edge_id: str) -> dict`

Returns the stored evidence text, source spans, extraction method, confidence,
and resolution status for one evidence graph node or edge.

## Diagnostics and User-Facing Semantics

Every dependency-like response should split information into:

- `known`: explicit source evidence and unique deterministic resolutions;
- `inferred`: heuristic associations such as proof-to-result links;
- `unresolved`: missing, ambiguous, or unsupported mentions;
- `warnings`: limitations relevant to the answer.

Required warnings include:

- empty PDF text may indicate scanned pages and unsupported OCR;
- proof association is heuristic unless the proof heading explicitly names the
  result;
- external result mentions identify what the source text says, not that the
  cited theorem is mathematically equivalent or actually sufficient;
- empty proof dependencies are not evidence that the proof has no dependencies.

## Components and Boundaries

### `pdf.py`

Owns local PDF loading and born-digital text extraction. It depends on the PDF
library and returns page/block/span structures. It does not know about SQLite or
MCP.

### `evidence.py`

Defines `EvidenceDocument`, source spans, result blocks, proof blocks,
bibliography entries, mentions, edges, confidence values, and serialization
helpers. It does not read files or talk to SQLite.

### `evidence_extractors.py`

Contains shared text heuristics for result headings, proof headings, local
result mentions, citation mentions, external result mentions, and bibliography
entry parsing. It works over extracted text blocks from either source where
possible.

### `parser.py` and `project.py`

Continue to own TeX project loading and theorem extraction. They may gain small
adapter functions to emit Evidence Graph records from existing TeX structures.

### `workspace.py`

Owns schema v3, migration or validation, transactional import, evidence graph
storage, and query APIs. It remains protocol-independent.

### `server.py`

Adds thin MCP adapters. It should not contain extraction, SQL assembly beyond
delegation, or graph reasoning.

## Error Handling

Domain errors should distinguish:

- invalid PDF path;
- non-PDF input;
- unreadable or encrypted PDF;
- empty born-digital text;
- unsupported scanned/OCR-required document;
- duplicate generated result IDs inside one paper;
- ambiguous proof association;
- ambiguous local result mention resolution;
- malformed or unsupported bibliography region;
- unsupported workspace schema;
- transaction/database failures.

Import failures are errors; unresolved mentions are data. A PDF with partial
extraction should import only when enough text exists to produce reliable page
spans and the response includes explicit warnings.

MCP tools translate domain errors into concise `ToolError` messages without
tracebacks. They should not expose private absolute source snippets unless the
tool's purpose is evidence inspection and the user asked for that paper's data
through the local workspace.

## Testing Strategy

### Domain model

- Validate evidence IDs, source spans, confidence ranges, and serialization.
- Verify TeX and PDF records can share the same result query interface.

### PDF extraction

- Generate or check in small born-digital PDF fixtures with one-column text.
- Extract page text, block order, and source spans deterministically.
- Warn or fail on an image-only PDF fixture with empty extracted text.
- Preserve page numbers and bounded excerpts.

### Result and proof extraction

- Detect theorem, lemma, proposition, corollary, definition, and remark headings.
- Preserve visible numbering.
- Associate `Proof.` with the immediately preceding result.
- Associate `Proof of Theorem 1.1.` with the matching result.
- Leave ambiguous proof blocks unresolved.

### Mentions and bibliography

- Extract local mentions from proof text and resolve unique visible-number
  matches.
- Preserve unresolved local mentions.
- Extract numeric citation mentions.
- Parse numeric bibliography entries.
- Extract arXiv IDs, DOI, URL, year, and raw text when present.
- Extract `[12, Theorem 3.5]` as an external result mention linked to entry
  `[12]` when that entry exists.

### Workspace

- Initialize schema v3 and migrate a v2 workspace without losing v0.4 records.
- Import TeX and PDF papers into the same workspace.
- Replace a PDF paper atomically.
- Query results, proofs, mentions, external mentions, and evidence spans.
- Keep existing v0.4 workspace tools compatible.

### MCP and CLI behavior

- Require an open workspace for all workspace tools.
- Translate PDF/evidence errors into `ToolError`.
- Verify all new tool payloads are deterministic and bounded.
- Keep no-argument server startup unchanged.

### Verification

Run the complete deterministic suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

No test should require live network access or private PDFs.

## Documentation

README should gain:

- a short v0.5 description;
- a PDF import example;
- a proof-dependency evidence example;
- a clear explanation of known, inferred, and unresolved response sections;
- limitations for scanned PDFs, proof verification, recursive downloads, and
  semantic theorem matching.

The architecture diagram should show two source adapters:

```text
TeX project -> TeX extractor -> EvidenceDocument -> SQLite workspace -> MCP
PDF file    -> PDF extractor -> EvidenceDocument -> SQLite workspace -> MCP
```

## Release Boundaries

The target release is `0.5.0` / `v0.5.0`.

Do not create tags, publish releases, merge PRs, delete branches, or change
unrelated clones without explicit user approval. The design document only
authorizes planning and implementation work inside `D:\ai4math\papergraph-mcp`.

## Acceptance Criteria

v0.5 is ready for review when:

- Existing v0.4.4 behavior and tests remain compatible.
- A local born-digital PDF can be imported into a workspace with `source_type`
  `pdf`.
- Imported PDF evidence includes page/span provenance.
- Result-like PDF blocks can be listed and inspected.
- At least one associated proof block can be queried by result ID.
- Proof-local local result mentions are extracted and uniquely resolved when
  possible.
- External result mentions such as `[12, Theorem 3.5]` are preserved with
  bibliography evidence.
- Unresolved and ambiguous mentions remain visible.
- Every dependency-like response separates known, inferred, unresolved, and
  warning sections.
- Schema v3 either migrates v2 workspaces safely or fails with a clear
  non-destructive message, with migration preferred.
- Complete deterministic tests pass on the supported Python versions.
