# Offline reference-quality acceptance

All bibliography and provider records in `cases.json` are synthetic MIT-licensed
test material. Expected hints, identity groups, confidence, reasons and eligibility
were explicitly authored, not captured from resolver output. The corpus is a
bounded regression suite, not a real-world accuracy estimate.

Run `uv run python scripts/reproduce_reference_quality.py`. The same evaluator is
used by pytest and checks provider/record order invariance of the complete result.
No provider requests, imports or workspace mutations are performed. Every
`safety_negative` case must produce zero automatic selections.

`schema8.sql` and `schema8-manifest.json` were captured before implementation of
schema 9 from synthetic v1.1.4 state. They preserve original IDs, search payload,
resolution and paused expansion policy for migration tests; do not regenerate
them with the new resolver. Source-root paths are replaced with `<fixture-root>`.
