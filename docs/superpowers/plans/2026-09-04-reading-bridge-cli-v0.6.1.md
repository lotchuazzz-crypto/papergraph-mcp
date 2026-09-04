# Reading Bridge CLI v0.6.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add command-line JSON export commands for existing Reading Bridge workspace payloads and prepare the `0.6.1` release.

**Architecture:** Reuse existing `Workspace` methods from `src/papergraph/workspace.py` and add a thin CLI adapter in `src/papergraph/server.py`. The adapter opens a workspace per command, prints sorted pretty JSON, converts expected errors into a stable JSON envelope, and closes the workspace.

**Tech Stack:** Python 3.10+, argparse, SQLite-backed `Workspace`, pytest, uv, Hatchling.

## Global Constraints

- Do not change MCP tool signatures or existing Reading Bridge payload shapes.
- CLI export commands read an existing workspace; they do not import papers.
- Each CLI command prints only JSON to stdout.
- Successful commands exit `0`; expected workspace/input failures exit nonzero.
- Source-slice context remains an integer from `0` through `5`.
- `get-result-reading-path` defaults to recursive traversal; `--direct` sets `recursive=False`.
- Target release is `0.6.1` / `v0.6.1`.
- Do not use subagents.

---

### Task 1: Reading Bridge CLI Commands

**Files:**
- Modify: `src/papergraph/server.py`
- Test: `tests/test_cli_reading.py`

**Interfaces:**
- Consumes: `Workspace.open(path)`, `Workspace.export_reading_bundle(paper_id)`, `Workspace.export_result_reading_context(result_id)`, `Workspace.get_source_slice(span_id=None, result_id=None, proof_id=None, context=1)`, `Workspace.get_result_reading_path(result_id, recursive=True)`.
- Produces: CLI subcommands `export-reading-bundle`, `export-result-reading-context`, `get-source-slice`, and `get-result-reading-path`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_reading.py` with tests that build small PDF-backed workspaces, call `server.main([...])`, and assert JSON-only stdout for:

```python
server.main([
    "export-reading-bundle",
    "--workspace",
    str(workspace_path),
    "--paper-id",
    "local:paper",
])
```

```python
server.main([
    "export-result-reading-context",
    "--workspace",
    str(workspace_path),
    "--result-id",
    "local:paper::pdf:theorem:1.1",
])
```

```python
server.main([
    "get-source-slice",
    "--workspace",
    str(workspace_path),
    "--proof-id",
    "local:paper::proof:1",
    "--context",
    "1",
])
```

```python
server.main([
    "get-result-reading-path",
    "--workspace",
    str(workspace_path),
    "--result-id",
    "local:paper::pdf:theorem:1.3",
    "--direct",
])
```

Also test invalid selector usage:

```python
with pytest.raises(SystemExit) as caught:
    server.main(["get-source-slice", "--workspace", str(workspace_path)])
assert caught.value.code == 1
payload = json.loads(capsys.readouterr().out)
assert payload["status"] == "error"
assert payload["action"] == "inspect_error"
assert payload["command"] == "get-source-slice"
assert "Exactly one source slice selector" in payload["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_reading.py -q -p no:cacheprovider --basetemp .pytest-tmp`

Expected: FAIL because the new CLI subcommands are not registered.

- [ ] **Step 3: Implement CLI adapter**

In `src/papergraph/server.py`, add a helper:

```python
def _run_workspace_cli_command(command: str, workspace_path: str, callback) -> None:
    workspace = None
    try:
        workspace = Workspace.open(workspace_path)
        _print_json(callback(workspace))
    except _WORKSPACE_TOOL_ERRORS as exc:
        _print_json(
            {
                "status": "error",
                "action": "inspect_error",
                "command": command,
                "message": str(exc),
            }
        )
        raise SystemExit(1) from exc
    finally:
        if workspace is not None:
            workspace.close()
```

Register the four argparse subcommands and route them before `mcp.run()`:

```python
if args.command == "export-reading-bundle":
    _run_workspace_cli_command(
        args.command,
        args.workspace,
        lambda workspace: workspace.export_reading_bundle(args.paper_id),
    )
    return
```

Use analogous callbacks for the other three commands.

- [ ] **Step 4: Run focused CLI tests**

Run: `uv run pytest tests/test_cli_reading.py -q -p no:cacheprovider --basetemp .pytest-tmp`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/papergraph/server.py tests/test_cli_reading.py
git commit -m "feat: add reading bridge cli exports"
```

### Task 2: Documentation and Release Surfaces

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Modify: `src/papergraph/arxiv.py`
- Modify: `scripts/check_onboarding.py`
- Modify: `.agents/skills/setting-up-papergraph/SKILL.md`
- Modify: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Modify: version-sensitive tests in `tests/test_cli.py`, `tests/test_diagnostics.py`, `tests/test_onboarding.py`, `tests/test_repository.py`, and `tests/test_server.py`

**Interfaces:**
- Consumes: CLI commands from Task 1.
- Produces: release metadata consistently set to `0.6.1` / `v0.6.1` and README CLI examples.

- [ ] **Step 1: Write failing documentation/release tests**

Update tests so they expect `0.6.1` / `v0.6.1`. Extend `tests/test_repository.py::test_readme_is_a_version_pinned_launch_page_with_verified_demo` to assert README contains:

```python
assert "export-reading-bundle" in readme
assert "export-result-reading-context" in readme
assert "get-source-slice" in readme
assert "get-result-reading-path" in readme
assert "--workspace" in readme
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_onboarding.py tests/test_server.py -q -p no:cacheprovider --basetemp .pytest-tmp`

Expected: FAIL because release surfaces and README docs are still at `0.6.0` and lack CLI export examples.

- [ ] **Step 3: Update release surfaces and README**

Replace active release pins from `0.6.0` / `v0.6.0` to `0.6.1` / `v0.6.1` in the files listed above. Keep historical `v0.6.0` references only when explicitly describing history.

Add README commands under the Reading Bridge workflow:

```text
papergraph-mcp export-reading-bundle --workspace C:/Temp/papergraph-reading.sqlite3 --paper-id local:example
papergraph-mcp export-result-reading-context --workspace C:/Temp/papergraph-reading.sqlite3 --result-id local:example::pdf:theorem:1.1
papergraph-mcp get-source-slice --workspace C:/Temp/papergraph-reading.sqlite3 --proof-id local:example::proof:1 --context 1
papergraph-mcp get-result-reading-path --workspace C:/Temp/papergraph-reading.sqlite3 --result-id local:example::pdf:theorem:1.1
```

- [ ] **Step 4: Run release/documentation tests**

Run: `uv run pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_onboarding.py tests/test_server.py -q -p no:cacheprovider --basetemp .pytest-tmp`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add README.md pyproject.toml uv.lock .github/workflows/ci.yml .github/ISSUE_TEMPLATE/bug_report.yml src/papergraph/arxiv.py scripts/check_onboarding.py .agents/skills/setting-up-papergraph/SKILL.md .agents/skills/setting-up-papergraph/references/client-configuration.md tests/test_cli.py tests/test_diagnostics.py tests/test_onboarding.py tests/test_repository.py tests/test_server.py
git commit -m "docs: prepare v0.6.1 release"
```

### Task 3: Final Verification, PR, Merge, and Tag

**Files:**
- No code files unless verification finds a defect.

**Interfaces:**
- Consumes: all commits from Tasks 1 and 2.
- Produces: remote branch, PR, merged `main`, tag `v0.6.1`, and pinned install verification.

- [ ] **Step 1: Run full verification**

Run:

```powershell
uv run pytest -q -p no:cacheprovider --basetemp .pytest-tmp
git diff --check
uv build
```

Expected: all commands exit `0`; pytest reports the full suite with zero failures.

- [ ] **Step 2: Verify built wheel CLI**

Run:

```powershell
uv venv .release-smoke-venv
uv pip install --python .release-smoke-venv\Scripts\python.exe dist\papergraph_mcp-0.6.1-py3-none-any.whl
.release-smoke-venv\Scripts\papergraph-mcp.exe --version
```

Expected output:

```text
papergraph-mcp 0.6.1
```

- [ ] **Step 3: Clean temporary directories**

Safely delete only `.pytest-tmp` and `.release-smoke-venv` under the repository root.

- [ ] **Step 4: Push branch and create PR**

Run:

```powershell
git push -u origin feature/v0.6.1-reading-cli
```

Create a PR titled `Add Reading Bridge CLI exports for v0.6.1` with summary and testing evidence.

- [ ] **Step 5: Wait for PR CI**

Wait until all CI jobs for the PR head commit succeed. If a job fails, fetch logs, find root cause, write a failing test if needed, fix, verify, push, and wait again.

- [ ] **Step 6: Merge and verify main CI**

Merge through the available GitHub path. If direct PR merge is unavailable in tooling, fast-forward or squash-equivalent merge the reviewed branch into `main` only after PR CI is green, then push `main`. Wait for main CI to succeed.

- [ ] **Step 7: Tag and verify release pin**

Run:

```powershell
git tag -a v0.6.1 -m "PaperGraph MCP v0.6.1"
git push origin v0.6.1
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version
```

Expected output:

```text
papergraph-mcp 0.6.1
```

Do not create the tag until merged `main` CI succeeds.
