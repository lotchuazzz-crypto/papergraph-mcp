# PaperGraph v1 Release Checklist

## Version Pins

- `pyproject.toml` reports `1.0.0`.
- `uv.lock` reports package version `1.0.0`.
- Runtime diagnostics report `version: 1.0.0` and `release_tag: v1.0.0`.
- Active install commands use `v1.0.0`.
- Historical specs and release history may keep old versions.

## Installation Validation

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.0.0 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.0.0 papergraph-mcp doctor
```

Keep workspace databases outside the Git repository.

## Documentation Review

- README opens with v1 stable positioning.
- README links the v1 core contract, first-workspace walkthrough, and example artifacts.
- README CLI examples use `papergraph-mcp <command> --workspace ...`.
- Evidence boundaries say PaperGraph does not verify proofs, infer hidden prerequisites, or perform semantic theorem matching.

## Test Commands

```powershell
uv run python scripts\check_onboarding.py
uv run pytest tests\test_repository.py tests\test_cli.py tests\test_diagnostics.py tests\test_server.py tests\test_onboarding.py tests\test_v1_readiness_docs.py -q -p no:cacheprovider --basetemp .pytest-tmp
uv run pytest -q -p no:cacheprovider --basetemp .pytest-tmp
```

Run the README CLI command sweep for documented commands:

```powershell
uv run papergraph-mcp <command> --help
```

## GitHub Release

- Merge the v1.0 PR into `main`.
- Create tag `v1.0.0` from the merge commit.
- Publish release notes that emphasize Paper Map, Reading Report, Cross-Paper Reading Plan, local SQLite workspaces, deterministic Markdown artifacts, MCP and CLI usage, and evidence boundaries.

## Post-v1 Scope

- PDF rendering.
- Global paper discovery.
- Semantic theorem equivalence.
- Notation or symbol indexing.
- Automatic external-paper import.
- Proof checking.
