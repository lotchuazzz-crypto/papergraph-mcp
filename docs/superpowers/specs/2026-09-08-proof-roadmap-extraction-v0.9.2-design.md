# Proof Roadmap Extraction v0.9.2 Design

## Purpose

PaperGraph v0.9.1 can associate TeX proof environments with their preceding result and can turn explicit proof-local label references into reading-path dependencies. v0.9.2 adds one narrow layer above that: extract conservative proof roadmap phrases that explicitly announce subresults needed to prove the current result.

This is meant to improve the first-use research workflow where a main theorem proof says things like "It remains to prove Lemmas 2.1 and 2.2" or "The proof is divided into Propositions 3.4 and 3.5." Those phrases are often the real reading order even when they are not written as LaTeX `\ref` commands.

## Scope

In scope:

- Detect roadmap phrases inside already-associated proof text.
- Resolve explicitly named local results by kind and visible number when the target is unique.
- Preserve unresolved or ambiguous roadmap mentions as evidence rather than silently dropping them.
- Feed resolved roadmap mentions through the existing `local_result_mentions` table so `get_proof_dependencies`, `get_result_reading_path`, and reading queues benefit without a schema migration.
- Version docs, pins, diagnostics, and tests to v0.9.2.

Out of scope:

- Natural-language proof reconstruction.
- Inferring unstated mathematical dependencies.
- External citation import planning improvements.
- Cross-paper theorem resolution.
- Database schema changes.

## Extraction Rules

The extractor looks only at proof text. It recognizes short roadmap windows introduced by phrases such as:

- `it remains to prove`
- `we prove`
- `we first prove`
- `we shall prove`
- `the proof is divided into`
- `the proof reduces to`
- `it suffices to prove`

Within the bounded window after such a phrase, it extracts explicit result names:

- `Lemma 2.1`
- `Lemmas 2.1 and 2.2`
- `Propositions 3.4, 3.5, and 3.6`
- `Theorem A`

Plural group mentions inherit the result kind from the plural heading. For example, `Lemmas 2.1 and 2.2` yields `Lemma 2.1` and `Lemma 2.2`.

The extractor stops each roadmap window at a sentence boundary or at common proof-flow separators that would make the statement too broad. It does not scan the whole proof after a trigger.

## Evidence Model

Roadmap mentions are represented as `LocalResultMentionEvidence`.

- `method`: `proof_roadmap_result_regex`
- `confidence`: `0.72`
- `raw_text`: the exact extracted local phrase, such as `Lemma 2.1`
- `kind`: normalized result kind
- `visible_number`: extracted visible number
- `target_result_id`: the uniquely resolved result, or `None`
- `resolution_status`: `resolved_unique`, `ambiguous`, or `unresolved`

This keeps the feature compatible with existing storage and reading APIs.

## Deduplication

If a proof already contains a stronger mention to the same target result, roadmap extraction does not add a duplicate resolved target. Stronger mentions include:

- TeX label references from v0.9.1.
- Plain proof-local result mentions that already resolved uniquely.

If the roadmap mention is unresolved, it is kept, because it is useful review evidence.

## User-Facing Behavior

For a proof of `Theorem 1.3` containing:

```tex
It remains to prove Lemmas 1.1 and 1.2.
```

PaperGraph should expose both lemmas in direct proof dependencies when they are known local results. The reading path for `Theorem 1.3` should place the theorem top-down first, then the extracted lemma dependencies, and the bottom-up path should reverse that order for reading.

If one mentioned lemma is missing, it appears under unresolved local result mentions with the roadmap method.

## Testing

Tests must cover:

- Direct extraction from a singular roadmap phrase.
- Plural grouped extraction such as `Lemmas 1.1 and 1.2`.
- Integration from LaTeX project import through `get_proof_dependencies`.
- Integration through `get_result_reading_path`.
- No duplicate dependency when a proof has both `\cref{lem:base}` and a roadmap phrase naming the same lemma.
- Unresolved roadmap mention preservation.

Full release verification requires the complete test suite, PR CI, main CI, and a pinned `uvx` install check for `v0.9.2`.
