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

1. If a repository directory already exists, run `git fetch --tags origin` before trusting local `origin/main`.
2. Verify `papergraph-mcp --version` and run `papergraph-mcp doctor` or call `get_environment_diagnostics`.
3. If a user provides both an arXiv ID and an arXiv URL, call `validate_arxiv_input` first.
4. Call `load_arxiv_paper` only when `validate_arxiv_input` returns `action: safe_to_load`.
5. If validation returns `action: ask_user_to_choose`, stop and ask which one to analyze. detecting a conflict and then continuing is a failure.

### What is missing

Run read-only detection when the host permits it:

```text
python scripts/check_onboarding.py
```

Use its facts for `git`, `uv`, and `uvx`; also detect the active MCP client without mutation. Infer the client only from reliable host or executable evidence. If it remains ambiguous, ask one concise question: “Which MCP client should I configure?”

After selecting the client, read [references/client-configuration.md](references/client-configuration.md) completely and use only its matching verified recipe. State the detected facts, proposed next mutation, and the next required approval.

There are three separate approval boundaries:

1. **install approval:** if `uv` or `uvx` is missing, show the official platform-specific installer source and command, explain that `uvx` provides the reproducible launch, and ask before running it. Never reinstall or upgrade an existing installation automatically. Verify both `uv --version` and `uvx --version`; if either fails, stop before configuration.
2. **configuration approval:** show the exact client change and ask before a native command or any edit outside this repository. For file-based configuration, parse first, preserve unrelated servers, and create a timestamped adjacent backup. If parsing fails, stop and show the error. If safe mutation is unavailable, provide the minimal snippet and exact placement guidance instead.
3. **restart approval:** after configuration and launch validation, ask before controlling or restarting the client. If control is unavailable or permission is declined, provide one direct manual restart instruction.

Use this immutable release source everywhere; never substitute a branch, a mutable default, or an unreleased revision:

```text
git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.3
```

Never request credentials, upload papers, or place a workspace database inside the Git repository.

### What changed

Only after actions occur, list the executable version checks, the PaperGraph entry added or confirmed, the validation result, and any backup path. Configuration success requires the pinned command below to exit successfully with version `0.4.3`; file presence alone is insufficient:

```text
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.3 papergraph-mcp --version
```

The expected output is:

```text
papergraph-mcp 0.4.3
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
