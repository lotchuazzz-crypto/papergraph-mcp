# PaperGraph v0.3.1 Launch Readiness Design

## Goal

Prepare PaperGraph MCP for a public GitHub launch by making installation verifiable, repository health visible, first-time setup understandable, and outside contributions structured. This release improves presentation and delivery without changing parser, graph, local-paper, arXiv, archive, or cache semantics.

## Scope

v0.3.1 includes:

- A minimal command-line surface for `--help` and `--version`.
- Continuous integration on Windows and Linux with Python 3.10 and 3.12.
- A clean wheel build and installation smoke test.
- A launch-oriented README with a GitHub-based one-command entry point, generic stdio MCP configuration, tool reference, real arXiv demonstration, architecture overview, limitations, and contribution links.
- Repository metadata, contribution guidance, issue forms, and a pull-request template.
- Version and lockfile updates to `0.3.1`.

The release does not publish to PyPI or the MCP Registry, create a website, produce a GIF or brand artwork, change core PaperGraph behavior, or create the `v0.3.1` Git tag and GitHub Release.

## Branch and release model

Development starts from the current `origin/main`, which already contains the merged v0.3 implementation, the `v0.3.0` tag, its GitHub Release, and the MIT license. Work occurs on `feature/v0.3.1-launch-readiness`.

After deterministic and packaging validation, the branch is pushed and proposed through a new pull request. The implementation does not merge `main`, move or replace `v0.3.0`, create `v0.3.1`, or publish a GitHub Release automatically.

## Minimal CLI behavior

The installed `papergraph-mcp` entry point continues to start the stdio MCP server when invoked without arguments. It adds:

```text
papergraph-mcp --help
papergraph-mcp --version
```

`--version` prints exactly:

```text
papergraph-mcp 0.3.1
```

`--help` describes PaperGraph as a theorem-dependency MCP server and exits successfully without starting MCP. Unknown arguments remain command-line errors. Version reporting uses installed distribution metadata through `importlib.metadata`, avoiding a second manually synchronized version constant.

The server entry point accepts an optional argument sequence for direct tests while remaining compatible with package-script invocation. Tests replace `mcp.run` only at the process boundary and prove that no arguments still call it once.

## Continuous integration

Add `.github/workflows/ci.yml` with least-privilege `contents: read` permissions. It runs for pull requests and pushes to `main`, and cancels obsolete runs for the same workflow/ref.

The test job uses this matrix:

- `ubuntu-latest`, Python `3.10`
- `ubuntu-latest`, Python `3.12`
- `windows-latest`, Python `3.10`
- `windows-latest`, Python `3.12`

It uses immutable action revisions:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`)
- `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9` (`v9.0.0`)

Each matrix job selects its Python through `UV_PYTHON`, runs `uv sync --locked --dev`, and executes `uv run pytest -q -p no:cacheprovider`. Automated tests remain deterministic and do not contact arXiv.

A separate Ubuntu build job runs after the test matrix, executes `uv build`, creates a clean temporary environment, installs the generated wheel, and verifies `papergraph-mcp --version` returns `papergraph-mcp 0.3.1`. There is no PyPI upload, release upload, secret, write permission, or deployment step.

The repository test suite parses the workflow as YAML and verifies triggers, permissions, matrix values, locked synchronization, the full pytest invocation, and the wheel smoke-test command. `PyYAML>=6,<7` is a development-only dependency for this repository-level validation.

## README information architecture

Rewrite the README in this order:

1. Project name, one-sentence value proposition, and badges for CI, Python 3.10+, MIT, and the latest GitHub Release.
2. A short explanation of the problem: agents normally receive flat LaTeX text, while PaperGraph exposes theorem-like statements and their reference relationships.
3. A concise capability list covering local/multi-file LaTeX, direct arXiv import, safe extraction, persistent caching, and graph queries.
4. A 60-second Quick Start.
5. Generic JSON-style stdio MCP configuration.
6. A table describing `load_paper`, `load_arxiv_paper`, `list_theorems`, `get_theorem`, `get_dependencies`, and `where_used`.
7. A real arXiv demonstration using `math/0307200`, which has been checked to select `main.tex` and expose seven theorem-like nodes with the current parser.
8. A Mermaid data-flow diagram from local/arXiv input through loading, parsing, graph construction, and MCP queries.
9. Safety and cache behavior.
10. Development, testing, contributing, limitations, and license sections.

The stable GitHub command shown to end users is:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.3.1 papergraph-mcp --version
```

The MCP configuration uses the same immutable tag and executes `papergraph-mcp` through `uvx`. The README explicitly notes that `v0.3.1` becomes available after the release tag is published. Contributor instructions use a clone plus `uv sync` rather than the immutable end-user command.

The README does not claim PyPI availability, PDF parsing, arbitrary URL support, proof verification, full TeX expansion, or compatibility with every LaTeX project.

## Package metadata

Update `pyproject.toml` and `uv.lock` to version `0.3.1`. Add:

- Keywords for MCP, arXiv, LaTeX, mathematics, theorem graphs, and AI agents.
- Standard classifiers for Python 3, the CI-tested Python 3.10 and 3.12 versions, MIT licensing, OS independence, and scientific/research use.
- Project URLs for Homepage, Repository, Issues, and Releases, all under `https://github.com/lotchuazzz-crypto/papergraph-mcp`.

No runtime dependency is added. `PyYAML` remains in the development group only.

## Community files

Add `CONTRIBUTING.md` with environment setup, focused and complete test commands, branch/commit expectations, pull-request guidance, and a reminder that tests must not depend on the live arXiv service.

Add structured issue forms:

- `.github/ISSUE_TEMPLATE/bug_report.yml` requests version, operating system, Python version, input type, reproduction steps, expected behavior, actual behavior, and sanitized logs. It warns users not to attach private papers or secrets.
- `.github/ISSUE_TEMPLATE/feature_request.yml` requests the problem, proposed outcome, alternatives, and additional context.
- `.github/ISSUE_TEMPLATE/config.yml` disables blank issues.

Add `.github/pull_request_template.md` with summary, motivation, testing, compatibility, documentation, and a checklist for deterministic tests and sensitive-data review.

No security email address is invented. A `SECURITY.md` file is deferred until the maintainer chooses a private contact or enables GitHub private vulnerability reporting.

## Testing strategy

Add `tests/test_cli.py` to drive the public entry point directly:

- `--version` prints exactly `papergraph-mcp 0.3.1`, exits successfully, and does not run MCP.
- `--help` contains the program name and theorem-dependency description, exits successfully, and does not run MCP.
- No arguments call `mcp.run` exactly once.
- An unknown argument exits with status 2 and does not run MCP.

Add `tests/test_repository.py` to validate:

- The package and lockfile versions are both `0.3.1`.
- Runtime and development dependencies remain in their intended groups.
- Required project URLs, keywords, and classifiers exist.
- The CI workflow has the exact triggers, permissions, matrix, locked install, deterministic pytest command, and build-smoke steps described above.
- README badges and pinned `v0.3.1` GitHub command are present.
- All paths linked from the README exist locally.
- Contribution and issue-template files contain their required sections and privacy warning.

All 98 v0.3 tests remain unchanged and passing. The final acceptance sequence is:

1. Run the complete deterministic suite.
2. Build both source distribution and wheel with `uv build`.
3. Install the wheel into a fresh isolated environment.
4. Run the installed `papergraph-mcp --version` and `--help` commands.
5. Run one live `math/0307200` import with an isolated temporary cache and confirm seven parsed nodes. This is a manual acceptance check, not a committed automated test.
6. Run the deterministic suite again after the live check.
7. Confirm a clean diff, no generated distributions, no cache data, and no secrets.

## Error handling and compatibility

CLI parsing errors use the conventional exit status and stderr generated by `argparse`. Metadata lookup failures are not hidden because they indicate a broken installation that the wheel smoke test must catch.

CI failures block release readiness but do not mutate the repository or publish artifacts. Documentation examples use public data only. Issue templates explicitly discourage uploading private manuscripts, tokens, or full sensitive logs.

The existing public MCP tools and return values do not change. Calling `papergraph-mcp` without arguments remains the same stdio-server startup path used by MCP clients.

## Acceptance criteria

v0.3.1 is ready when:

- A fresh Git checkout passes the four-platform/version CI matrix.
- The built wheel installs cleanly and exposes working `--help` and `--version` commands.
- The no-argument entry point still starts MCP.
- README installation and configuration examples are version-pinned and internally consistent.
- The real `math/0307200` demonstration still selects `main.tex` and produces seven nodes.
- Contribution, issue, and pull-request paths are present and usable.
- Package metadata reports version `0.3.1` and the correct repository links.
- Every deterministic test passes after all changes.
- The feature branch is pushed for review without merging `main` or creating the release tag.
