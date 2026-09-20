# Offline expansion fixtures

Expected output manifest: `docs/examples/reference-expansion-example.json` and
`docs/examples/reference-expansion-example.md`. Generate into a fresh directory
with `uv run python scripts/reproduce_reference_expansion.py --output-dir PATH`.
The baseline has 3 nodes, 5 edges, 2 new papers, 0 searches and completed state
at depth 3. `mixed_b` plus `provider-responses.json` exercises ambiguity and
metadata boundaries while the independent A-to-C branch completes.

Golden normalization covers run/attempt IDs, timestamp-derived commit event IDs, timestamps, source revision hashes
derived from import timestamps, and absolute fixture-root paths. It preserves
edge IDs, graph structure, ordering, source evidence, policies, reasons and
budget counts. Resumed runs may append extra advance/recovery events.

Original synthetic examples contributed to PaperGraph, 2026. Distributed under
the repository MIT license. These statements and IDs are test data, not claims
about real arXiv papers. Never download the fixture IDs from arXiv.

The test acquisition adapter maps 2401.10001/2/3 to a/b/c source directories.
It runs real parsing and workspace imports and forbids HTTP traffic.

Expected graph: A -> B, A -> C, B -> A, B -> C, C -> A.
From A at depth 3: two new papers, zero searches, five edges, three nodes;
each new target acquired once. Cycles and shared targets retain incoming edges.
