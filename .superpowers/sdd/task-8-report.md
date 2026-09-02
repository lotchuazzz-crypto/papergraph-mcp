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
