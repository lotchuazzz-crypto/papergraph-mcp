# PaperGraph v1 Release Checklist

## Version Pins

- `pyproject.toml` and `uv.lock` report prepared version `1.2.2`.
- Runtime diagnostics report `version: 1.2.2` and `release_tag: v1.2.2`; this does not verify tag availability or publication.
- Install recipes target fixed `1.2.2`, with `publication_verified=false` until its own official-index acceptance. [Prior 1.2.1 acceptance](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/38837645223) applies only to that immutable version.
- Historical specs and release history may keep old versions.

## Installation Validation

PyPI 1.2.2 is prepared, not published; ordinary launch stays blocked by the
publication guard. Test its reviewed wheel/sdist in isolated environments.
After official-index acceptance, prefer `uvx --from papergraph-mcp==1.2.2`.
The optional tag commands below require the exact source recorded in the
[1.2.2 release notes](v1.2.2-release-notes.md). Do not claim an unpublished tag
was installed or rebuild/re-upload prior frozen distributions.

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.2 papergraph-mcp --version
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.2 papergraph-mcp doctor
```

Keep workspace databases outside the Git repository.

## Documentation Review

- README opens with v1 stable positioning.
- README links the v1 core contract, first-workspace walkthrough, and example artifacts.
- README CLI examples identify each command's positional arguments or `--workspace` flags; check the named command's `--help`.
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

- v1.2.2 awaits independent acceptance. Bind exact source/artifact hashes in a
  separate configuration commit, then use the protected publishing workflow.
  Do not create its tag, dispatch publishing or mark publication verified during
  development. The following completed records describe historical v1.2.1.
- PR49 is merged at configuration commit `6375d95ba9caf78b03d61f8ccfc468766dae1316`; [main CI](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/38704231803) passed all seven jobs. Manual PyPI publication and official-index acceptance have completed.
- Tag `v1.2.1` and the [formal GitHub Release](https://github.com/lotchuazzz-crypto/papergraph-mcp/releases/tag/v1.2.1) are published. The tag was verified at immutable package source R, `d4c232efb4736eb37fad8975708abd773b0e90d7`, not the configuration merge or closeout commit; never move it. Release flags: draft=false, prerelease=false, no uploaded assets.
- Record the exact source identity and two Linux-built artifact hashes before updating the fixed publisher guards. Preserve same-run immutable artifact IDs, strict metadata/manifest/hash checks and the protected `pypi` human deployment review.
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
