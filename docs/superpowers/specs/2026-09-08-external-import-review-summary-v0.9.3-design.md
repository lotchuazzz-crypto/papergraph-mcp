# External Import Review Summary v0.9.3 Design

## Purpose

PaperGraph v0.9.0 introduced external import planning, v0.9.1 made TeX proofs visible, and v0.9.2 made proof-roadmap dependencies visible. v0.9.3 improves the next review step: when PaperGraph suggests importing an external arXiv paper, the candidate should explain why in a compact, researcher-readable summary.

The goal is not to add new external resolution logic. The goal is to make the existing evidence easier to audit before a user or agent downloads anything.

## Scope

In scope:

- Add a per-candidate `review` payload to external import plans.
- Summarize which local result IDs motivate the candidate.
- Summarize which proof IDs contain the evidence.
- Summarize citation keys and raw cited result texts involved.
- Preserve the existing `evidence`, `counts`, `source`, `status`, and warning fields.
- Keep the plan schema version unchanged at `1` for backward compatibility, because the change is additive.
- Update version pins and docs to `v0.9.3`.

Out of scope:

- Automatically importing papers.
- Ranking candidates by mathematical importance.
- Matching external theorem statements.
- Fetching arXiv metadata during planning.
- Database schema changes.

## Candidate Review Payload

Each candidate in `workspace_plan_external_imports_for_result`, `workspace_plan_external_imports_for_queue`, and `workspace_plan_external_imports_for_paper` gains:

```json
{
  "review": {
    "local_result_ids": ["local:paper::pdf:theorem:1.1"],
    "proof_ids": ["local:paper::proof:1"],
    "citation_keys": ["12"],
    "raw_texts": ["[12, Theorem 3.5]"],
    "evidence_summary": "Needed by 1 local result through 1 proof; citation keys: 12; cited result evidence: [12, Theorem 3.5]"
  }
}
```

Rules:

- Values are deduplicated and sorted for deterministic output.
- `local_result_ids` is derived from evidence `result_id`.
- `proof_ids` is derived from evidence `proof_id`.
- `citation_keys` is derived from evidence `citation_key`.
- `raw_texts` includes non-empty raw evidence snippets, bounded to a small deterministic list.
- If a list is empty, it remains an empty list rather than disappearing.
- `evidence_summary` is short and purely descriptive; it must not claim the dependency is mathematically verified.

## User-Facing Behavior

For a plan generated from a theorem whose proof cites `[12, Theorem 3.5]`, the candidate for `2401.12345` should tell the reviewer that:

- this candidate is motivated by the theorem result ID;
- the evidence occurs in the theorem proof ID;
- citation key `12` is involved;
- the cited local evidence text includes `[12, Theorem 3.5]`.

This helps a first-use agent produce a better import plan without inventing dependencies or downloading external sources automatically.

## Testing

Tests must cover:

- Candidate `review` payload for result-scoped plans.
- Candidate `review` payload for queue-scoped plans.
- Candidate `review` payload for paper-scoped plans.
- Deduplication when the same citation evidence reaches the candidate through multiple plan sources.
- CLI JSON output still includes the additive `review` payload.
- Existing external import planner tests remain compatible.
- Release pin tests and full suite pass locally before handing push instructions to the user.
