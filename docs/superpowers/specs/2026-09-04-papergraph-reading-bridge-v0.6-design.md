# PaperGraph Reading Bridge v0.6 Design

## Context

PaperGraph v0.5.0 added Evidence Graph v1, born-digital PDF ingestion, source
spans, deterministic proof evidence extraction, schema v3 storage, and MCP
evidence tools. The next product step is not to turn PaperGraph into a natural
language paper-reading agent. It is to make PaperGraph export evidence-grounded
reading bundles that AI4Math-Paper-Reading can consume.

The bridge keeps a strict boundary:

- PaperGraph is the evidence and structure substrate.
- AI4Math-Paper-Reading is the explanation and deep-reading workflow layer.
- PaperGraph may export statements, proof text, dependency evidence, source
  locations, unresolved mentions, warnings, and handles for bounded source
  lookup.
- PaperGraph must not claim proof verification, semantic theorem equivalence,
  hidden mathematical dependencies, or model-assisted proof-step completion.

The v0.6 target is a narrow bridge and review workflow release. OCR, main-result
detection, automatic cited-paper download, and cross-paper theorem matching stay
outside this release unless represented only as explicit unresolved evidence.

## Goals

1. Export a stable PaperGraph reading bundle for one stored paper.
2. Export a focused reading context for one result and its proof.
3. Provide bounded source-slice retrieval for L3 deep reading without requiring
   an agent to read an entire PDF or source database dump.
4. Provide a result-level reading path that turns known proof dependencies into
   a topological reading order.
5. Map PaperGraph evidence records into the subset of AI4Math-Paper-Reading
   structure JSON needed by L2/L3/L4 workflows.
6. Preserve fact/interpretation separation in the schema itself.

## Non-Goals

- Do not generate AI4Math `paper_summary`, natural-language theorem
  explanations, proof strategy summaries, or proof gap fillings inside
  PaperGraph.
- Do not force PaperGraph to emit a complete AI4Math `skill_base` v4.2
  structure JSON.
- Do not add OCR or scanned-PDF support.
- Do not perform semantic theorem matching across papers.
- Do not download cited papers automatically.
- Do not infer main theorems beyond transparent evidence already present in the
  workspace.

## Technical Pain Points

PaperGraph v0.5 exposes evidence through query tools, but those tools are still
too low-level for a paper-reading workflow. AI4Math-Paper-Reading expects a
single structured JSON source containing entities, dependencies, external
references, uncertainty logs, and proof framework data. Requiring an agent to
compose that contract manually from many MCP calls would make bridge behavior
hard to test and easy to drift.

AI4Math-Paper-Reading also assumes that JSON topology is ground truth but proof
step filling requires original source paragraphs. PaperGraph already stores
source spans, but the current API has no direct bounded source-slice tool. A
reading agent therefore lacks a standard way to request "the proof paragraph
around this result" without pulling excessive source text into context.

The ID systems differ. PaperGraph uses stable workspace IDs such as
`local:paper::pdf:theorem:1.1`; AI4Math uses paper URIs such as
`paper:arxiv:2401.0001#Thm-1`. The bridge should expose both instead of
renaming existing PaperGraph IDs.

## Recommended Approach

Use a minimal bridge export layer in PaperGraph core plus a thin adapter skill
outside PaperGraph.

PaperGraph v0.6 adds deterministic export tools:

- `workspace_export_reading_bundle(paper_id: str) -> dict`
- `workspace_export_result_reading_context(result_id: str) -> dict`
- `workspace_get_source_slice(span_id: str | None = None, result_id: str | None = None, proof_id: str | None = None, context: int = 1) -> dict`
- `workspace_get_result_reading_path(result_id: str, recursive: bool = True) -> dict`

These tools return bridge-schema payloads, not a full AI4Math `skill_base`
artifact. The payloads are deliberately close enough for AI4Math L2/L3/L4 to
consume, while marking fields that require model interpretation.

## Alternative Approaches Considered

### Full AI4Math JSON Export

PaperGraph could emit a nearly complete AI4Math `<slug>_structure.json`. This
would reduce adapter work, but it would pressure PaperGraph to fabricate or
guess fields such as `paper_summary`, `section_map`, proof strategies, and main
theorem roles. That violates the evidence-first boundary and creates a brittle
contract tied to one external skill version.

### Adapter-Only Bridge

A local `papergraph-paper-reading` skill could call existing v0.5 tools and
assemble reading contexts itself. This avoids PaperGraph code changes, but the
bridge logic would live in prompts instead of tested code. It would be harder to
version, harder to validate, and more likely to produce inconsistent payloads
across agent runs.

### Recommended Minimal Export Layer

PaperGraph should own deterministic transformation from workspace evidence to a
stable bridge schema. The adapter skill should own how that schema is consumed
by AI4Math-Paper-Reading. This gives PaperGraph testable contracts while keeping
interpretation in the agent layer.

## Bridge Schema

All bridge payloads include:

```json
{
  "bridge_schema_version": "1",
  "papergraph_version": "0.6.0",
  "source_policy": {
    "facts_from": "papergraph_evidence_graph",
    "interpretation_from": "consumer",
    "proof_verification": false,
    "semantic_matching": false
  },
  "warnings": []
}
```

`bridge_schema_version` versions the export contract independently from the
SQLite schema. Consumers should reject unknown major versions and tolerate
additional fields.

## Reading Bundle Contract

`workspace_export_reading_bundle(paper_id)` returns one paper-level artifact:

```json
{
  "bridge_schema_version": "1",
  "paper": {
    "paper_id": "local:paper",
    "source_type": "pdf",
    "source_ref": "C:/Papers/example.pdf",
    "source_version": null,
    "title": null,
    "authors": [],
    "main_file": "example.pdf"
  },
  "uri_map": {
    "paper_uri": "paper:local:paper",
    "entities": {
      "local:paper::pdf:theorem:1.1": "paper:local:paper#Thm-1.1"
    }
  },
  "results": [],
  "proofs": [],
  "entities": [],
  "dependency_index": {},
  "external_mentions": [],
  "source_handles": [],
  "completeness_check": {},
  "uncertain_log": [],
  "interpretation_policy": {
    "paper_summary": "requires_consumer_interpretation",
    "proof_gap_filling": "requires_bounded_source_slice",
    "main_result_detection": "not_provided"
  },
  "warnings": []
}
```

### Results

Each `ResultEvidence` maps to a `results[]` item and an AI4Math-like
`entities[]` item.

Result fields:

- `result_id`: existing PaperGraph ID.
- `papergraph_id`: duplicate explicit name for consumer clarity.
- `reading_uri`: bridge URI, for example `paper:local:paper#Thm-1.1`.
- `type`: AI4Math uppercase type such as `THEOREM`, `LEMMA`,
  `PROPOSITION`, `COROLLARY`, `DEFINITION`, `CLAIM`, `REMARK`, or `EXAMPLE`.
- `kind`, `display_kind`, `visible_number`, `label`, `title`.
- `statement`: verbatim extracted statement text.
- `location`: first page/source/block summary derived from source spans.
- `source_handles`: handles that can be passed to `workspace_get_source_slice`.
- `confidence`, `method`.

AI4Math-like entity fields:

- `type`: uppercase type.
- `label`: prefer display kind plus visible number, fall back to `reading_uri`.
- `statement`: copied from `ResultEvidence.statement`.
- `location`: derived from source spans.
- `dependencies`: resolved local dependency labels or reading URIs.
- `uncertain_dependencies`: unresolved local mentions with reasons.
- `external_refs`: bibliography-backed or unresolved external result mentions.
- `proof_methods`: proof association summaries only; no natural-language proof
  strategy is generated.
- `shared_node`: false unless computed from known dependency topology.
- `auto_labeled`: true only for generated claim-like nodes.

### Proofs

Each `ProofEvidence` maps to `proofs[]`:

- `proof_id`
- `result_id`
- `reading_uri`
- `text_excerpt`: bounded excerpt, not necessarily the whole proof.
- `source_handles`
- `association_basis`
- `association_confidence`
- `method`
- `confidence`

The reading bundle may include full proof text only if it is already bounded to
the proof span. For larger future spans, the bundle should expose handles and
require `workspace_get_source_slice`.

### Dependencies

`dependency_index` is keyed by `result_id`:

```json
{
  "local:paper::pdf:theorem:1.1": {
    "known": {
      "resolved_local_results": [],
      "external_result_mentions": []
    },
    "inferred": [],
    "unresolved": {
      "local_result_mentions": [],
      "citation_mentions": [],
      "external_result_mentions": []
    },
    "warnings": []
  }
}
```

This payload is derived from `workspace_get_proof_dependencies(result_id,
recursive=false)` for paper-level export. Recursive expansion belongs in
`workspace_get_result_reading_path`.

### External Mentions

External mentions preserve:

- raw source text.
- external kind and number.
- citation mention ID.
- bibliography entry ID.
- target paper ID when explicitly known.
- resolution status.
- source handles and span trail.

They do not claim that the external result was located or semantically matched
unless a future version adds explicit evidence for that operation.

### Completeness Check

The bridge emits a conservative `completeness_check`:

- `dependency_integrity`: generated from resolved and unresolved dependency
  evidence.
- `self_containment`: `high`, `medium`, or `low`, based only on external and
  unresolved dependency counts.
- `external_deps`: external result mentions and bibliography-backed mentions.
- `isolated_results`: results not reached from any other known local
  dependency edge, labeled as structural isolation only.
- `circular_deps`: cycles detected in known local dependency graph.
- `summary`: omitted or marked `requires_consumer_interpretation`.

## Result Reading Context Contract

`workspace_export_result_reading_context(result_id)` returns a focused payload
for L3 reading:

```json
{
  "bridge_schema_version": "1",
  "result": {},
  "proof": {},
  "dependencies": {},
  "reading_path_preview": {},
  "source_slice_handles": [],
  "interpretation_prompts": {
    "allowed": [
      "plain_language_explanation",
      "proof_gap_filling",
      "symbol_table",
      "uncertainty_review"
    ],
    "requires_source_slice_for": [
      "proof_gap_filling",
      "implicit_claim_extraction"
    ]
  },
  "warnings": []
}
```

This is the preferred payload for `/paper.proof [Thm-ID]`. It includes the
verbatim result statement, associated proof evidence, local/external dependency
evidence, unresolved mentions, and source handles. It does not include completed
proof-step narration.

## Source Slice Contract

`workspace_get_source_slice(...)` returns bounded source text around a span,
result, or proof. Exactly one selector is required:

- `span_id`
- `result_id`
- `proof_id`

`context` is an integer from 0 through 5 and counts neighboring source spans on
each side of the anchor. The default is 1.

Response:

```json
{
  "selector": {
    "kind": "proof_id",
    "value": "local:paper::proof:1"
  },
  "paper_id": "local:paper",
  "source_type": "pdf",
  "source_ref": "C:/Papers/example.pdf",
  "context": 1,
  "anchor_span_ids": ["local:paper::span:3"],
  "slices": [
    {
      "span_id": "local:paper::span:2",
      "page": 1,
      "block_index": 1,
      "role": "before",
      "text": "Theorem 1.1. Main result.",
      "method": "pdf_text_blocks",
      "confidence": 0.9
    },
    {
      "span_id": "local:paper::span:3",
      "page": 1,
      "block_index": 2,
      "role": "anchor",
      "text": "Proof. By Lemma 1.2 and [12, Theorem 3.5].",
      "method": "pdf_text_blocks",
      "confidence": 0.9
    }
  ],
  "bounded": true,
  "warnings": []
}
```

The tool must not return the entire paper unless the entire paper is already
within the explicit bounded slice. If the requested slice would exceed internal
size limits, it should truncate by span count and report a warning.

## Reading Path Contract

`workspace_get_result_reading_path(result_id, recursive=True)` returns a
deterministic graph-derived path:

```json
{
  "result_id": "local:paper::pdf:theorem:1.3",
  "recursive": true,
  "top_down": [],
  "bottom_up": [],
  "edges": [],
  "external_stops": [],
  "unresolved_stops": [],
  "cycles": [],
  "warnings": []
}
```

`top_down` starts from the target result and follows known local dependencies.
`bottom_up` reverses the acyclic known-local portion so a reader can build from
base results toward the target. External mentions become stop nodes. Unresolved
mentions become stop nodes with explicit reasons.

This tool supports the "logical chain between theorem/proposition statements"
experience. The result reading context plus source slices support the "concrete
explanation" experience.

## URI Mapping

PaperGraph IDs remain canonical inside storage. The bridge adds consumer-facing
URIs:

- Paper URI: `paper:<paper_id>` with characters preserved after PaperGraph
  normalization.
- Result URI: `paper:<paper_id>#<KindAbbrev>-<visible_number>`.
- If no visible number exists, use `paper:<paper_id>#<KindAbbrev>-<local_id-slug>`.

Kind abbreviations:

- `Theorem` -> `Thm`
- `Lemma` -> `Lem`
- `Proposition` -> `Prop`
- `Corollary` -> `Cor`
- `Definition` -> `Def`
- `Claim` -> `Claim`
- `Remark` -> `Rem`
- `Example` -> `Ex`

The bridge must include both directions in `uri_map`:

- `papergraph_to_reading`
- `reading_to_papergraph`

Consumers should display reading URIs but call PaperGraph tools with
PaperGraph IDs.

## AI4Math-Paper-Reading Mapping

For L2:

- Consume `paper`, `entities`, and `results`.
- Treat `statement` as verbatim extracted evidence.
- Generate `paper_summary`, symbol tables, and plain-language explanations in
  the skill layer.

For L3:

- Consume `workspace_export_result_reading_context`.
- Use `dependencies` as topology.
- Call `workspace_get_source_slice` before proof gap filling or implicit claim
  extraction.
- Mark all explanation beyond source text as model-assisted.

For L4:

- Consume `completeness_check`, `uncertain_log`, `warnings`,
  `external_mentions`, and unresolved stops.
- Critique self-containment and dependency quality as reading diagnostics, not
  as proof correctness judgments.

For graph rendering:

- Consume `workspace_get_result_reading_path` or `dependency_index`.
- Compute visual topology from known local dependencies.
- Render external and unresolved stops separately.

## Fact and Interpretation Policy

Every exported payload must make provenance obvious:

- `known`: directly stored or resolved evidence.
- `inferred`: deterministic extraction metadata such as proof association basis
  and confidence.
- `unresolved`: mentions or citations PaperGraph could not resolve.
- `warnings`: extraction caveats.
- `requires_consumer_interpretation`: fields that a reading skill may generate.

The bridge should use the word "inferred" only for deterministic extraction
inference, not mathematical explanation. Natural-language explanation,
background reconstruction, gap filling, and implicit claim extraction belong in
the consumer.

## Error Handling

- Unknown paper ID: raise the same MCP-visible `ToolError` style used by
  current workspace tools.
- Unknown result/proof/span ID: return a clear unknown-ID error.
- Invalid source-slice selector: require exactly one selector.
- Invalid `context`: require integer 0 through 5.
- Missing proof: reading context returns unresolved proof status and warning.
- Empty dependency evidence: include the existing empty-dependency warning; do
  not imply mathematical independence.
- Unknown bridge schema version in consumers: fail closed.

## Implementation Boundaries

The v0.6 code should add small, focused workspace methods and MCP wrappers. It
should reuse current storage tables and v0.5 evidence query helpers wherever
possible.

Suggested workspace methods:

- `export_reading_bundle(paper_id: str) -> dict`
- `export_result_reading_context(result_id: str) -> dict`
- `get_source_slice(...) -> dict`
- `get_result_reading_path(result_id: str, recursive: bool = True) -> dict`

Suggested helper module:

- `src/papergraph/reading.py`

This module should contain deterministic mapping helpers, URI construction,
AI4Math-like entity shaping, dependency path construction, and source-slice
payload shaping. It should not access SQLite directly unless doing so clearly
reduces duplication; prefer workspace query methods for persistence access.

## Validation Plan

Tests should cover:

1. Reading bundle export for the existing simple PDF fixture.
2. Reading bundle export for TeX-derived evidence from a local project.
3. Result reading context includes statement, proof association, dependencies,
   unresolved mentions, external mentions, source handles, and warnings.
4. Source slice requires exactly one selector.
5. Source slice is bounded by `context` and never returns unrelated full-paper
   text.
6. Source slice works by `span_id`, `result_id`, and `proof_id`.
7. Reading path follows recursive local dependencies in deterministic order.
8. Reading path emits external and unresolved stop nodes.
9. URI map is stable and reversible for visible-number and no-number results.
10. MCP wrappers expose the same contracts and convert workspace exceptions to
    tool errors.
11. Snapshot tests assert bridge schema shape without over-constraining ordering
    where ordering is intentionally semantic.
12. README documents the bridge workflow without claiming proof verification or
    semantic matching.

## Release Criteria

v0.6 is ready when:

- All existing v0.5 tests still pass.
- New bridge tests pass.
- The README documents a complete local workflow:
  `open_workspace` -> import paper -> export reading bundle -> export result
  context -> get source slice -> get reading path.
- The bridge payloads expose enough structure for AI4Math-Paper-Reading L2/L3
  to run without reading the whole paper.
- The documentation states that PaperGraph exports evidence and the reading
  skill performs interpretation.

## Open Follow-Up Work

- A local `papergraph-paper-reading` adapter skill can be added after v0.6 API
  design is accepted.
- Main-result detection can become a later evidence-ranked tool.
- Cross-paper external result resolution can become a v0.7 feature once the
  bridge can represent stop nodes and source handles reliably.
- OCR support should wait until source slicing and correction workflows are
  stable.
