# Task 8 Report: PaperGraph v0.4.0 documentation and packaging

## RED

Command (with the repository-local uv cache):

```powershell
& 'C:\Users\Jonathan Lee\.local\bin\uv.exe' run pytest tests/test_repository.py -q -p no:cacheprovider
```

Result: **5 failed, 7 passed** in 0.17s. The new release-contract assertions
correctly failed because the package and lockfile were still `0.3.1`, the CI
wheel-smoke assertion still expected `0.3.1`, and the README lacked the
v0.4.0 pinned source and workspace documentation.

## GREEN

Focused repository contract:

```powershell
& 'C:\Users\Jonathan Lee\.local\bin\uv.exe' run pytest tests/test_repository.py -q -p no:cacheprovider
```

Result: **12 passed** in 0.08s.

Complete deterministic suite:

```powershell
& 'C:\Users\Jonathan Lee\.local\bin\uv.exe' run pytest -q -p no:cacheprovider
```

Result: **207 passed, 1 skipped** in 9.92s.

`uv lock` completed successfully and updated `papergraph-mcp` from v0.3.1 to
v0.4.0. The invocation used `UV_CACHE_DIR` pointed at the ignored
repository-local `.uv-cache` because the default user cache was inaccessible.

## Delivered scope

- Version, lockfile, CLI expectation, and CI wheel-smoke expectation are v0.4.0.
- README documents all eight workspace tools with exact signatures and return
  summaries, SQLite persistence, explicit citation evidence and unresolved
  examples, a reproducible three-fixture walkthrough, path/backup/privacy
  guidance, and semantic-matching/automatic-download limitations.
- `tests/test_repository.py` now asserts the v0.4.0 release contract, runtime
  `pybtex` dependency, and presence of all eight workspace tool names.

## Concerns

- No tag, release, push, or publication was performed.
- The three-paper walkthrough intentionally uses tracked synthetic fixtures;
  callers must substitute their checkout's absolute paths and a controlled
  temporary SQLite path.

## Review correction: local-fixture citation targets

### RED

The new execution-level test ran the README's local fixture sequence against a
temporary SQLite database. It confirmed three local theorem IDs and showed that
the `paper-b` citation has `cited_arxiv_id` `2401.12346`,
`target_paper_id` `None`, and `resolution_status` `resolved_candidate`; the
incoming query for `local:paper-b` is empty. Before the README correction, the
test failed at its documentation assertion because the walkthrough incorrectly
claimed a resolved `local:paper-b` target and an incoming local-cycle result.

### GREEN

Focused command:

```powershell
& 'C:\Users\Jonathan Lee\.local\bin\uv.exe' run pytest tests/test_readme_local_workspace_walkthrough.py tests/test_repository.py -q -p no:cacheprovider
```

Result: **13 passed** in 1.17s.

Full command:

```powershell
& 'C:\Users\Jonathan Lee\.local\bin\uv.exe' run pytest -q -p no:cacheprovider
```

Result: **208 passed, 1 skipped** in 10.52s.

The README now documents cross-paper theorem search plus explicit outgoing
citation evidence for the local fixtures. It explicitly states that only a
matching arXiv paper imported through `workspace_add_arxiv_paper` creates a
stored citation target; it makes no live-download claim.
