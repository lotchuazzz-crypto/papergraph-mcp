# PaperGraph v1.1.4: Bounded Reference Expansion and Compatibility Fixtures

Date: 2026-09-20
Status: Draft for user review; implementation not started
Baseline: v1.1.3, merged commit `596c6b7f0e1cfafc437ae60eadc869899c3e84bc`

## Goal and approved direction

Make a small literature-reading project advance from an imported paper through
its extracted references, with bounded automatic imports, durable progress,
and reviewable evidence. Ship reproducible compatibility fixtures in the same
release so the complete workflow has a stable acceptance baseline.

The user approved combining compatibility work and iterative import in v1.1.4,
using bounded expansion and automatically importing a unique strong candidate
with an importable source inside an approved budget. Ambiguous or insufficient
evidence requires selection; independent branches continue.

Defaults are two reference hops and ten newly imported papers. These are
defaults for an explicitly created expansion run, not permission to expand
whenever an existing search or report tool is called.

## Approaches and decision

1. Fixture-only release: establishes repeatability but leaves iterative reading
   manual. Insufficient for the combined scope the user selected.
2. Bounded persisted expansion backed by the same fixtures: selected approach.
   Builds on existing search and import APIs and makes automation measurable.
3. General literature crawler and arbitrary publisher downloads: substantially
   broader acquisition, identity, and scheduling work. Deferred.

## Existing implementation constraints

- Workspace schema is currently 7. Reference searches, candidates and resolutions
  already persist in SQLite; reports and Evidence Triage consume them.
- `plan_external_imports_for_paper` exposes directly identifiable arXiv targets
  and blocked references. Expansion must process both collections.
- Search confidence `strong` can currently arise from score or provider agreement.
  It is a display label, not a sufficient automatic-selection predicate.
- Existing import targets are arXiv source projects and user-supplied local PDFs.
  A DOI or an open-access URL alone does not make a target importable.
- `resolve_external_reference` returns an existing resolution early, including a
  failed import. Recovery therefore needs an explicit retry path.
- `workspace.py` is already large. Put new orchestration and storage helpers in
  focused modules, exposing thin Workspace methods rather than embedding the
  entire state machine there.

## Scope

Included: persisted expansion runs, approved policy snapshots, deterministic
breadth-first traversal, automatic-selection policy, branch-local boundaries,
manual decisions, deduplication, cycle detection, bounded calls, interruption
recovery, JSON and Markdown reports, CLI/MCP parity, fixtures and client recipes.

Deferred: arbitrary remote PDF fetching, publisher scraping, new scholarly
providers, semantic theorem matching, proof verification, general parser
improvements, unattended background scheduling and unbounded exploration.
Extracted citation trails must not be described as verified mathematical
dependency graphs or complete bibliographies.

## Entry points and authorization

Create a run from one or more paper IDs already in the workspace. To start from
a selected search candidate, first apply/import it through the existing API,
then use its paper ID as a root. A manual selection during a run can supply a
stored candidate, explicit normalized target, or an already imported paper.

Creating a run records the policy and initial frontier but performs no network
requests or imports. Advancing it explicitly executes that policy. MCP tool
descriptions and CLI help must say that advancing can search and download arXiv
sources, import papers and record resolutions without per-paper confirmation.

Policy fields:

- `max_depth`: integer 1..10, default 2; roots are depth 0.
- `max_new_papers`: integer 1..100, default 10, cumulative across resumes.
- `max_searches`: integer 1..1000, default 100, cumulative across resumes.
- `max_edges`: integer 1..10000, default 500, limits persisted reference edges.
- `providers`: nonempty supported-provider list, default existing three providers.
- `auto_select_policy`: `unique_strong_v1`, fixed for this release.

These validation ceilings keep a run finite; they are engineering limits, not
claims about an ideal literature-reading size. Policy changes require an
explicit update call and append a revision. Resume never resets counters or
increases a limit. A decreased limit cannot be below already consumed usage.
Updates cannot silently replace providers or automatic-selection policy.

Manual decisions authorize a target identity but do not bypass budgets or
authorize replacing existing papers/resolutions. Conflicting resolutions are
reported for review; replacement stays in the existing explicit overwrite flow.
Local paths must be supplied by the user/controlling client, never accepted from
provider metadata as executable local import instructions.

## Traversal and budget semantics

Process roots in normalized paper-ID order, then references breadth-first, with
stable ordering by source paper ID and stable reference key. An edge represents
one grouped planner reference, retaining all its extracted evidence. Duplicate
mentions in that group do not trigger separate work.

Importing a target from a depth-d paper gives it depth d+1. Papers at the maximum
depth can be imported and reported, but their outgoing references are not
searched or expanded. Mark this frontier as `depth_limit`; do not claim its
references have been exhaustively enumerated.

The paper budget counts distinct new workspace papers committed by this run,
including manual choices. Existing papers and duplicate targets cost zero.
Failed imports cost zero paper slots but consume a bounded work step. Reserve a
paper slot before acquisition and reconcile it after interruption. Once no slot
remains, stop new acquisition/search work; preserve pending frontier and report
`paper_limit`. Roots never consume the new-paper budget.

A search slot is reserved before invoking one blocker search across configured
providers. A cache hit costs zero searches; every fresh attempt, including a
failed or explicitly retried search, costs one. Provider calls retain bounded
timeouts and result sizes. Reaching the search limit preserves pending work.

The edge limit includes all recorded incoming edges, even to existing papers.
Discovery stores a stable cursor so increasing the limit can continue without
discarding unrecorded references. Reports state that discovery was truncated.

Each advance call processes at most `max_steps` (default 10, range 1..100), and
stops scheduling new steps after `time_budget_seconds` (default 20, range 1..60).
A step is one bounded discovery page, search, or import/reconciliation attempt.
An active request may finish after the time budget; transport timeouts still
apply. Return saved progress and a continuation indicator. No sleeping retry
loop or background worker is introduced.

## Automatic selection

Preserve v1.1.3 ranking for display. A separate pure predicate returns
`eligible`, `reason_codes`, `policy_version` and the selected target snapshot.
It must require all of the following:

1. Exactly one identity group has confidence `strong` after canonical identifier
   merging, and no candidate in the search is labelled `ambiguous`.
2. Identity evidence is either an exact DOI/arXiv identifier extracted from the
   source reference, or exact normalized title plus author overlap and exact
   year, corroborated by two distinct provider names on that identity.
3. There is no conflicting identifier, version, title, author, year, withdrawal
   or retraction warning for the selected identity. Missing metadata cannot
   satisfy the metadata-only route in item 2.
4. There is no competing plausible/strong identity with a different identifier
   and the same normalized title, or the same author/year evidence. Such a
   conflict requires review even if the numeric scores differ.
5. An importable target exists: an arXiv ID directly supported by source/provider
   evidence, or a local PDF explicitly attached by the user. DOI-to-arXiv mapping
   requires an explicit provider linkage, not a title-only guess.

Provider failure blocks automatic metadata-only selection because the search is
incomplete. Exact source-identifier matches may proceed despite another provider
failing if no identity/version conflict is observed. Store these warnings.
Record text and provenance used by the predicate; provider agreement alone is
insufficient. A manual choice may accept a weaker candidate, recorded as manual.

Direct planner arXiv candidates do not need a redundant online search, but must
have consistent source identifiers and pass the same version/conflict checks.
No implicit version upgrade or refresh of an already imported paper is allowed.

## Identity, shared targets and cycles

Use normalized arXiv IDs and DOI identifiers plus explicit provider linkage for
aliases. Keep version information separately. Do not merge workspace papers by
title alone. Local PDFs deduplicate by existing paper ID or a content digest
recorded on the import attempt; distinct unlinked arXiv/PDF records remain
distinct and may be flagged for review.

Represent the result as a graph with a tree presentation. Store every incoming
reference edge, but acquire each canonical target at most once per run. A
repeated node renders as a cross-reference; an ancestor link renders as a cycle.
Roots and pre-existing workspace papers participate in cycle detection.

The minimum discovered depth determines expansion eligibility. If a manual
decision later exposes a shorter path, update depth and reopen only previously
depth-limited discovery that is now permitted. Already processed references and
imports remain deduplicated.

## State and recovery

Run states: `ready`, `running`, `paused`, `waiting`, `completed`, `cancelled`,
`failed`. `ready` means runnable frontier exists, including after a bounded call.
`waiting` means only user decisions or retryable failures remain. `completed`
means no runnable or review work remains within policy; terminal source
boundaries may remain. Depth-limited frontiers can coexist with completion.
`paused` records a budget or explicit pause reason; `failed` is a run-wide storage
or invariant failure. Branch/provider failures do not fail the entire run.

Edge states: `queued`, `searching`, `needs_review`, `selected`, `importing`,
`imported`, `linked_existing`, `boundary`, `retryable_failure`, `skipped`.
Boundary reasons include `metadata_only`, `no_importable_source`,
`restricted_source`, `no_candidates`, `version_conflict`, and `stale_source`.
Use `restricted_source` only when evidence says access is restricted; a missing
download URL alone means `no_importable_source`.

Run summaries expose runnable, review, boundary, retry and frontier counts
separately. Retrying and supplying a source can reopen the corresponding edge.
Skipping a branch is an explicit recorded decision. Cancellation preserves
imported papers and all history; cancelled runs cannot advance.

Use a workspace-wide expansion execution lease with owner and expiry so two
clients cannot advance competing expansion runs concurrently. Renew while
active; reject a second owner. An expired lease can be reclaimed, recording an
interruption event and reconciling unfinished steps before scheduling new ones.
No database transaction is held open across network requests.

Before each import, persist an attempt ID, canonical target, baseline existence,
reserved budget slot and policy/decision provenance. On recovery inspect both
the paper and resolution record. Reuse a committed result and finish its edge;
never import it again merely because the edge was not updated before a crash.
An existing incompatible paper produces review instead of replacement.

Add an explicit internal retry operation for `failed_import` and incomplete
resolutions; do not rely on repeating the early-return v1.1.3 API. Preserve
attempt history. Search/candidate snapshots on expansion edges remain immutable
even if candidate tables are refreshed later. If source evidence changes,
mark affected unfinished edges `stale_source` and require a new decision/run.

## Persistence and components

Migrate schema 7 to 8 transactionally. Preserve older migration paths and reject
newer unsupported schemas using the existing policy.

New storage groups:

- `reference_expansion_runs`: ID, roots, policy revisions, state/reasons,
  usage/reservations, discovery cursors and timestamps.
- `reference_expansion_nodes`: run-scoped canonical identities, aliases, paper
  links, minimum depth, expansion status and source fingerprints.
- `reference_expansion_edges`: stable edge ID, source/target nodes, source
  reference key, evidence/search/decision snapshots and state/reason.
- `reference_expansion_attempts`: action ID, step type, target, phase, outcome,
  retry ancestry and budget reservation.
- `reference_expansion_events`: append-only state/policy/decision history.
- `reference_expansion_lease`: single workspace execution owner/expiry.

Uniqueness constraints enforce one node per canonical identity per run and one
edge per run/source/reference key. Paper and resolution links must not cascade
delete historical snapshots. Events and counters commit with state transitions.

Suggested modules: `reference_expansion.py` (policy/traversal),
`reference_expansion_store.py` (persistence/reconciliation),
`reference_expansion_report.py` (pure rendering). Workspace owns connection
lifecycle; existing provider adapters and import primitives remain shared.
Any changes to existing resolution/import internals need regression coverage.

## Public contract

All new JSON payloads carry `expansion_schema_version: 1` and a stable run ID.
Workspace methods, matching `workspace_` MCP tools and hyphenated CLI commands:

| Workspace method | Required input | Behavior |
| --- | --- | --- |
| `create_reference_expansion` | `root_paper_ids`; optional policy | Persist finite plan, no network/import |
| `advance_reference_expansion` | `run_id`; optional call limits | Execute approved policy, return progress |
| `get_reference_expansion` | `run_id` | Return policy, graph, counts and next actions |
| `list_reference_expansions` | optional state filter | Stable ordered run summaries |
| `decide_reference_expansion` | `run_id`, `edge_id`, decision | Select candidate/target/paper, skip or retry |
| `update_reference_expansion_policy` | `run_id`, numeric limits | Append explicit budget revision |
| `pause_reference_expansion` | `run_id` | Stop scheduling after active step |
| `cancel_reference_expansion` | `run_id` | Preserve state, forbid further advance |
| `export_reference_expansion` | `run_id`; format `json` or `markdown` | Render saved state without network |

Decisions accept exactly one of `candidate_id`, `target`, `existing_paper_id`,
`skip`, or `retry`; candidate ownership must match the edge and search snapshot.
A decision persists intent; a later advance performs the import. Advancing an
explicitly paused run resumes it; budget pauses resume only after enough budget
is available. Retry records a new bounded attempt; it does not reset usage.

CLI uses `--workspace`, `--run-id`, repeated `--root-paper-id` and explicit limit
flags. Export defaults to stdout; file export requires `--output` and refuses
overwrite without `--overwrite`. MCP returns report text/JSON for client-owned
file handling. Existing search/apply tools keep their defaults and signatures.

## Reports and reading integration

Expansion report includes roots, policy and usage, newly imported/reused papers,
reference tree with shared-target/cycle links, source evidence, automatic/manual
selection reasons, pending decisions, retry outcomes and frontier limits.
Every unresolved entry gives a concrete next action with run and edge IDs.

Reading Reports and Evidence Triage gain additive expansion summaries for runs
that include the paper. Recompute from current workspace state when requested.
At each advance return affected paper IDs and updated expansion summary; render
fresh paper/cross-paper reports through existing export APIs. Never silently
overwrite previously exported files. Documentation includes a complete export
recipe after each advance or manual decision.

Completion wording describes exhaustion within extracted evidence and approved
limits. Automatically selected identities are labelled policy-selected with
their evidence, not user-confirmed or mathematically verified.

## Reproducible fixtures and compatibility

Ship an openly reusable synthetic three-paper source set as the mandatory
offline baseline, extending existing fixtures where suitable. Include license,
provenance and an expected-output manifest. An optional real-paper walkthrough
records public source URLs, exact versions and hashes; only redistribute source
content if its license permits. Network-dependent acquisition is opt-in.

Inject recorded/synthetic provider responses and arXiv source packages at the
provider/acquisition boundary. Exercise real parsing, SQLite, public APIs and
report rendering. Default tests must fail on unexpected network access.

Golden JSON/Markdown normalizes only documented volatile fields: timestamps,
run/attempt IDs, absolute fixture paths and elapsed times. Preserve graph
structure, evidence, ordering, reasons, policy and usage counts. Compare resumed
and uninterrupted semantic outputs, allowing extra recovery events.

Mandatory scenarios:

1. A imports B automatically, then B exposes ambiguous C and metadata-only D;
   an independent eligible branch continues. Manual choice of C resumes work.
2. Same target via multiple references/providers imports once; all incoming
   evidence remains visible. A-B-A terminates with a cycle link.
3. Depth, paper, search and edge limits each stop at the exact boundary;
   explicit budget increase continues without resetting counters.
4. Provider disagreement, partial failure, weak match and incompatible versions
   cannot accidentally trigger automatic selection.
5. Interrupt before acquisition, after paper commit, and before edge completion;
   resume without duplicate paper count or import. Two advancing clients cannot
   acquire the execution lease simultaneously.
6. Failed import can explicitly retry; pre-existing resolutions/papers are reused
   or flagged for conflict. Source replacement invalidates unfinished evidence.
7. CLI and actual MCP stdio calls produce equivalent semantic outputs and errors;
   exported reports preserve evidence boundaries and pending-action IDs.
8. Schema-7 upgrade preserves existing papers/searches/resolutions; migration
   failure rolls back; older supported upgrade paths still reach schema 8.

Provide Codex, Claude and AutoClaw recipes with pinned version, workspace setup,
the same scenario prompt, explicit expansion budget, expected artifacts and
troubleshooting. Separate fixture/protocol tests from actual client validation.
Client matrix labels are `verified`, `documented_not_run`, or `failed`, with
client version/date and retained test evidence. Never infer client compatibility
from Python tests. Unavailable clients do not block release if clearly labelled;
the offline CLI and MCP protocol baseline is a release gate.

## Acceptance and release

v1.1.4 is ready when the mandatory scenarios pass, the full deterministic suite
passes, migration and installation smoke checks pass, and docs/examples explain
the policy, default budgets, continuation calls and review boundaries.

Update package version, diagnostics, pinned install/client examples and release
surfaces to 1.1.4 only during implementation/release preparation. Release notes
describe bounded reference expansion and reproducible compatibility fixtures;
list actual client validation status and acquisition limitations.

Implementation sequence: fixture contracts and auto-selection predicate;
schema/store and recovery; orchestration; public APIs and reports; client
recipes, golden outputs and release validation. This document is the design
review artifact; a separate implementation plan follows user review.
