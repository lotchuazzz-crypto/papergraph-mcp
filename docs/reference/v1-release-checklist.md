# PaperGraph v1 Release Checklist

## Version Pins

- `pyproject.toml` reports `1.2.0`.
- `uv.lock` reports package version `1.2.0`.
- Runtime diagnostics report `version: 1.2.0` and `release_tag: v1.2.0`.
- Active install commands pin the available and publicly validated `v1.2.0` Git tag. Installation examples are updated separately after tag publication; the GitHub Release page is a distinct publication step.
- Historical specs and release history may keep old versions.

## Installation Validation

The tag commands below require an available Git tag. Before publishing a future
tag, build the wheel with `uv build` and test it in an isolated environment. Do
not claim an unpublished tag was installed.

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.0 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.0 papergraph-mcp doctor
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

- Merge the reviewed v1.2.0 preparation branch into `main` after all checks pass.
- Verify merge-commit CI, then create tag `v1.2.0` from that exact commit; never move an existing tag.
- Publish a formal GitHub release using an English introduction and Highlights, Compatibility, Verification and Install sections. Describe first use, DOI bodies and dependency reading with explicit coverage/identity boundaries.
- Existing recent releases have no uploaded assets; do not add a new distribution channel.
- After tag publication, verify the exact tag target and public pinned launch/version/diagnostics before updating active installation examples. Verify formal GitHub release flags and its tag separately after creating the release page.

## Post-v1 Scope

- PDF rendering.
- Global paper discovery.
- Semantic theorem equivalence.
- Notation or symbol indexing.
- Unlimited external-paper crawling (bounded expansion is available in v1.2.0).
- Proof checking.
