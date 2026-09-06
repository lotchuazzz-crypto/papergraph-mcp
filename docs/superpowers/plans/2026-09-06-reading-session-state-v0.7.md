# Reading Session State v0.7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent Reading Session State to PaperGraph workspaces, MCP tools, and CLI commands.

**Architecture:** Extend SQLite schema from version 3 to 4 with three session tables. Add focused `Workspace` methods for sessions, checkpoints, notes, and recovery summaries; expose them through thin MCP wrappers and JSON CLI commands.

**Tech Stack:** Python 3.10+, SQLite, argparse, pytest, existing PaperGraph workspace and server modules.

## Global Constraints

- Do not generate theorem explanations, proof strategies, symbol tables, or proof-gap fillings.
- Do not rank main results or resolve external dependencies automatically.
- Do not add new runtime dependencies.
- Commands print only JSON to stdout.
- Expected workspace and input errors use the existing CLI JSON error envelope and nonzero exit behavior.
- Every production behavior starts with a failing test.
- Do not use subagents for this implementation.

---

## File Structure

- `src/papergraph/workspace.py`: schema v4 migration, table validation, session ID helpers, workspace session methods.
- `src/papergraph/server.py`: MCP wrappers and argparse commands.
- `tests/test_workspace_reading_sessions.py`: direct workspace API and migration coverage.
- `tests/test_workspace_reading_sessions_server.py`: MCP wrapper coverage.
- `tests/test_cli_reading_sessions.py`: CLI command and JSON error coverage.
- `tests/test_onboarding.py` and README tests: version/release surface updates.
- `README.md`, `pyproject.toml`, `uv.lock`: v0.7.0 release surfaces.

## Task 1: Schema v4 and Workspace Session Core

**Files:**
- Modify: `src/papergraph/workspace.py`
- Create: `tests/test_workspace_reading_sessions.py`

**Interfaces:**
- Produces: `Workspace.create_reading_session(paper_id, label=None, target_result_id=None) -> dict`
- Produces: `Workspace.list_reading_sessions(paper_id=None, status=None) -> list[dict]`
- Produces: `Workspace.get_reading_session(session_id) -> dict`

- [ ] **Step 1: Write failing schema and create tests**

Add tests asserting `SCHEMA_VERSION == 4`, the three new tables exist, a v3 workspace migrates to v4, and `create_reading_session()` returns an active session with zero counts.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspace_reading_sessions.py::test_schema_v4_initializes_reading_session_tables tests/test_workspace_reading_sessions.py::test_create_reading_session_returns_active_session -v`

Expected: FAIL because `SCHEMA_VERSION` is still `3` and `Workspace.create_reading_session` does not exist.

- [ ] **Step 3: Implement schema v4 and session creation**

In `workspace.py`, add `_READING_SESSION_SCHEMA_SQL`, include required tables and column sets, migrate v3 to v4, and add `create_reading_session`, `list_reading_sessions`, and `get_reading_session`.

Session IDs use `session:<slug>:<YYYYMMDDHHMMSS>` and append `-2`, `-3` on collision. Use existing UTC timestamp style from the workspace module.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_workspace_reading_sessions.py -v`

Expected: PASS for schema/session tests added in this task.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/papergraph/workspace.py tests/test_workspace_reading_sessions.py
git commit -m "feat: add reading session workspace state"
```

## Task 2: Checkpoints, Notes, and Session Summary

**Files:**
- Modify: `src/papergraph/workspace.py`
- Modify: `tests/test_workspace_reading_sessions.py`

**Interfaces:**
- Produces: `Workspace.record_reading_checkpoint(session_id, target_kind, target_id, status, summary="", evidence=None) -> dict`
- Produces: `Workspace.add_reading_note(session_id, text, note_type="note", target_kind=None, target_id=None) -> dict`
- Produces: `Workspace.export_reading_session_summary(session_id) -> dict`

- [ ] **Step 1: Write failing checkpoint and summary tests**

Add tests for creating and updating a unique checkpoint, rejecting invalid status/kind/unknown result IDs, adding a question note, and exporting progress counts, blocked targets, open questions, latest notes, and next actions.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspace_reading_sessions.py::test_record_reading_checkpoint_updates_unique_target tests/test_workspace_reading_sessions.py::test_export_reading_session_summary_reports_recovery_state -v`

Expected: FAIL because the checkpoint, note, and summary methods do not exist.

- [ ] **Step 3: Implement checkpoint, note, and summary methods**

Add validators for session status, target kind, checkpoint status, note type, non-empty text, and JSON-serializable evidence. Update `reading_sessions.updated_at` whenever a checkpoint or note changes.

Summary output must include `source_policy` from the existing Reading Bridge base policy and deterministic `next_actions`:

- `review_blocked_targets`
- `continue_queued_targets`
- `review_target_result`
- `answer_or_retire_open_questions`

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_workspace_reading_sessions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/papergraph/workspace.py tests/test_workspace_reading_sessions.py
git commit -m "feat: track reading checkpoints and notes"
```

## Task 3: MCP Tools

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_workspace_reading_sessions_server.py`

**Interfaces:**
- Produces MCP wrappers named:
  - `workspace_create_reading_session`
  - `workspace_list_reading_sessions`
  - `workspace_get_reading_session`
  - `workspace_record_reading_checkpoint`
  - `workspace_add_reading_note`
  - `workspace_export_reading_session_summary`

- [ ] **Step 1: Write failing MCP wrapper tests**

Add tests that open a workspace, import a small PDF, create a session, record a reviewed result checkpoint, add a question, export a summary, and verify missing workspace/errors become `ToolError`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspace_reading_sessions_server.py -v`

Expected: FAIL because server wrappers are missing.

- [ ] **Step 3: Implement MCP wrappers**

Follow the existing workspace wrapper pattern in `server.py`: decorate with `@mcp.tool()` and `@_serialized_workspace_tool`, call `require_workspace()`, and translate `_WORKSPACE_TOOL_ERRORS` to `ToolError`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_workspace_reading_sessions_server.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/papergraph/server.py tests/test_workspace_reading_sessions_server.py
git commit -m "feat: expose reading session mcp tools"
```

## Task 4: CLI Commands

**Files:**
- Modify: `src/papergraph/server.py`
- Create: `tests/test_cli_reading_sessions.py`

**Interfaces:**
- Produces CLI subcommands:
  - `create-reading-session`
  - `list-reading-sessions`
  - `get-reading-session`
  - `record-reading-checkpoint`
  - `add-reading-note`
  - `export-reading-session-summary`

- [ ] **Step 1: Write failing CLI tests**

Add tests that create a PDF-backed workspace and exercise every command through `server.main([...])`, parsing stdout as JSON. Add one malformed `--evidence-json` test expecting `SystemExit(1)` and the existing error envelope.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_reading_sessions.py -v`

Expected: FAIL because argparse commands are missing.

- [ ] **Step 3: Implement CLI commands**

Add subparsers near the Reading Bridge CLI commands. Use `_run_workspace_json_command` and `_print_json_error` style already present in `server.py`. Parse `--evidence-json` with `json.loads`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_cli_reading_sessions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/papergraph/server.py tests/test_cli_reading_sessions.py
git commit -m "feat: add reading session cli commands"
```

## Task 5: Docs and v0.7.0 Release Surfaces

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_onboarding.py`
- Modify: version-sensitive tests discovered by `rg "0\\.6\\.1|v0\\.6\\.1"`

**Interfaces:**
- Produces: documented Reading Session workflow and `papergraph-mcp 0.7.0` version surfaces.

- [ ] **Step 1: Write failing docs/release tests**

Update tests to expect `0.7.0` / `v0.7.0` and README text for `create-reading-session`, `record-reading-checkpoint`, `add-reading-note`, and `export-reading-session-summary`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding.py tests/test_cli_reading_sessions.py -v`

Expected: FAIL until docs and version surfaces are updated.

- [ ] **Step 3: Update docs and version files**

Update README intro, tool table, Reading Bridge adjacent workflow section, CLI examples, `pyproject.toml`, and `uv.lock`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_onboarding.py tests/test_cli_reading_sessions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md pyproject.toml uv.lock tests
git commit -m "docs: prepare v0.7.0 release"
```

## Task 6: Full Verification, PR, and Release

**Files:**
- No source changes expected unless verification finds issues.

- [ ] **Step 1: Run full suite with project-local temp**

Run:

```powershell
$env:TMP = (Resolve-Path '.').Path + '\.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
uv run pytest
```

Expected: all tests pass with one skipped test.

- [ ] **Step 2: Inspect diff and status**

Run: `git status --short --branch` and `git log --oneline --decorate -8`.

- [ ] **Step 3: Push branch and create PR**

Run: `git push -u origin feature/v0.7-reading-sessions`.

Create a PR targeting `main` with a summary of session state, MCP/CLI commands,
and verification evidence.

- [ ] **Step 4: After PR checks pass, merge and tag**

After GitHub checks pass, merge the PR, update local main, tag `v0.7.0`, and push
the tag.

- [ ] **Step 5: Verify pinned install**

Run:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.7.0 papergraph-mcp --version
```

Expected output: `papergraph-mcp 0.7.0`.

- [ ] **Step 6: Publish GitHub Release**

Create GitHub Release `PaperGraph MCP v0.7.0` for tag `v0.7.0` with release
notes covering Reading Session State and verification evidence.

## Self-Review

- Spec coverage: schema, workspace methods, MCP wrappers, CLI commands, docs,
  tests, PR, and release are all mapped to tasks.
- Placeholder scan: no `TBD`, `TODO`, or ambiguous follow-up placeholders remain.
- Type consistency: method names and CLI commands match the design document.
