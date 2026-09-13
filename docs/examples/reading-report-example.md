# Reading Report: Example Paper

This is a compact example artifact showing the shape of a PaperGraph Reading Report. It is not generated from a real unpublished paper.

## Paper

- Paper ID: `local:example-a`
- Source type: `pdf`
- Title: Example Paper
- Result count: 3
- Proof count: 2
- Citation count: 1
- Report format: `markdown`
- Report schema version: 1

## Paper Map

- Recommended start result: `local:example-a::pdf:theorem:1.1`
- Evidence status: `usable`
- Main-result candidates: 1
- Reading route items: 4
- External risks: 1
- Unresolved risks: 0

## Main-Result Candidates

1. `local:example-a::pdf:theorem:1.1` theorem - Theorem 1.1
   - Score: 7
   - Statement: Every example object has the stated fixed point property.
   - Reasons:
     - `title_signal` weight 4: result text contains a main-result cue
     - `proof_dependency_signal` weight 1: reading path evidence is available

## Recommended Reading Route

1. `local:example-a::pdf:theorem:1.1` start - selected_main_candidate
2. `local:example-a::proof:2` required - proof_evidence
3. `local:example-a::pdf:lemma:1.2` recommended - local_dependency
4. `local:example-a::external-mention:1` caution - external_risk

## Local Logic Chain

- `local:example-a::pdf:theorem:1.1` uses local evidence involving `local:example-a::pdf:lemma:1.2`.

## External Reading Risks

- Review candidate: arXiv:2401.12345
  - Citation keys: 12
  - Review summary: Needed by 1 local result through 1 proof.

## Evidence Quality

- `external_dependencies`: External import candidates are visible from stored evidence.

## Evidence Boundaries

- PaperGraph does not verify proofs.
- PaperGraph does not infer hidden mathematical prerequisites.
- PaperGraph does not perform semantic theorem matching.
- Empty dependencies mean no supported extraction evidence was found, not that no mathematical dependencies exist.

## Next Commands

```powershell
papergraph-mcp --workspace <WORKSPACE> get-paper-map local:example-a
papergraph-mcp --workspace <WORKSPACE> plan-external-imports-for-paper local:example-a
```
