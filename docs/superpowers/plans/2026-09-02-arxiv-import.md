# arXiv Source Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure, cached `load_arxiv_paper` MCP tool that downloads an arXiv source package, selects its root LaTeX file, and activates the existing PaperGraph theorem graph.

**Architecture:** Keep the server thin. `papergraph.archive` owns bounded source-package extraction, while `papergraph.arxiv` owns identifier normalization, fixed-endpoint HTTP streaming, main-file selection, transactional caching, and import orchestration. The server passes the selected root file through the existing loader/parser/graph pipeline and swaps global state only after the whole operation succeeds.

**Tech Stack:** Python 3.10+, `httpx`, standard-library `tarfile`/`gzip`/`pathlib`/`json`/`tempfile`, MCP Python SDK v2, pytest, uv.

## Global Constraints

- Preserve `load_paper` and every v0.2 local-loading behavior.
- Accept only modern and legacy arXiv identifiers, optionally prefixed by `arXiv:`; never accept a caller-controlled URL.
- Limit downloads to 100 MiB, extracted data to 500 MiB, and archive members to 10,000.
- Never extract absolute, drive-qualified, parent-traversing, linked, device, FIFO, or other special archive members.
- Build replacements in a temporary sibling and publish only a completely validated cache entry.
- Keep an existing valid cache entry intact when refresh fails.
- Automated tests must use `httpx.MockTransport`; only the final manual acceptance check may use the live network.
- Follow red-green-refactor for every behavior change and commit after each coherent task.

---

## Task 1: Add the HTTP dependency and establish the baseline

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] Add `httpx>=0.27,<1` to `[project].dependencies` in `pyproject.toml`.
- [ ] Synchronize the environment and lock file:

  ```powershell
  C:\Users\Jonathan Lee\.local\bin\uv.exe sync
  ```

- [ ] Verify the dependency is the real `httpx` package and record the current regression baseline:

  ```powershell
  .\.venv\Scripts\python.exe -c "import httpx; print(httpx.__version__)"
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

  Expected baseline: all 15 existing v0.2 tests pass.

- [ ] Commit:

  ```powershell
  git add pyproject.toml uv.lock
  git commit -m "Add HTTP client dependency"
  ```

## Task 2: Implement bounded, safe source-package extraction

**Files:**

- Create: `src/papergraph/archive.py`
- Create: `tests/test_archive.py`

**Public implementation surface:**

```python
MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024

class ArchiveError(Exception): ...
class UnsafeArchiveError(ArchiveError): ...
class ArchiveLimitError(ArchiveError): ...
class UnsupportedArchiveError(ArchiveError): ...

def extract_source_package(
    source: Path,
    destination: Path,
    *,
    max_members: int = MAX_ARCHIVE_MEMBERS,
    max_bytes: int = MAX_EXTRACTED_BYTES,
) -> None: ...
```

- [ ] Write failing tests for a regular tar package and a gzip-compressed tar package. Each test creates the package in `tmp_path`, calls `extract_source_package`, and asserts nested file contents.
- [ ] Run the focused tests and confirm failure because `papergraph.archive` does not exist:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_archive.py -q -p no:cacheprovider
  ```

- [ ] Implement tar detection with `tarfile.open(..., mode="r:*")` and manual member extraction. Normalize member names as POSIX paths after converting backslashes; reject absolute paths, Windows drive prefixes, `..`, and resolved targets outside `destination`.
- [ ] Permit only directories and regular files. Reject symbolic links, hard links, devices, FIFOs, and all unknown member types before writing anything from that member.
- [ ] Count members before extraction and reject `len(members) > max_members`. Sum declared regular-file sizes and reject the archive before extraction if the total exceeds `max_bytes`. During copying, count actual bytes as a second enforcement layer.
- [ ] Rerun the focused tests and confirm the tar cases pass.
- [ ] Add failing tests for absolute paths, `../` traversal, backslash traversal, drive-qualified paths, symlinks, hardlinks, special files, excessive member count, excessive declared size, and excessive bytes actually read from a mocked member stream.
- [ ] Implement the smallest changes required to make every safety test pass. Ensure no rejected path creates content outside `destination`.
- [ ] Add failing tests for a gzip-compressed single TeX source and a plain single-file TeX response; both must become `destination/main.tex`.
- [ ] Implement fallback detection: after tar parsing raises `ReadError`, recognize gzip magic and stream-decompress one file, otherwise accept only plausible non-empty TeX text. Apply the extracted-byte limit to both. Reject zip signatures, random binary content, empty bodies, and invalid gzip as `UnsupportedArchiveError`.
- [ ] Run focused and regression tests:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_archive.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

- [ ] Commit:

  ```powershell
  git add src\papergraph\archive.py tests\test_archive.py
  git commit -m "Add safe arXiv source extraction"
  ```

## Task 3: Normalize identifiers and stream bounded downloads

**Files:**

- Create: `src/papergraph/arxiv.py`
- Create: `tests/test_arxiv.py`

**Initial implementation surface:**

```python
ARXIV_SOURCE_BASE = "https://export.arxiv.org/e-print"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

class ArxivImportError(Exception): ...
class InvalidArxivIdError(ArxivImportError): ...
class ArxivDownloadError(ArxivImportError): ...
class ArxivCacheError(ArxivImportError): ...
class MainFileSelectionError(ArxivImportError): ...

def normalize_arxiv_id(value: str) -> str: ...

def download_arxiv_source(
    arxiv_id: str,
    destination: Path,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> None: ...
```

- [ ] Write parameterized failing tests showing these normalize successfully: `2401.12345`, `2401.12345v2`, `arXiv:2401.12345`, `math/0307200`, and `hep-th/9901001v3`.
- [ ] Add rejection tests for empty values, URLs, whitespace inside identifiers, `..`, leading slashes, malformed modern IDs, malformed legacy IDs, and version zero.
- [ ] Run the focused tests to establish red:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_arxiv.py -q -p no:cacheprovider
  ```

- [ ] Implement strict full-match patterns: modern `\d{4}\.\d{4,5}(?:v[1-9]\d*)?` and legacy `[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v[1-9]\d*)?`. Strip surrounding whitespace and one case-insensitive `arXiv:` prefix; return a canonical prefix-free identifier.
- [ ] Write a failing `httpx.MockTransport` test asserting a GET to exactly `https://export.arxiv.org/e-print/{normalized-id}`, redirects enabled, a PaperGraph user agent, streamed body contents, and no request to a caller-provided host.
- [ ] Implement `download_arxiv_source` with `httpx.Timeout(connect=10, read=60, write=60, pool=10)`. Stream into `destination`, reject non-2xx responses, declared `Content-Length` over the limit, observed bytes over the limit, and empty responses. Delete a partial destination on every failure.
- [ ] Add failing tests for oversized declared length, oversized streamed body, empty response, HTTP errors, timeout, and connection error. Assert messages identify the normalized paper but do not expose destination paths or response bodies.
- [ ] Translate `httpx.HTTPError` and validation failures into `ArxivDownloadError`; make all focused tests pass.
- [ ] Run focused and regression tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_arxiv.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add src\papergraph\arxiv.py tests\test_arxiv.py
  git commit -m "Add bounded arXiv source downloads"
  ```

## Task 4: Select and validate a root LaTeX file

**Files:**

- Modify: `src/papergraph/arxiv.py`
- Modify: `tests/test_arxiv.py`

**New implementation surface:**

```python
def select_main_file(
    project_root: Path,
    main_file: str | None = None,
) -> Path: ...
```

- [ ] Write failing tests for: one document candidate; unique preferred `main.tex`, then `paper.tex`, then `manuscript.tex`; ambiguity; no valid candidate; explicit nested override; non-`.tex` override; missing override; absolute override; drive-qualified override; and parent traversal.
- [ ] Test that commented `\documentclass` or `\begin{document}` does not qualify, while escaped percent signs do not incorrectly hide later commands.
- [ ] Implement recursive enumeration of non-hidden `.tex` regular files. Inspect only a bounded prefix per file, decode with a documented tolerant strategy, strip LaTeX comments consistently with the loader, and require both root-document commands in uncommented text.
- [ ] Return an absolute resolved path inside `project_root`. Error messages for ambiguity must list sorted relative candidate paths; the no-candidate error must list discovered `.tex` paths when present.
- [ ] For explicit overrides, normalize both slash styles, reject absolute/drive/`..` paths before resolution, require containment, a regular file, and a `.tex` suffix.
- [ ] Run focused and regression tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_arxiv.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add src\papergraph\arxiv.py tests\test_arxiv.py
  git commit -m "Select arXiv root LaTeX files"
  ```

## Task 5: Add transactional persistent caching and orchestration

**Files:**

- Modify: `src/papergraph/arxiv.py`
- Modify: `tests/test_arxiv.py`

**Final orchestration surface:**

```python
@dataclass(frozen=True, slots=True)
class ArxivProject:
    arxiv_id: str
    project_dir: Path
    main_file: Path
    cached: bool

def default_cache_root() -> Path: ...

def prepare_arxiv_project(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
    *,
    cache_root: Path | None = None,
    client: httpx.Client | None = None,
) -> ArxivProject: ...
```

- [ ] Write failing tests for platform cache-root precedence: `LOCALAPPDATA`, then `XDG_CACHE_HOME`, then `~/.cache`. Isolate environment variables with `monkeypatch`.
- [ ] Implement `default_cache_root`. Encode cache directory names deterministically, replacing the slash in legacy IDs with `__` and preserving version suffixes.
- [ ] Write a failing first-import test using `MockTransport`. Assert download, extraction, main-file selection, a JSON manifest named `.papergraph.json`, and `cached is False`.
- [ ] Implement preparation in a temporary sibling directory. Store extracted files under the final entry root and a manifest containing only the normalized ID and main-file relative path. Flush/close files before publishing with an atomic rename.
- [ ] Write a failing cache-hit test that supplies a transport which would fail if called. Validate manifest ID, safe relative main path, existence, regular-file status, suffix, and containment; return `cached is True` without network access.
- [ ] Write failing tests for `refresh=True`: successful refresh replaces the entry and returns `cached is False`; failed download, extraction, or selection preserves the old valid entry byte-for-byte; temporary siblings are removed.
- [ ] Implement refresh with an adjacent backup only during the final rename window, restore it if publication fails, and remove it after success. Never delete the valid entry before a replacement is ready.
- [ ] Write failing tests for corrupt JSON, mismatched IDs, unsafe manifest paths, missing selected files, and invalid entry layout. Treat these as cache misses and rebuild when possible; if rebuilding fails, raise `ArxivCacheError` or the underlying domain error and leave no partial published state.
- [ ] Test that a `main_file` override is honored for both new imports and valid cache hits. A different valid override may select another root inside the cached project without downloading again.
- [ ] Translate `ArchiveError` subclasses into safe `ArxivImportError` messages that retain whether the package was unsafe, too large, or unsupported.
- [ ] Run focused and full tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_arxiv.py tests\test_archive.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add src\papergraph\arxiv.py tests\test_arxiv.py
  git commit -m "Cache prepared arXiv source projects"
  ```

## Task 6: Expose arXiv import through MCP without unsafe state swaps

**Files:**

- Modify: `src/papergraph/server.py`
- Create: `tests/test_server.py`

- [ ] Write a failing test that monkeypatches `prepare_arxiv_project` to return a temporary multi-file project, invokes `load_arxiv_paper`, and asserts normalized ID, selected path, cache flag, node count, kind counts, and availability through the existing graph query functions.
- [ ] Add the MCP tool:

  ```python
  @mcp.tool()
  def load_arxiv_paper(
      arxiv_id: str,
      main_file: str | None = None,
      refresh: bool = False,
  ) -> dict: ...
  ```

  Compose `prepare_arxiv_project -> load_latex_project -> parse_latex -> PaperGraph`. Assign `_current_graph` and `_current_path` only after every step succeeds.
- [ ] Extract a private response/count helper only if it removes duplication with `load_paper`; do not change the existing public response shape of `load_paper`.
- [ ] Write failing tests proving `ArxivImportError`, loader `OSError`, and loader `ValueError` become `ToolError` with useful messages.
- [ ] Add a state-preservation test: load a known local graph, force an arXiv failure after preparation, and assert subsequent graph queries still return the original paper.
- [ ] Update `require_graph` to mention both load tools without breaking its exception type.
- [ ] Run focused and regression tests, then commit:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_server.py -q -p no:cacheprovider
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  git add src\papergraph\server.py tests\test_server.py
  git commit -m "Expose arXiv paper loading through MCP"
  ```

## Task 7: Document and version v0.3

**Files:**

- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/papergraph/__init__.py` only if it currently exposes a version constant

- [ ] Update the package version to `0.3.0` and synchronize the lock file:

  ```powershell
  C:\Users\Jonathan Lee\.local\bin\uv.exe lock
  ```

- [ ] Expand the README with `load_arxiv_paper`, accepted ID examples, cache reuse and `refresh`, ambiguous-root recovery with `main_file`, network requirements, fixed arXiv source endpoint, and the 100 MiB/500 MiB/10,000 safety limits.
- [ ] Keep the local `load_paper` v0.2 documentation intact.
- [ ] Run the full deterministic suite:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

- [ ] Commit:

  ```powershell
  git add README.md pyproject.toml uv.lock src\papergraph\__init__.py
  git commit -m "Document PaperGraph v0.3"
  ```

  If `src/papergraph/__init__.py` does not contain version metadata and is unchanged, omit it from `git add`.

## Task 8: Final verification and live acceptance

**Files:** No intended source changes. If verification reveals a defect, return to the relevant task, add a regression test first, fix it, and commit that focused correction.

- [ ] Inspect the complete branch diff and confirm it contains no generated archives, cache entries, secrets, local environment changes, or unrelated edits:

  ```powershell
  git status --short
  git diff --check origin/main...HEAD
  git diff --stat origin/main...HEAD
  ```

- [ ] Run all deterministic tests from a clean process:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  ```

- [ ] Exercise a local MCP-level smoke test with a `MockTransport` fixture or temporary source package to verify download-to-query behavior without network dependency.
- [ ] Perform one manual live import using a small stable arXiv identifier and an isolated temporary cache root. Confirm the fixed endpoint returns a supported source package, the root file is selected, and at least the import metadata is returned. If that paper has no theorem environments, successful preparation and graph activation with zero nodes is acceptable; otherwise confirm theorem queries work.
- [ ] Run the full deterministic suite again after the live check to prove the acceptance action did not affect tests.
- [ ] Review the implementation against every acceptance criterion in `docs/superpowers/specs/2026-09-02-arxiv-import-design.md`.
- [ ] Report commits, exact test result, live acceptance result, and any known limitations. Do not merge or push unless the user explicitly asks.
