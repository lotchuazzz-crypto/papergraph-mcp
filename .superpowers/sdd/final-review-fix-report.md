## Final Review Fix - Evidence Graph/PDF

- Centralized resolved evidence statuses and made recursive proof dependency traversal follow `resolved_unique` PDF local mentions.
- Added `known.resolved_local_results[*].via_mentions` with traced local mention evidence, including `mention_id`, `raw_text`, `spans`, and `span_trail`.
- Added PDF workspace regression coverage for recursive local dependencies and strengthened the MCP server payload test for resolved local mention evidence.
- Updated README wording for stored TeX/PDF evidence results and dependency bucket semantics.
