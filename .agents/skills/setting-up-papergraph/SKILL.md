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

For a published DOI, do not pass it to an arXiv loader or claim metadata is an imported paper. Explain the supported inputs: arXiv source, local LaTeX, or a local born-digital PDF. Identify an unambiguous legally accessible full-text source, or ask for the user's local PDF; never bypass a paywall. A root paper requested by the user is distinct from newly discovered external references, which still require a reviewable import plan before downloads.

For a local development server advertising `discover_doi_paper`, use it to find
exact DOI metadata/body candidates without downloading. Review access reports,
provider outcomes and reported versions. When the user's reading policy allows
automatic loading of a requested root, use `workspace_add_doi_paper`: it imports
only when one exact-identity public PDF candidate is eligible. For multiple
candidates ask the user to select, then use `workspace_import_doi_candidate` with
`confirmed=true`. Report actual import state and provenance. Never treat this as
permission for recursive external-reference downloads. Do not expect these
unreleased tools in the pinned v1.1.7 package.

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

The pinned Git-source launch requires Git as well as `uv` and `uvx`. If Git is missing, explain that prerequisite and stop before claiming launch readiness; do not misdiagnose it as an API-key or MCP handshake problem. Installing Git needs the user's installation approval too.

After selecting the client, read [references/client-configuration.md](references/client-configuration.md) completely and use only its matching verified recipe. State the detected facts, proposed next mutation, and the next required approval.

There are three separate approval boundaries:

1. **install approval:** if `uv` or `uvx` is missing, show the official platform-specific installer source and command, explain that `uvx` provides the reproducible launch, and ask before running it. Never reinstall or upgrade an existing installation automatically. Verify both `uv --version` and `uvx --version`; if either fails, stop before configuration.
2. **configuration approval:** show the exact client change and ask before a native command or any edit outside this repository. For file-based configuration, parse first, preserve unrelated servers, and create a timestamped adjacent backup. If parsing fails, stop and show the error. If safe mutation is unavailable, provide the minimal snippet and exact placement guidance instead.
3. **restart approval:** after configuration and launch validation, ask before controlling or restarting the client. If control is unavailable or permission is declined, provide one direct manual restart instruction.

For ordinary installation, use this immutable release source; never substitute a
branch, a mutable default, or an unreleased revision:

```text
git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.7
```

An explicitly requested candidate-development test is separate: the local
candidate is `1.2.0.dev0`, not a published release. Use the requested checkout's
locked development environment or install its built wheel in a separate environment,
then launch that exact interpreter. Check CLI version, `doctor.build_identity`
(source commit, tracked changes and source-tree digest), and MCP initialization
version. A dirty build's commit is its base; unknown build provenance is unknown.
The candidate's `recommended_source` still launches stable v1.1.7 and is labelled
`stable_release_not_running_candidate`; it cannot validate candidate features.
Keep the user's active MCP registration intact unless they explicitly authorize a
configuration change, and never invent a development release/tag.

For PDF reading, surface `text_coverage` and unverified statement/proof completeness.
Use its continuation-source locator before interpreting truncated text. Adjacent
context is not additional proof evidence, and delayed proof ownership remains
unresolved unless supported. Author `partial_overlap` is not full-list equivalence.

Never request credentials, upload papers, guess the identity of ambiguous references, recursively import newly discovered literature, bypass paywalls, or place a workspace database inside the Git repository. When a reference trail reaches an old paper with no electronic source, a metadata-only record, a paywalled target, or conflicting candidates, explain that PaperGraph reached a boundary and needs a user-supplied source or selection.

### What changed

Only after actions occur, list the executable version checks, the PaperGraph entry added or confirmed, the validation result, and any backup path. Configuration success requires the pinned command below to exit successfully with version `1.1.7`; file presence alone is insufficient:

```text
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.7 papergraph-mcp --version
```

Also validate the pinned diagnostics command:

```text
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.7 papergraph-mcp doctor
```

The expected output is:

```text
papergraph-mcp 1.1.7
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
