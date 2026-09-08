# Proof Block Association v0.9.1 Design

## Goal

PaperGraph v0.9.1 fixes the first v0.9 reading gap: LaTeX projects with explicit `proof` environments should store proof evidence and associate each proof with the result it proves when the proof immediately follows that result.

This is a focused patch release. It does not attempt proof-roadmap extraction or citation-level import planning; those remain planned for later v0.9.x releases.

## Problem

The PDF evidence path already extracts proof-like text blocks and associates an unlabeled `Proof.` block with the immediately preceding theorem-like result. The LaTeX project path does not. `latex_project_to_evidence_document` currently emits `proofs=()`, so TeX papers with ordinary:

```latex
\begin{theorem}\label{th:a}
...
\end{theorem}
\begin{proof}
...
\end{proof}
```

produce `proof: not_found` even though the source contains a proof environment. This makes reading paths stop too early and hides proof-local references from downstream dependency tools.

## Scope

### In Scope

- Discover `proof` environments in LaTeX project text.
- Create `ProofEvidence` records for those environments.
- Associate an unlabeled proof with the nearest preceding unassociated result when no other theorem-like result appears between the result and proof.
- Preserve the existing `immediately_follows_result` basis for this adjacent association.
- Store proof spans as TeX source evidence with accurate source file and source offsets.
- Extract local result mentions, citation mentions, and external result mentions from the newly stored TeX proof evidence by reusing existing evidence extractor functions.
- Update release pins from `0.9.0`/`v0.9.0` to `0.9.1`/`v0.9.1`.

### Out of Scope

- Named proof headings such as `Proof of Theorem 1.2` for TeX labels or numbers.
- Narrative roadmap extraction, such as "we prove Theorem X by splitting it into A, B, C".
- Turning plain citation lists into import candidates when no proof-local external result mention exists.
- Semantic dependency inference or proof verification.
- SQLite schema changes.

## Public Behavior

For a TeX project with adjacent result and proof environments:

- `workspace_add_local_paper` and `workspace_add_arxiv_paper` imports report nonzero `proof_count`.
- `workspace_get_result_proof(result_id)` returns:

```python
{
    "known": {
        "proof": {
            "result_id": "...::th:a",
            "association_basis": "immediately_follows_result",
            "association_confidence": 0.8,
            "method": "latex_proof_environment",
        }
    },
    "inferred": [
        {
            "basis": "immediately_follows_result",
            "confidence": 0.8,
            "method": "latex_proof_environment",
        }
    ],
    "unresolved": {},
    "warnings": [],
}
```

If the proof references another local result with `\ref`, `\cref`, `\Cref`, `\autoref`, or `\eqref`, the existing proof-dependency query should expose that mention when it names a stored result label.

If the proof cites an external result with bracket notation already supported by PaperGraph, such as `[12, Theorem 3.5]`, the existing external import planner should see the resulting external mention after import.

## Association Rule

The v0.9.1 rule is deliberately conservative:

1. Parse theorem-like environments and proof environments from the same combined LaTeX project text.
2. Sort all result/proof blocks by source offset.
3. For each proof environment, scan backward to the nearest preceding result block.
4. Associate only if that result has not already been associated with another proof.
5. Do not skip over another proof environment to reuse an older result.
6. Leave the proof unresolved if no eligible preceding result exists.

This matches common mathematical writing while avoiding broad inference.

## Data Flow

`latex_project_to_evidence_document` will:

1. Parse result nodes as it does today.
2. Parse proof blocks from `project.text`.
3. Build `SourceSpanEvidence` for both result and proof blocks.
4. Build `ResultEvidence` for result spans.
5. Build `ProofEvidence` for proof spans with `result_id` set by the adjacent association rule.
6. Call existing extractor helpers on those proofs:
   - `extract_local_result_mentions`
   - `extract_citation_mentions`
   - `extract_external_result_mentions`
7. Return one `EvidenceDocument` containing results, proofs, proof-local mentions, and external mentions.

## Tests

Add focused tests that fail on v0.9.0:

- TeX project import stores a proof immediately following a theorem and `get_result_proof` no longer returns `proof: not_found`.
- TeX proof-local `\cref{lem:a}` references resolve to local result mentions and appear in `get_proof_dependencies`.
- TeX proof-local `[12, Theorem 3.5]` citation evidence creates an external import candidate through `plan_external_imports_for_result`.
- A second proof immediately after the same result remains unresolved rather than stealing the same result twice.
- Release tests expect `0.9.1` pins and `PaperGraph/0.9.1`.

## Release

Release as `v0.9.1` after:

- local full `uv run pytest`
- PR CI success on Ubuntu and Windows for Python 3.10 and 3.12
- main CI success after merge
- pinned install smoke test:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.1 papergraph-mcp --version
```
