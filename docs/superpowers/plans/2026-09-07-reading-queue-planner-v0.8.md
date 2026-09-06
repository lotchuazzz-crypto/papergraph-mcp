# Reading Queue Planner v0.8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent Reading Queue Planner support that converts existing result reading-path evidence into ordered queue items and can apply those items to v0.7 reading sessions.

**Architecture:** Advance the SQLite workspace schema to v5 with `reading_queues` and `reading_queue_items`. Build queue items inside `Workspace` from existing `get_result_reading_path`, `get_result_proof`, and `record_reading_checkpoint` APIs, then expose the same behavior through MCP wrappers and JSON CLI commands.

**Tech Stack:** Python 3.10+, SQLite, pytest, existing PaperGraph MCP server and argparse CLI.

## Global Constraints

- The workspace schema advances from version 4 to version 5.
- Queue statuses are exactly `active` and `archived`.
- Queue item target kinds are exactly `result_id`, `proof_id`, `span_id`, `external_stop`, and `unresolved_stop`.
- Queue item priorities are exactly `required`, `recommended`, and `caution`.
- Applying a queue to a session may only use checkpoint statuses `queued`, `reviewed`, `blocked`, or `skipped`; default is `queued`.
- The planner must not generate mathematical explanations, verify proofs, perform semantic ranking, or automatically import citations.
- The active release version becomes `0.8.0` and release pins become `v0.8.0`.

---

## File Structure

- `src/papergraph/workspace.py`: schema v5 migration, queue persistence, queue planner, queue-to-session application.
- `src/papergraph/server.py`: MCP wrappers and CLI commands.
- `tests/test_workspace_reading_queue.py`: workspace-level schema, planner, listing, retrieval, and apply tests.
- `tests/test_workspace_reading_queue_server.py`: MCP wrapper success and error conversion tests.
- `tests/test_cli_reading_queue.py`: JSON CLI round-trip tests.
- `tests/test_workspace.py`, `tests/test_workspace_evidence.py`, `tests/test_workspace_server.py`: schema-version expectation updates.
- `tests/test_repository.py`, `tests/test_onboarding.py`: repository metadata and version pin expectation updates.
- `README.md`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `scripts/check_onboarding.py`, `src/papergraph/arxiv.py`, `.agents/skills/setting-up-papergraph/SKILL.md`, `.agents/skills/setting-up-papergraph/references/client-configuration.md`: v0.8.0 release surface updates.

---

### Task 1: Workspace Queue Schema And Planner

**Files:**
- Modify: `src/papergraph/workspace.py`
- Create: `tests/test_workspace_reading_queue.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/test_workspace_evidence.py`
- Modify: `tests/test_workspace_server.py`

**Interfaces:**
- Consumes: `Workspace.get_result_reading_path(result_id: str, recursive: bool = True) -> dict`, `Workspace.get_result_proof(result_id: str) -> dict`, `Workspace.record_reading_checkpoint(...) -> dict`
- Produces: `Workspace.create_reading_queue(result_id: str, label: str | None = None, recursive: bool = True) -> dict`, `Workspace.list_reading_queues(paper_id: str | None = None, status: str | None = None) -> list[dict]`, `Workspace.get_reading_queue(queue_id: str) -> dict`, `Workspace.apply_reading_queue_to_session(queue_id: str, session_id: str, status: str = "queued") -> dict`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/test_workspace_reading_queue.py` with tests that build small PDF workspaces, assert schema v5 queue tables exist, migrate a v4 database by dropping future tables and setting schema `4`, create a queue for a result, verify deterministic item order and duplicate suppression, list/get queues, apply a queue to a reading session, and reject cross-paper application.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace_reading_queue.py -v
```

Expected: fail because `Workspace` has no reading queue methods and schema v5 tables are missing.

- [ ] **Step 3: Implement schema v5 and workspace queue methods**

In `src/papergraph/workspace.py`, set `SCHEMA_VERSION = 5`, add queue constants, extend `_REQUIRED_TABLES` and `_REQUIRED_TABLE_COLUMNS`, add `_READING_QUEUE_SCHEMA_SQL`, add `_migrate_v4_to_v5`, call it from `_ensure_schema`, and implement the public queue methods plus private payload/id/item helpers.

- [ ] **Step 4: Run workspace queue tests to verify GREEN**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace_reading_queue.py -v
```

Expected: pass.

- [ ] **Step 5: Update existing schema expectation tests**

Update existing tests that assert schema version `4` or future schema `5` so current schema is `5` and future unsupported schema is `6`.

- [ ] **Step 6: Run schema-related tests**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace.py tests/test_workspace_evidence.py tests/test_workspace_server.py tests/test_workspace_reading_queue.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src/papergraph/workspace.py tests/test_workspace.py tests/test_workspace_evidence.py tests/test_workspace_server.py tests/test_workspace_reading_queue.py
git commit -m "feat: add reading queue workspace state"
```

---

### Task 2: MCP Reading Queue Tools

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_workspace_reading_queue_server.py`

**Interfaces:**
- Consumes: workspace methods from Task 1
- Produces: MCP wrappers `workspace_create_reading_queue`, `workspace_list_reading_queues`, `workspace_get_reading_queue`, `workspace_apply_reading_queue_to_session`

- [ ] **Step 1: Write failing MCP wrapper tests**

Create `tests/test_workspace_reading_queue_server.py` with tests that open a workspace, import a small PDF fixture, create/get/list/apply a queue through server wrappers, and verify missing workspace or invalid IDs raise `ToolError`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace_reading_queue_server.py -v
```

Expected: fail because MCP wrappers are missing.

- [ ] **Step 3: Implement MCP wrappers**

Add wrapper functions near the existing reading-session tools in `src/papergraph/server.py`. Each wrapper uses `require_workspace()` inside `_workspace_call` and forwards parameters to the workspace methods.

- [ ] **Step 4: Run MCP wrapper tests**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_workspace_reading_queue_server.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_workspace_reading_queue_server.py
git commit -m "feat: expose reading queue mcp tools"
```

---

### Task 3: CLI Reading Queue Commands

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_cli_reading_queue.py`

**Interfaces:**
- Consumes: workspace methods from Task 1
- Produces: commands `create-reading-queue`, `list-reading-queues`, `get-reading-queue`, `apply-reading-queue-to-session`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_reading_queue.py` with a JSON round-trip: create queue, list queues, get queue, create session, apply queue, and assert queued checkpoints appear in the session summary. Include an invalid ID test that verifies the existing JSON error envelope.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_cli_reading_queue.py -v
```

Expected: fail because CLI commands are missing.

- [ ] **Step 3: Implement CLI parsers and command handlers**

Add argparse subcommands in `build_parser()` and command branches in `main()` using `_workspace_json_command`, matching the existing reading-session command style.

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_cli_reading_queue.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_cli_reading_queue.py
git commit -m "feat: add reading queue cli commands"
```

---

### Task 4: v0.8.0 Documentation And Release Pins

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Modify: `scripts/check_onboarding.py`
- Modify: `src/papergraph/arxiv.py`
- Modify: `.agents/skills/setting-up-papergraph/SKILL.md`
- Modify: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: public MCP and CLI command names from Tasks 2 and 3
- Produces: README workflow and active version pins for v0.8.0

- [ ] **Step 1: Write/update documentation expectation tests**

Update tests so repository metadata expects `workspace_create_reading_queue`, `workspace_list_reading_queues`, `workspace_get_reading_queue`, `workspace_apply_reading_queue_to_session`, `create-reading-queue`, and `apply-reading-queue-to-session`. Update onboarding/version tests to expect `0.8.0`/`v0.8.0`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_repository.py tests/test_onboarding.py -v
```

Expected: fail until docs/version surfaces are updated.

- [ ] **Step 3: Update README and version pins**

Update README intro, feature list, tool list/table, quick-start pins, MCP config pins, and add a "Reading queue workflow" section. Update all active version pins from `0.7.0`/`v0.7.0` to `0.8.0`/`v0.8.0`, leaving historical release prose intact.

- [ ] **Step 4: Run documentation/version tests**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest tests/test_repository.py tests/test_onboarding.py tests/test_cli_reading_queue.py tests/test_workspace_reading_queue_server.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add README.md pyproject.toml uv.lock .github/workflows/ci.yml .github/ISSUE_TEMPLATE/bug_report.yml scripts/check_onboarding.py src/papergraph/arxiv.py .agents/skills/setting-up-papergraph/SKILL.md .agents/skills/setting-up-papergraph/references/client-configuration.md tests/test_repository.py tests/test_onboarding.py
git commit -m "docs: prepare v0.8.0 release"
```

---

### Task 5: Full Verification, PR, Merge, Tag, Release

**Files:**
- No source edits unless verification exposes a defect.

**Interfaces:**
- Consumes: all prior task outputs
- Produces: branch push, PR, main CI verification, `v0.8.0` tag, GitHub Release

- [ ] **Step 1: Run full local suite**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest
```

Expected: `386+ passed, 1 skipped`, exact count depends on new tests.

- [ ] **Step 2: Inspect git status and release pins**

Run:

```powershell
git status --short --branch
git log --oneline --decorate --max-count=12
rg -n "v0\.7\.0|0\.7\.0" README.md pyproject.toml uv.lock .github scripts src tests .agents/skills/setting-up-papergraph
```

Expected: clean worktree; remaining v0.7.0 references only in historical release prose/spec/plan text.

- [ ] **Step 3: Push feature branch and create PR**

Run:

```powershell
git push -u origin feature/v0.8-reading-queue
```

Then create a PR targeting `main` titled `Add Reading Queue Planner for v0.8.0` with summary and testing evidence. Prefer GitHub connector; fall back to GitHub REST using Git Credential Manager if connector permissions reject PR creation.

- [ ] **Step 4: Merge/publish after CI**

After PR or branch CI passes, merge to `main`. If PR creation is impossible because of GitHub integration/browser constraints, fast-forward `main` from the verified branch and record the deviation in the final report.

- [ ] **Step 5: Tag and release**

Create and push annotated `v0.8.0`, verify pinned install:

```powershell
git tag -a v0.8.0 -m "PaperGraph MCP v0.8.0"
git push origin v0.8.0
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.8.0 papergraph-mcp --version
```

Create GitHub Release `PaperGraph MCP v0.8.0` after tag install verifies.

---

## Plan Self-Review

- Spec coverage: schema, planner semantics, API, MCP, CLI, docs, tests, and release are covered by Tasks 1-5.
- Placeholder scan: no unfinished placeholders or undefined follow-up placeholders remain.
- Type consistency: queue method names, tool names, CLI command names, statuses, target kinds, and priorities match the spec.
