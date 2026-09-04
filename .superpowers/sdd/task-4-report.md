# Task 4 Report: Workspace Schema v3 and Evidence Storage

Status: DONE

Commit created:
- `f79ced3` `feat: persist evidence graph workspace records`

Files changed:
- `src/papergraph/workspace.py`
- `tests/test_workspace.py`
- `tests/test_workspace_server.py`
- `tests/test_workspace_evidence.py`

RED verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `5 failed in 0.73s`
- Expected failure evidence:
  - `assert SCHEMA_VERSION == 3` failed because current value was `2`.
  - `Workspace` had no `import_evidence_document` method.
  - v2 workspace metadata stayed at `('2',)` instead of migrating to `('3',)`.

Implementation summary:
- Bumped workspace schema to v3 while preserving v0.4 theorem/citation tables and payload shapes.
- Added evidence storage tables for source spans, results, result-span links, proofs, proof-span links, bibliography entries, local mentions, citation mentions, external result mentions, evidence edges, and edge-span links.
- Added v2 to v3 migration that rebuilds `papers` with `source_type IN ('local', 'arxiv', 'pdf')`, preserves legacy rows, creates evidence tables, and updates metadata in a single explicit transaction.
- Implemented `Workspace.import_evidence_document(...)` as an atomic replace operation that consumes `EvidenceDocument`, stores all evidence records, and returns `WorkspaceImportResult`.
- Implemented result/proof/dependency/external/evidence query APIs requested in the brief.
- Kept external mention `target_paper_id` as stored text rather than a local `papers` foreign key so evidence can name external papers before those papers are imported into the workspace.

Test adjustments:
- Preserved and used the interrupted agent's draft `tests/test_workspace_evidence.py`, including the added external mention and transaction rollback coverage.
- Updated existing schema assertions from version `2` to `3`.
- Updated future-schema rejection fixtures from version `3` to `4`.
- Expanded the expected initialized table set to include the new evidence tables.
- Kept existing workspace server payload assertions unchanged except for `schema_version`.

GREEN verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `5 passed in 1.06s`
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `75 passed in 17.14s`

Concerns:
- None.

## Fourth Review Fix: Preserve Direct Bibliography Edge Spans

Status: DONE

Files changed:
- `src/papergraph/workspace.py`
- `tests/test_workspace_evidence.py`

RED verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py::test_direct_span_backed_bibliography_entries_keep_edge_spans -q -p no:cacheprovider`
- Result: `1 failed in 0.54s`
- Expected failure evidence:
  - An edge referencing a directly span-backed bibliography entry returned `get_evidence(edge_id)["spans"] == []`.

Implementation summary:
- Preserved any source-span IDs already keyed by a bibliography entry ID when deriving edge spans.
- Kept the existing empty fallback for bibliography entries that are only traceable through citation or external mention inheritance.
- Added a focused regression importing a bibliography entry whose direct `SourceSpanEvidence.span_id` equals the `entry_id`, with an edge referencing that entry.

GREEN verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py::test_direct_span_backed_bibliography_entries_keep_edge_spans -q -p no:cacheprovider`
- Result: `1 passed in 0.46s`
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `88 passed in 22.57s`

Concerns:
- None.

## Third Review Fix: Require Result and Proof Source Spans

Status: DONE

Files changed:
- `src/papergraph/workspace.py`
- `tests/test_workspace_evidence.py`

RED verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `2 failed, 15 passed in 3.92s`
- Expected failure evidence:
  - `ResultEvidence` with empty `span_indices` was accepted instead of raising `ValueError`.
  - `ProofEvidence` with empty `span_indices` raised a later mention traceability error instead of the clear proof span validation error.

Implementation summary:
- Added import-time validation that results and proofs must reference at least one source span.
- Reused `_validate_span_indices(...)` so empty-span rejection happens before bounds checks and before downstream traceability validation.
- Added focused regression tests for empty result and proof `span_indices` cases with explicit `ValueError` message expectations.

GREEN verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `17 passed in 3.47s`
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `87 passed in 20.23s`

Concerns:
- None.

## Review Fix: Evidence Span Traceability

Status: DONE

Files changed:
- `src/papergraph/workspace.py`
- `tests/test_workspace_evidence.py`

RED verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `6 failed, 3 passed in 2.22s`
- Expected failure evidence:
  - Incomplete `result_source_spans`, `proof_source_spans`, and `evidence_edge_source_spans` tables were accepted because schema validation did not check link-table columns.
  - Dependency mention payloads had no `evidence_id` or source spans.
  - `get_evidence(...)` returned empty or undocumented span payloads for inherited evidence nodes and edges.

Implementation summary:
- Added required-column validation for `result_source_spans`, `proof_source_spans`, and `evidence_edge_source_spans`.
- Inserted `evidence_edge_source_spans` during `import_evidence_document(...)`, deriving edge spans from node evidence IDs, source span IDs, or inherited parent proof spans.
- Added span-trail payloads to `get_evidence(...)` so results/proofs expose direct spans and bibliography entries, local mentions, citation mentions, external result mentions, and edges expose a documented parent/evidence trail.
- Added `evidence_id`, `spans`, and `span_trail` to dependency mention records returned by `get_proof_dependencies(...)`.
- Added focused tests requiring traceable evidence payloads for supported evidence ID types, dependency mention payloads, edge span persistence, and link-table column validation.

GREEN verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `9 passed in 2.17s`
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `79 passed in 18.97s`

Concerns:
- None.

## Second Review Fix: Reject Untraceable Evidence Records

Status: DONE

Files changed:
- `src/papergraph/workspace.py`
- `tests/test_workspace_evidence.py`

RED verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `7 failed, 8 passed in 3.30s`
- Expected failure evidence:
  - `get_external_result_mentions(...)` returned plain external mention rows without `evidence_id`, `spans`, or `span_trail`.
  - `import_evidence_document(...)` accepted an unreferenced bibliography entry that would later produce empty `get_evidence(...)` spans/trail.
  - `import_evidence_document(...)` accepted local, citation, and external mentions with no traceable parent proof/citation trail.
  - `import_evidence_document(...)` accepted edges with empty or unknown `evidence_ids`.

Implementation summary:
- Added import-time traceability validation for bibliography entries, mentions, and evidence edges.
- Bibliography entries now require either a direct stored source span whose `span_id` matches the `entry_id`, or a traceable citation/external mention reference.
- Local and citation mentions now require a known parent proof with stored source spans; external mentions require either that parent proof or a traceable citation mention.
- Evidence edges now require nonempty `evidence_ids`, and every referenced evidence ID must be known and traceable.
- `get_external_result_mentions(...)` now returns the same trace-enriched mention payload shape used by `get_proof_dependencies(...)`.
- Added direct bibliography span lookup by `SourceSpanEvidence.span_id` for bibliography entries that can be traced directly without changing the dataclass shape.

GREEN verification:
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `15 passed in 3.15s`
- Command: `.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py tests/test_workspace_server.py tests/test_workspace_evidence.py -q -p no:cacheprovider`
- Result: `85 passed in 19.85s`

Concerns:
- None.
