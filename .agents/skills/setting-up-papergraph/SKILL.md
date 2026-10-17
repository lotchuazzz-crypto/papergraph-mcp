---
name: setting-up-papergraph
description: Use when a user has cloned PaperGraph MCP and asks to install, initialize, configure, set up, or start using it with an agent or MCP client.
---

# Set up PaperGraph

Guide one conservative setup conversation. This skill does not change PaperGraph runtime behavior.

Before responding, read [references/usage-prompt.md](references/usage-prompt.md) completely. Present that reusable prompt before requesting install approval, even if the user may defer setup.

## Response contract

Keep these four phases short and in this order. Do not show later phases as completed before their work occurs.

### What the user gets

Briefly explain that PaperGraph lets an MCP client analyze LaTeX papers, build a multi-paper workspace, search theorem-like content, and inspect explicit citation evidence. Give the reusable prompt in a copyable block. Translate it only under the preservation rule in its reference.

Before loading arXiv papers:

1. If a repository directory already exists, inspect its branch, HEAD, working changes, and remote URL. Run `git fetch --tags origin` before trusting remote-tracking refs, and verify the remote default branch (do not assume `main`). Run `python scripts/check_onboarding.py --repository <checkout>` to compare local refs. Its `freshness_verified: false` means it did not fetch: matching a cached ref is not proof of freshness. Updating an old feature branch's upstream is not updating default-branch instructions. Unless the user explicitly requests a historical version, use instructions from the freshly fetched remote default revision. Preserve dirty or historical checkouts: use a separate clean checkout for current instructions, never reset, stash, overwrite, or switch the user's working files automatically. If fetch fails, disclose that freshness is unknown; do not say “already latest.”
2. Verify the pinned `uvx --from ... papergraph-mcp --version` command and run pinned `uvx --from ... papergraph-mcp doctor` or call `get_environment_diagnostics`.
3. For raw user wording, Markdown links, URLs, or prose, call `validate_arxiv_request` or `load_arxiv_request`.
4. If a user provides both an arXiv ID and an arXiv URL, `load_arxiv_request` must stop before loading unless they identify the same paper.
5. Use `load_arxiv_paper` only after the user has provided one already-disambiguated arXiv ID.
6. If validation returns `action: ask_user_to_choose`, stop and ask which one to analyze. detecting a conflict and then continuing is a failure.
7. For a user's first real reading project, propose `plan-starter-project` before `bootstrap-reading-project` so they can review the workspace path, artifact directory, explicit paper inputs, and generated manifest path before writes.
8. After bootstrap or Reading Report export, report Evidence Triage before interpreting dependency output. Name the triage status, supported local chains, candidate starting point, external blockers, and next actions. Do not treat empty dependencies as evidence that no mathematical dependencies exist.
9. If Evidence Triage reports external blockers, use `workspace_search_external_reference` to gather scholarly metadata candidates. Report confidence, provider evidence, ambiguity, and boundaries before applying anything. Use `workspace_resolve_external_reference_candidate` only for a selected candidate, or `workspace_resolve_external_reference` only with a confirmed arXiv ID, local PDF, DOI, URL, or published metadata. Then call `workspace_list_external_reference_resolutions`, `workspace_list_external_reference_searches`, or export a Reading Report to show whether each target is `resolved_imported`, `resolved_not_imported`, `failed_import`, ambiguous, or unavailable.

For local LaTeX, supply the main `.tex` file, such as
`tests/fixtures/workspace/paper_a/main.tex`, rather than its directory. MCP starter
inputs use `kind: local_tex` and `path` pointing to that file. Inspect the running
server's tools/schema before choosing a workflow. In v1.2.2,
starter planning performs read-only file preflight and does not open a database
or create directories; `ready` means input preflight passed, not successful parsing
or import. Bootstrap writes the workspace and artifacts and actually imports the
inputs. Historical/published builds may behave differently: disclose their actual
capability and side effects before calling them.

Use command-first CLI syntax, checking the named command's `--help`. Most
workspace commands use flags; `get-dependency-reading WORKSPACE PAPER_ID`,
`discover-doi DOI`, `add-doi-paper WORKSPACE DOI`, and
`import-doi-candidate WORKSPACE DOI CANDIDATE_ID --confirm` use positional
arguments. Do not carry `--workspace`/`--paper-id` onto those positional commands.
For example
`papergraph-mcp get-paper-map --workspace '<WORKSPACE>' --paper-id 'local:example-a'`.
Replace placeholders before execution and use the block for the user's shell.
Quote Windows paths with spaces using PowerShell single quotes (double embedded
apostrophes); POSIX shell quoting is separate. Checkpoint `target_kind` is
`result_id`, not `result`; obtain the other supported enum values from the live
schema. For `workspace_list_results`, the current schema exposes `limit` 1..100
(default 50) and nonnegative `offset` (default 0). Read successive pages in a stable
workspace until an empty/short page; a single response is not necessarily complete.

For proof-local citations and bibliography identity, inspect result/proof IDs and
source spans. TeX spans use offsets into their named original file; a cross-file
body has ordered fragments. BibTeX evidence must point to the parsed top-level
entry, not a similar key inside a comment or field. A citation supports an import
candidate, not an inferred mathematical dependency or proof verification, and
does not authorize external downloads.

For a published DOI, do not pass it to an arXiv loader or claim metadata is an imported paper. Explain the supported inputs: arXiv source, local LaTeX, or a local born-digital PDF. Identify an unambiguous legally accessible full-text source, or ask for the user's local PDF; never bypass a paywall. A root paper requested by the user is distinct from newly discovered external references, which still require a reviewable import plan before downloads.

For servers advertising `discover_doi_paper`, use it to find
exact DOI metadata/body candidates without downloading. Review access reports,
provider outcomes and reported versions. When the user's reading policy allows
automatic loading of a requested root, use `workspace_add_doi_paper`: it imports
only when one exact-identity public PDF candidate is eligible. For multiple
candidates ask the user to select, then use `workspace_import_doi_candidate` with
`confirmed=true`. Report actual import state and provenance. Never treat this as
permission for recursive external-reference downloads. These tools are available in v1.2.2; historical versions may not provide them.

If available, `workspace_get_dependency_reading` lists source-backed main-result
candidates without silently choosing one. Pass a user-selected target to separate
statement references, direct/recursive proof-local evidence, reading order and
external import plans. Check `order_status` before presenting `bottom_up` as a
local prerequisite order; cycles block ordering, and unknown/external prerequisites
remain outside it. Paper Map/queue exploration routes are not prerequisite orders.

For PDF papers, use `result_count`/`evidence_counts` and `import_state`; old
theorem/citation counters describe the LaTeX statement graph. Keep
`provider_metadata` display titles distinct from extracted PDF contents. Inspect
`proof_entry` for explicit author-declared introductory correspondence: a
corresponding proof keeps its original result owner and is not a verified
mathematical equivalence. Ambiguous/missing/cyclic/bounded entries stay unresolved;
do not silently choose a target or present their blocked order as complete.

Interpret `dependency_extraction_basis` as the legacy statement graph only, not the whole server's capabilities. Inspect `dependency_capabilities` when available. For proof questions use `workspace_get_proof_dependencies`, `workspace_get_result_reading_path`, and source-backed reading context. Neither statement refs nor proof-local evidence establish complete mathematical dependency coverage; empty output does not prove independence.

### What is missing

Run read-only detection when the host permits it:

```text
python scripts/check_onboarding.py
```

Use its facts for `git`, `uv`, and `uvx`; also detect the active MCP client without mutation. Infer the client only from reliable host or executable evidence. If it remains ambiguous, ask one concise question: “Which MCP client should I configure?”

The default pinned PyPI launch requires `uv` and `uvx`, index access, and no Git
or checkout. PyPI v1.2.2 has passed [public-byte and Git-free official-index acceptance](../../../docs/reference/v1.2.2-publication.md).
Current main records `PyPI publication_verified=true`; immutable R/tag/package
files retain their historical prepared-state snapshot. GitHub Release public
assets are verified against the same approved PyPI bytes; see the publication
record for source R and distribution hashes. The checker defaults to `pypi`;
`--install-source pypi`
is also explicit. Do not install Git solely for a PyPI consumer. Missing
repository/Git context is separate from index readiness. Doctor recommends the
PyPI version pin and reports optional Git source separately; it does not verify
publication. Prior [v1.2.1 index acceptance](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/38837645223)
applies only to that immutable version.

The optional Git-source launch requires Git as well as `uv` and `uvx`. Inspect
that route with `python scripts/check_onboarding.py --install-source git`.
This default check performs no remote tag verification and must keep Git
`publication_verified=false`, even when every command is available. To verify
publication explicitly, add `--verify-git-release --expected-source-commit SHA`,
using the reviewed 40-character package source commit from release evidence.
That read-only network check must find the exact version tag and match its
peeled target to the expected source before `ready_for_smoke_test` can be true.
Missing tags, network failures and target conflicts remain unverified. Add
`--smoke-test` to this verified route to test launch. An exact development Git
commit installation is a separate capability check and does not verify a tag.
If Git is missing, explain that route's prerequisite and stop before claiming
Git-source readiness; do not misdiagnose it as an API-key or MCP handshake problem.
Installing Git needs the user's installation approval too.

After selecting the client, read [references/client-configuration.md](references/client-configuration.md) completely and use only its matching verified recipe. State the detected facts, proposed next mutation, and the next required approval.

There are three separate approval boundaries:

1. **install approval:** if `uv` or `uvx` is missing, show the official platform-specific installer source and command, explain that `uvx` provides the reproducible launch, and ask before running it. Never reinstall or upgrade an existing installation automatically. Verify both `uv --version` and `uvx --version`; if either fails, stop before configuration.
2. **configuration approval:** show the exact client change and ask before a native command or any edit outside this repository. For file-based configuration, parse first, preserve unrelated servers, and create a timestamped adjacent backup. If parsing fails, stop and show the error. If safe mutation is unavailable, provide the minimal snippet and exact placement guidance instead.
3. **restart approval:** after configuration and launch validation, ask before controlling or restarting the client. If control is unavailable or permission is declined, provide one direct manual restart instruction.

The recipes below pin the published 1.2.2 package. Before installation, run the
read-only checker and consult the version-specific official-index acceptance
record above. If `publication_verified` is false, report that ordinary PyPI launch is blocked;
do not run the new recipe or silently substitute a mutable Git branch.
Verify the exact `v1.2.2` tag before using the optional Git-source recipe.
The Git recipe uses `git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.2`
as `--from`; do not substitute this for the default PyPI route.

An explicitly requested development test is separate: use the requested checkout's
locked environment or install its built wheel in a separate environment, then
launch that exact interpreter. Record CLI/MCP version, interpreter,
`doctor.build_identity` (source commit, tracked changes, source-tree digest) and
artifact hashes. A dirty build's commit is its base; unknown provenance remains
unknown. Version equality does not establish publication. Keep active client
registration intact. Switching installation sources requires configuration
approval and a backup; never invent a release/tag.

For PDF reading, surface `text_coverage` and unverified statement/proof completeness.
Use its continuation-source locator before interpreting truncated text. Follow
`source_reading` / `workspace_read_source_blocks` and its `next` handle for bounded
raw source reading (limit 1..50); source-slice `context` is 0..5. Raw blocks do
not assert proof ownership. New PDF proof evidence is limited to the first
physical line carrying an explicit proof heading. It does not automatically
join later lines or blocks or use their QED to establish ownership. An unnamed
Proof heading requires a directly preceding result span; intervening
unattributed source text leaves the owner unknown, unless the heading explicitly
names one unique result. The complete heading must name a single goal; compound,
alternative or unsupported goals stay unowned and never use proximity fallback.
Heading goals are not proof-body references. Boundaries respect nested brackets
and quotations; internal punctuation cannot open the body. Unbalanced structures
or unsupported heading syntax keep body references unknown. Bibliography entry evidence remains
accessible by ID while raw navigation returns its original container once. The first
marker clips that line; an ambiguous marker mention stops without certifying
closure. Fragment offsets are block-relative; the bbox identifies the raw
container. `automatic_ownership_policy` distinguishes this policy from legacy
stored excerpts, which remain unverified and unchanged until an explicitly
chosen reimport. Long-proof late references stay unknown; offer raw source for
review without promoting it to dependency evidence. For a selected dependency target use `detail: compact`
to omit repeated bodies/catalogs and follow `full_evidence` for original records.
Use `blocked_groups` / unique target counts for display; legacy `blocked_count`
counts records and original `blocked_ids` remain valid. Adjacent
context is not additional proof evidence, and delayed proof ownership remains
unresolved unless supported. Author `partial_overlap` is not full-list equivalence.

Never request credentials, upload papers, guess the identity of ambiguous references, recursively import newly discovered literature, bypass paywalls, or place a workspace database inside the Git repository. When a reference trail reaches an old paper with no electronic source, a metadata-only record, a paywalled target, or conflicting candidates, explain that PaperGraph reached a boundary and needs a user-supplied source or selection.

### What changed

Only after actions occur, list the executable version checks, the PaperGraph entry added or confirmed, the validation result, and any backup path. Configuration success requires the pinned command below to exit successfully with version `1.2.2`; file presence alone is insufficient:

```text
uvx --from papergraph-mcp==1.2.2 papergraph-mcp --version
```

Also validate the pinned diagnostics command:

```text
uvx --from papergraph-mcp==1.2.2 papergraph-mcp doctor
```

The expected output is:

```text
papergraph-mcp 1.2.2
```

Before restart, say “launch command validated”; never say “client has loaded the PaperGraph tools.” Tool loading can be confirmed only after the restarted client discovers the server.

### What to do now

Request restart approval or give the client-specific manual restart instruction. Remind the user that future conversations can use the reusable prompt. Stop after this instruction: do not persist setup state, create a handoff file, schedule work, or imply an automatic continuation.

## Failure branches

- If install approval is declined, change nothing, retain the reusable prompt, and give the official `uv` installation URL.
- If `uv` installation or either executable check fails, report the failing check and do not configure a client.
- If the client remains ambiguous, ask for its name before showing configuration; do not read the client reference or show generic JSON until the client is selected.
- If the identified client is unsupported or the user explicitly chooses a generic route, show the generic JSON entry, ask for its official documentation, and never guess a path.
- If the configuration is already equivalent, do not rewrite it; validate the pinned launch command and continue to restart guidance.
- If an existing `papergraph` entry differs, show the difference and ask before replacing only that entry.
- If configuration parsing fails, leave the file unchanged and report the exact error.
- If the launch check fails, keep any valid configuration, report setup as incomplete, and do not claim readiness.
- If restart is unavailable or declined, give the manual instruction and stop without persisted state or continuation.
