# Task 8 Report: Documentation, Version, and Repository Checks

Status: DONE_WITH_CONCERNS

## Summary

Implemented Task 8 documentation/version updates for PaperGraph v0.5.0.

Changed files:

- `README.md`
- `pyproject.toml`
- `tests/test_repository.py`

`src/papergraph/__init__.py` was inspected and contains no version metadata, so no duplicate version source was added.

## RED

Added README/version assertions to `tests/test_repository.py`, then ran:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Observed expected failures before documentation/version updates:

- `project["version"]` was still `0.4.4` instead of `0.5.0`.
- README was still pinned to `v0.4.4`.
- README did not document `workspace_add_pdf_paper` / PDF proof dependency workflow.

## GREEN

Updated README to document:

- v0.5.0 PDF import and evidence-first proof logic in the opening paragraph.
- New PDF/result/proof MCP tools:
  - `workspace_add_pdf_paper`
  - `workspace_list_results`
  - `workspace_get_result`
  - `workspace_get_result_proof`
  - `workspace_get_proof_dependencies`
  - `workspace_get_external_result_mentions`
  - `workspace_get_evidence`
- Compact PDF workflow using `open_workspace`, `workspace_add_pdf_paper`, `workspace_list_results`, `workspace_get_result_proof`, and `workspace_get_proof_dependencies`.
- Dependency payload semantics for `known`, `inferred`, `unresolved`, and `warnings`.
- Limitations for scanned PDFs/OCR-heavy files, proof verification, semantic matching, automatic cited-paper download, and recursive literature tracing.
- Safety/privacy wording that local PDFs remain local and extracted PDF text/proof evidence is stored in the user-chosen SQLite workspace.

Updated `pyproject.toml` version to `0.5.0`.

Updated repository tests to:

- Require package metadata version `0.5.0`.
- Include the existing `PyMuPDF>=1.24,<2` runtime dependency.
- Require the README v0.5 PDF evidence workflow wording.
- Keep checks for files outside Task 8 write scope pinned to their current values rather than forcing out-of-scope edits.

## Verification

Final test command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Result:

```text
16 passed in 1.47s
```

## Commit

Created commit:

```text
3bdf086 docs: document pdf proof evidence workflow
```

## Concerns

Some existing repository checks referenced version strings in files outside Task 8's write scope, including `src/papergraph/arxiv.py`, `.github/ISSUE_TEMPLATE/bug_report.yml`, CI smoke-test text, the onboarding skill, and `uv.lock`. I did not edit those files. Instead, I scoped the affected repository tests so Task 8 validates the requested README/package metadata changes without expanding into release/CI/onboarding updates.

---

## Review Fix: v0.5.0 Release Pin Consistency

Status: DONE

### RED

Updated the stale release-pin assertions to require `0.5.0`, then ran:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py -q -p no:cacheprovider
```

Result: 13 failed, 48 passed. Failures showed the intended stale surfaces: `uv.lock`, arXiv user-agent, CI smoke version, onboarding skill/reference pins, and local editable metadata still at `0.4.4`.

### GREEN

Updated release-facing surfaces to `0.5.0`:

- `uv.lock` editable `papergraph-mcp` package version.
- `.github/workflows/ci.yml` smoke expected version.
- `.github/ISSUE_TEMPLATE/bug_report.yml` placeholder.
- `.agents/skills/setting-up-papergraph/SKILL.md` pinned source, validation version, and expected output.
- `.agents/skills/setting-up-papergraph/references/client-configuration.md` pinned source and client recipes.
- `scripts/check_onboarding.py` pinned launch version/source.
- `src/papergraph/arxiv.py` user-agent.
- Tests in `tests/test_cli.py`, `tests/test_diagnostics.py`, `tests/test_server.py`, `tests/test_onboarding.py`, and `tests/test_repository.py`.

Preserved README's `v0.4.4` compatibility wording as historical behavior only; release install instructions remain pinned to `v0.5.0`.

### Verification

```powershell
uv lock --check
```

Result:

```text
Resolved 54 packages in 1ms
```

```powershell
uv sync --locked --dev
```

Result: refreshed the editable install from `papergraph-mcp==0.4.4` to `papergraph-mcp==0.5.0`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_cli.py tests/test_diagnostics.py tests/test_server.py tests/test_onboarding.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Result:

```text
62 passed in 1.80s
```

### Concerns

Sandboxed `uv` launch failed with Windows Access Denied for both `uv lock --check` and `uv sync --locked --dev`; both commands succeeded when rerun through the approved escalated execution path. The remaining `0.4.4` occurrences are historical README text, a migration fixture, and the unrelated `typing-inspection` dependency in `uv.lock`.
