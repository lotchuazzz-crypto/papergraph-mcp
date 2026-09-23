# v1.1.5 Client Compatibility

Status vocabulary: `verified`, `documented_not_run`, `failed`. A successful
Python/protocol test is not evidence that a particular client UI works.

| Surface | Status | Version / date | Evidence |
| --- | --- | --- | --- |
| Offline CLI + SQLite | verified | PaperGraph 1.1.5 / 2026-09-23 | `tests/test_reference_quality_stdio.py` and `tests/test_reference_expansion_api.py`; retained JSON/Markdown examples |
| MCP stdio protocol | verified | SDK pinned in `uv.lock` / 2026-09-23 | Real server subprocess, initialize, list_tools, calls, saved state and errors in `tests/test_reference_quality_stdio.py` and `tests/test_reference_expansion_api.py` |
| Codex client | documented_not_run | Client version not measured / 2026-09-23 | Recipe below; no actual-client transcript retained |
| Claude client | documented_not_run | Client version not measured / 2026-09-23 | Recipe below; no actual-client transcript retained |
| AutoClaw client | documented_not_run | Client version not measured / 2026-09-23 | Generic stdio recipe only; configuration location unverified |

## Pinned launch contract

After the v1.1.5 tag is published, use command `uvx` with these separate arguments:

```json
["--from", "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.5", "papergraph-mcp"]
```

Before publication, use command `uv` with `run --project ABSOLUTE_CHECKOUT_PATH
papergraph-mcp`, recording the checkout commit. Do not claim that the unpublished
tag was successfully installed. The server uses stdio: an idle launch waiting for
input is normal, not a hang. No credentials or client configuration are changed
by the fixture tests.

For Codex and Claude, use the corresponding existing
[repository setup recipes](../../.agents/skills/setting-up-papergraph/references/client-configuration.md),
changing only the reviewed server entry. For AutoClaw, select its documented
custom MCP stdio server interface and enter the command/arguments above. Do not
assume its config-file location or that it accepts another client's JSON wrapper.
If no stdio server interface is available, use the CLI and retain a failed client
record instead of inventing configuration support.

Before configuring a client, obtain approval, back up the existing configuration,
preserve other servers, and restart only with permission. These instructions are
manual verification recipes, not assertions of current client-specific behavior.

## Same scenario for each client

First reproduce the [offline fixture](../walkthroughs/bounded-reference-expansion.md).
For an actual client test, use a fresh workspace outside the repository with an
explicitly chosen real paper or an already imported local root. Do not ask a
client to download the synthetic arXiv IDs from the offline fixtures.

Use this common prompt after substituting a real absolute workspace path and
existing root ID:

> Open workspace WORKSPACE_PATH and verify ROOT_PAPER_ID exists. Create a
> reference expansion with max_depth=2, max_new_papers=10, max_searches=100 and
> max_edges=500. I approve automatic selection only under unique_strong_v2.
> Advance it in bounded calls; keep the same run ID. If ready, continue; if a
> budget is exhausted, stop and ask before increasing it. Report ambiguous
> candidates and metadata boundaries without inventing identities. Let other
> eligible branches finish. For any manual decision I provide, record it and
> advance again. Export expansion JSON/Markdown and fresh Reading Reports for
> affected papers to new filenames. Show policy-selected versus manual choices,
> remaining actions, actual usage, and extraction limitations; do not claim
> proof verification or complete literature coverage.

Expected artifacts: stable run ID, saved policy/usage/graph/history, expansion
JSON, reference-tree Markdown, fresh Reading Reports and optional Cross-Paper
Reading Plan. A metadata-only boundary or arXiv acquisition failure is a valid
reported outcome, not proof of a broken client. Keep network-dependent tests
separate from the deterministic offline baseline.

## Troubleshooting and evidence record

- Launch failure: record `--version` and `doctor`; distinguish missing uv/Python,
  unavailable tag, permissions and network errors from MCP negotiation errors.
- Empty tool list: retain initialize/list_tools responses and client logs; confirm
  the launch uses stdio, without extra stdout from wrappers.
- Pending progress: `ready` requires another advance. `waiting` requires a saved
  decision/retry. `paused` includes a stop reason. `cancelled` cannot resume.
- Lease busy: another expansion is active; do not delete its lease. After a killed
  process the lease expires within 120 seconds.
- Sparse LaTeX/PDF evidence: report extraction limits and supply an explicit
  target rather than interpreting missing edges as absent mathematics.

For every future actual-client validation retain client name/version, OS, date,
PaperGraph commit/tag, sanitized config, scenario/root IDs, protocol/client logs,
run ID and artifact hashes. Change its matrix row only after examining that
evidence; redact credentials and private paper content before publishing logs.
