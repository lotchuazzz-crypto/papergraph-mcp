# PaperGraph v0.3.1 Launch Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PaperGraph verifiably installable, understandable, and contribution-ready for a public GitHub launch without changing its theorem-graph behavior.

**Architecture:** Keep the existing MCP tool layer unchanged. Add a thin `argparse` boundary to the installed entry point, repository-level tests for metadata and automation, a least-privilege CI workflow, and launch documentation/community files. Package validation builds and installs the real wheel rather than testing only the editable checkout.

**Tech Stack:** Python 3.10+, MCP Python SDK v2, pytest, PyYAML (development only), uv, GitHub Actions, Markdown, YAML.

## Global Constraints

- Preserve all existing MCP tool names, signatures, return values, parser behavior, graph behavior, arXiv behavior, safety limits, and cache behavior.
- Calling `papergraph-mcp` with no arguments must still call `mcp.run()` exactly once.
- `papergraph-mcp --version` must print exactly `papergraph-mcp 0.3.1`.
- CI must run on Windows/Linux and Python 3.10/3.12 with no live arXiv requests.
- CI permissions are `contents: read`; there are no uploads, deployments, secrets, PyPI actions, or registry actions.
- End-user GitHub commands must pin `v0.3.1`; contributor commands use the checkout.
- Do not create or move tags, publish a Release, or merge `main`.
- Follow red-green-refactor for Python and repository behavior. Configuration is written only after a failing repository test describes it.

---

## Task 1: Add a testable CLI boundary and set version 0.3.1

**Files:**

- Create: `tests/test_cli.py`
- Modify: `src/papergraph/server.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**

- Consumes: existing `papergraph.server.mcp.run()` and the installed distribution name `papergraph-mcp`.
- Produces: `main(argv: Sequence[str] | None = None) -> None`; no-argument package-script invocation remains valid.

- [ ] Write `tests/test_cli.py` with four failing tests. Patch `server.mcp.run` with a recorder or a function that raises `AssertionError` when it must not run. Use `pytest.raises(SystemExit)` and `capsys` to assert:

  ```python
  server.main(["--version"])
  # stdout == "papergraph-mcp 0.3.1\n", exit code 0, MCP not run

  server.main(["--help"])
  # stdout contains "papergraph-mcp" and "theorem dependency", exit code 0

  server.main([])
  # returns normally and calls mcp.run once

  server.main(["--unknown"])
  # stderr contains "unrecognized arguments", exit code 2, MCP not run
  ```

- [ ] Run the focused tests and verify red because `main` accepts no argument sequence:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_cli.py -q -p no:cacheprovider
  ```

- [ ] Update `pyproject.toml` to `version = "0.3.1"`, then synchronize the lock and editable environment:

  ```powershell
  C:\Users\Jonathan Lee\.local\bin\uv.exe lock
  C:\Users\Jonathan Lee\.local\bin\uv.exe sync
  ```

- [ ] Implement the CLI in `server.py` using `argparse.ArgumentParser`, `importlib.metadata.version`, and `collections.abc.Sequence`. The parser description is `Expose LaTeX theorem dependency graphs through MCP.` Add only the standard help plus:

  ```python
  parser.add_argument(
      "--version",
      action="version",
      version=f"%(prog)s {distribution_version('papergraph-mcp')}",
  )
  ```

  Parse `argv`; after successful parsing with no exit action, call `mcp.run()` exactly once.

- [ ] Run focused and full suites:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_cli.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

- [ ] Commit:

  ```powershell
  git add tests\test_cli.py src\papergraph\server.py pyproject.toml uv.lock
  git commit -m "Add launch-ready CLI metadata"
  ```

## Task 2: Add package and repository metadata validation

**Files:**

- Create: `tests/test_repository.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**

- Consumes: repository root files and Python 3.10 `tomllib`.
- Produces: a test helper `repository_root() -> Path` and direct metadata assertions; no production API.

- [ ] Add `PyYAML>=6,<7` to the development dependency group and synchronize. It must not appear in `[project].dependencies`.
- [ ] Write failing metadata tests that parse `pyproject.toml` and `uv.lock` and assert:

  - Both report `0.3.1` for `papergraph-mcp`.
  - Runtime dependencies are exactly the existing `httpx` and `mcp[cli]` declarations.
  - Development dependencies contain pytest and PyYAML.
  - Keywords include `mcp`, `arxiv`, `latex`, `mathematics`, `theorem-graph`, and `ai-agents`.
  - Classifiers include Python 3, Python 3.10, Python 3.12, MIT, OS Independent, and Scientific/Engineering.
  - Homepage, Repository, Issues, and Releases use the canonical GitHub repository.

- [ ] Run the metadata tests and verify they fail because keywords, classifiers, URLs, and PyYAML metadata are absent.
- [ ] Add this metadata to `[project]` without changing runtime dependencies:

  ```toml
  keywords = ["mcp", "arxiv", "latex", "mathematics", "theorem-graph", "ai-agents"]
  classifiers = [
      "Development Status :: 3 - Alpha",
      "License :: OSI Approved :: MIT License",
      "Operating System :: OS Independent",
      "Programming Language :: Python :: 3",
      "Programming Language :: Python :: 3.10",
      "Programming Language :: Python :: 3.12",
      "Topic :: Scientific/Engineering",
  ]

  [project.urls]
  Homepage = "https://github.com/lotchuazzz-crypto/papergraph-mcp"
  Repository = "https://github.com/lotchuazzz-crypto/papergraph-mcp"
  Issues = "https://github.com/lotchuazzz-crypto/papergraph-mcp/issues"
  Releases = "https://github.com/lotchuazzz-crypto/papergraph-mcp/releases"
  ```

- [ ] Run the focused and full suites, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_repository.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add tests\test_repository.py pyproject.toml uv.lock
  git commit -m "Add discoverable project metadata"
  ```

## Task 3: Add least-privilege cross-platform CI and build smoke testing

**Files:**

- Create: `.github/workflows/ci.yml`
- Modify: `tests/test_repository.py`
- Modify: `.gitignore`

**Interfaces:**

- Consumes: `uv.lock`, pytest suite, `papergraph-mcp --version`, wheel output under `dist/`.
- Produces: GitHub workflow `CI`; repository tests load it with `yaml.load(..., Loader=yaml.BaseLoader)` so YAML 1.1 boolean coercion does not alter the `on` key.

- [ ] Add a failing repository test for `.github/workflows/ci.yml`. Assert its parsed structure contains pull-request and main-push triggers, `contents: read`, four matrix combinations, `uv sync --locked --dev`, the exact deterministic pytest command, a build job dependent on tests, `uv build`, wheel installation, and the expected version check.
- [ ] Add a failing assertion that `.gitignore` contains `dist/` and `.smoke-venv/`.
- [ ] Run the focused test and confirm failure because the workflow does not exist.
- [ ] Create `.github/workflows/ci.yml` with:

  - `name: CI`
  - `on: {pull_request: {}, push: {branches: [main]}}`
  - workflow/ref concurrency with `cancel-in-progress: true`
  - top-level `permissions: {contents: read}`
  - matrix test job for `ubuntu-latest`/`windows-latest` and `3.10`/`3.12`
  - `UV_PYTHON: ${{ matrix.python-version }}`
  - pinned checkout SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`
  - pinned setup-uv SHA `c771a70e6277c0a99b617c7a806ffedaca235ff9`
  - `uv sync --locked --dev`
  - `uv run pytest -q -p no:cacheprovider`

  Add an Ubuntu `build` job with `needs: test`. It runs `uv build`, creates `.smoke-venv`, installs the single wheel found under `dist`, and invokes that environment's `papergraph-mcp --version`. Use a small cross-platform Python command to resolve the wheel path rather than an unportable shell wildcard.

- [ ] Add `dist/` and `.smoke-venv/` to `.gitignore`.
- [ ] Run repository and full tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_repository.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add .github\workflows\ci.yml tests\test_repository.py .gitignore
  git commit -m "Add cross-platform CI validation"
  ```

## Task 4: Add contributor and issue workflows

**Files:**

- Create: `CONTRIBUTING.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`
- Modify: `tests/test_repository.py`

**Interfaces:**

- Consumes: current uv/pytest development workflow and GitHub issue-form schema.
- Produces: human-facing contribution contracts; no Python API.

- [ ] Write failing repository tests that require every listed file and validate YAML issue forms with PyYAML.
- [ ] Assert the bug form contains required fields for PaperGraph version, OS, Python, input type, reproduction, expected behavior, actual behavior, and logs. Require visible text warning against private papers, tokens, and secrets.
- [ ] Assert the feature form contains problem, proposed outcome, alternatives, and context fields. Assert `config.yml` has `blank_issues_enabled: false`.
- [ ] Assert the PR template contains Summary, Motivation, Testing, Compatibility, Documentation, and a sensitive-data checklist.
- [ ] Run the focused test and verify red because community files are absent.
- [ ] Write `CONTRIBUTING.md` with these exact operational commands:

  ```powershell
  uv sync
  uv run pytest -q -p no:cacheprovider
  uv run pytest tests/test_arxiv.py -q -p no:cacheprovider
  ```

  State that tests must be deterministic, network tests belong only in manual acceptance, changes need focused regression tests, and PRs must not contain manuscripts, cache data, credentials, or generated distributions.

- [ ] Create both issue forms with valid `name`, `description`, `title`, `labels`, and `body` structures. Make the required fields mandatory and keep logs optional. Add `config.yml` with no contact links and blank issues disabled.
- [ ] Create the PR template with the six required headings/checklist areas.
- [ ] Run focused and full tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_repository.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add CONTRIBUTING.md .github tests\test_repository.py
  git commit -m "Add contributor workflows"
  ```

## Task 5: Rewrite README for first-time users

**Files:**

- Modify: `README.md`
- Modify: `tests/test_repository.py`

**Interfaces:**

- Consumes: public MCP tool signatures, repository URL, version `0.3.1`, `uvx`, and the verified `math/0307200` behavior.
- Produces: launch landing page; no Python API.

- [ ] Add failing README tests for:

  - CI, Python, MIT, and Release badges.
  - The exact pinned command `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.3.1 papergraph-mcp --version`.
  - A generic JSON stdio configuration containing command `uvx` and arguments for the same immutable Git revision.
  - All six MCP tool names.
  - The `math/0307200` demonstration, `main.tex`, and seven parsed nodes.
  - A Mermaid diagram.
  - Safety limits `100 MiB`, `500 MiB`, and `10,000`.
  - Explicit limitations for no PDF fallback, no arbitrary URLs, and possible `main_file` overrides.
  - Links to `CONTRIBUTING.md` and `LICENSE`, with a local-path existence check for every relative Markdown link.

- [ ] Run the focused tests and verify red against the current short README.
- [ ] Rewrite README in the exact section order defined by the design: title/badges, value proposition, Why, Features, Quick Start, MCP Configuration, Tools, Demo, Architecture, Safety and Cache, Development, Contributing, Limitations, License.
- [ ] Use this core positioning verbatim near the top:

  ```text
  PaperGraph turns local or arXiv LaTeX papers into theorem dependency graphs that AI agents can query through MCP.
  ```

- [ ] In Quick Start, show uv installation as a prerequisite link, the pinned `--version` command, and note that the `v0.3.1` command becomes available when that GitHub Release is published. Do not claim PyPI or MCP Registry availability.
- [ ] In Demo, show `load_arxiv_paper(arxiv_id="math/0307200")` and a representative response with `path` ending in `main.tex`, `cached: false`, and `nodes: 7`. Explain that exact node kinds reflect LaTeX environment names.
- [ ] Add a Mermaid flow with local `.tex` and arXiv ID inputs converging on recursive loading, parsing, `PaperGraph`, and the four query tools.
- [ ] Run focused and full tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_repository.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add README.md tests\test_repository.py
  git commit -m "Rewrite README for public launch"
  ```

## Task 6: Verify source, wheel, installation, and live demonstration

**Files:** No intended tracked changes. If a defect appears, add a failing regression test in the owning test file before fixing it.

**Interfaces:**

- Consumes: complete repository and network access for one isolated manual acceptance run.
- Produces: verification evidence only; generated `dist/` and `.smoke-venv/` remain ignored and are removed after inspection.

- [ ] Run the complete deterministic suite from a fresh process:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

- [ ] Build distributions and inspect the filenames:

  ```powershell
  C:\Users\Jonathan Lee\.local\bin\uv.exe build
  Get-ChildItem dist
  ```

  Expected: one `papergraph_mcp-0.3.1-py3-none-any.whl` and one `papergraph_mcp-0.3.1.tar.gz`.

- [ ] Create `.smoke-venv`, install the exact wheel with `uv pip install --python`, and run both installed commands. Expected version output is exactly `papergraph-mcp 0.3.1`; help contains `theorem dependency`.
- [ ] Use an isolated `TemporaryDirectory` cache to call `prepare_arxiv_project("math/0307200")`, load/parse it, and assert the selected relative path is `main.tex` and the parsed node count is seven. Do not retain the cache.
- [ ] Run the deterministic suite again after the live check.
- [ ] Inspect repository state and complete diff:

  ```powershell
  git diff --check origin/main...HEAD
  git status --short --branch
  git diff --stat origin/main...HEAD
  ```

  Confirm no distributions, virtual environments, caches, secrets, or unrelated edits are tracked.

- [ ] Review each acceptance criterion in `docs/superpowers/specs/2026-09-02-launch-readiness-design.md` against command output.
- [ ] Push `feature/v0.3.1-launch-readiness` and create a pull request titled `Prepare PaperGraph v0.3.1 for public launch`. Do not merge it and do not create the `v0.3.1` tag or Release.
