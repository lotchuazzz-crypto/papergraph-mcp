# arXiv Source Import Design

## Goal

Add a dedicated MCP tool that accepts an arXiv identifier, downloads and safely unpacks the paper's source package, selects its root LaTeX file, and loads the resulting theorem dependency graph through the existing PaperGraph pipeline.

## Scope

v0.3 adds arXiv source import only. GitHub Actions, theorem source-line metadata, PDF fallback, and arbitrary URL downloads remain outside this release.

Supported identifiers include:

- Modern identifiers such as `2401.12345` and `2401.12345v2`.
- Legacy identifiers such as `math/0307200` and `hep-th/9901001v3`.
- The optional `arXiv:` prefix.

Web URLs are not accepted as identifiers. An unversioned identifier resolves to the latest source returned by arXiv and remains cached until the caller passes `refresh=True`.

## Public MCP interface

Add:

```python
load_arxiv_paper(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
) -> dict
```

The tool returns the normalized arXiv identifier, selected root-file path, whether an existing cache entry was reused, theorem count, and counts by theorem kind. It activates the same in-memory graph used by `list_theorems`, `get_theorem`, `get_dependencies`, and `where_used`.

`load_paper(path)` remains the local-file interface and keeps its current behavior.

## Components and data flow

Add `src/papergraph/arxiv.py` for identifier validation, HTTP download, caching, main-file selection, and project orchestration. Add `src/papergraph/archive.py` for source-package format detection and safe extraction.

```text
load_arxiv_paper
  -> normalize_arxiv_id
  -> fetch source from https://export.arxiv.org/e-print/{id}
  -> enforce compressed download limit
  -> safely unpack into a temporary cache entry
  -> select or validate the main .tex file
  -> atomically publish the cache entry
  -> load_latex_project
  -> parse_latex
  -> PaperGraph
```

The server imports this orchestration layer and does not implement network, archive, or cache logic itself.

## HTTP behavior

Declare `httpx>=0.27,<1` as a direct dependency. Download with a 10-second connection timeout, a 60-second read timeout, redirects enabled, and a PaperGraph user agent. Only the fixed arXiv e-print endpoint is constructed; user input never becomes a host, scheme, query, or arbitrary path.

Read the response as a stream. Reject a declared or observed body larger than 100 MiB. Treat non-success responses, timeouts, connection failures, and empty bodies as explicit import errors containing the normalized identifier but no local secrets.

Tests use `httpx.MockTransport`; the normal automated suite never depends on live network access.

## Cache behavior

Use a platform-appropriate per-user cache root:

- `%LOCALAPPDATA%\papergraph\arxiv` on Windows when `LOCALAPPDATA` exists.
- `$XDG_CACHE_HOME/papergraph/arxiv` when `XDG_CACHE_HOME` exists.
- `~/.cache/papergraph/arxiv` otherwise.

An optional internal cache-root parameter permits isolated tests without changing the MCP signature. Replace `/` in legacy identifiers with a filesystem-safe separator and keep version suffixes distinct.

Each cache entry contains the extracted project and a small JSON manifest with the normalized identifier and selected main-file relative path. A cache hit validates the manifest and selected file before reuse.

Downloads and extraction occur in a temporary sibling directory. Only a fully downloaded, safely extracted, and unambiguously selected project is renamed into the final cache location. On refresh, the existing valid entry remains usable until the replacement is ready. Failures clean up temporary data and do not publish partial entries.

## Safe archive extraction

Support tar archives, compressed tar archives recognized by Python's `tarfile`, gzip-compressed single-source files, and plain single-file TeX responses.

Before writing an archive member:

- Reject absolute paths, drive-qualified paths, and any path containing `..`.
- Resolve the destination and require it to remain inside the temporary extraction root.
- Reject symbolic links, hard links, devices, FIFOs, and other special members.
- Permit only directories and regular files.
- Enforce at most 10,000 members.
- Enforce at most 500 MiB of total declared and actually written content.

Single-file gzip and plain-TeX responses are written as `main.tex` under the same extracted-size limit.

## Main-file selection

If `main_file` is supplied, interpret it relative to the extracted project root. It must remain inside that root, exist as a regular file, and use a `.tex` suffix.

Without an override:

1. Enumerate non-hidden `.tex` files.
2. Keep files whose uncommented text contains both `\documentclass` and `\begin{document}`.
3. If exactly one candidate remains, choose it.
4. If multiple remain, prefer a unique basename in this order: `main.tex`, `paper.tex`, `manuscript.tex`.
5. If selection is still ambiguous, raise an error listing relative candidate paths.
6. If no candidate exists, raise an error listing the discovered `.tex` files when available.

Candidate inspection uses bounded text reads so a single unusually large file cannot create an avoidable memory spike.

## Error model

Define focused domain exceptions in `arxiv.py`, rooted at `ArxivImportError`, for invalid identifiers, download failures, unsafe or unsupported archives, cache corruption, and main-file selection failures. `archive.py` raises archive-specific subclasses or errors that `arxiv.py` translates.

The MCP tool converts `ArxivImportError`, loader `OSError`, and loader `ValueError` into `ToolError`. Failed imports do not replace the currently loaded graph.

## Testing

Add unit tests for:

- Modern, versioned, prefixed, and legacy identifier normalization.
- Invalid identifiers and attempted URL/path input.
- Correct endpoint construction and streaming through `httpx.MockTransport`.
- Download size enforcement and HTTP failure translation.
- Safe tar extraction and rejection of traversal, links, special files, excessive members, and excessive expanded size.
- Single-file gzip and plain-TeX packages.
- Unique, preferred-name, ambiguous, missing, and explicitly overridden main-file selection.
- Cache reuse without a second HTTP request, refresh replacement, invalid manifest handling, and cleanup after failure.
- MCP activation of a downloaded multi-file project and conversion of import failures to `ToolError`.
- Regression of all v0.2 local-loading behavior.

After the deterministic suite passes, perform one manual live import of a small stable arXiv source package. The live check is an acceptance command, not a committed test.

## Version and documentation

Update the package version and lockfile to `0.3.0`. Document `load_arxiv_paper`, supported identifier formats, caching, `main_file`, `refresh`, network requirements, and the safety limits in the README.

## Acceptance criteria

v0.3 is complete when a valid arXiv identifier can populate the active PaperGraph from a safely cached source package; ambiguous entry files can be resolved with `main_file`; malicious or excessive archives are rejected without filesystem escape or partial cache state; every deterministic test passes; and one live arXiv import succeeds.
