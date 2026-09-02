# Multi-file LaTeX Support Design

## Goal

Upgrade PaperGraph MCP from parsing one LaTeX file to parsing a complete project rooted at a main `.tex` file, while preserving the existing parser, graph, and MCP architecture.

## Git migration

The current `feature/v0.2-multifile` branch was created from the initial `main` commit and does not contain v0.1. Merge `feature/v0.1-local-latex` into it so the existing parser, graph, server, tests, and their three original commits remain in history. Do not merge v0.2 into `main` and do not push any branch.

## Architecture

Add `src/papergraph/loader.py` immediately before the existing parser. The loader accepts the main file path, recursively expands `\\input{...}` and `\\include{...}` in source order, and returns one combined LaTeX string. The existing `parse_latex` function consumes that string without taking responsibility for file traversal. `PaperGraph` remains unchanged.

The MCP server's `load_paper` tool continues to accept one path. That path now identifies the root file of a LaTeX project rather than the only file to parse. The tool passes the expanded text to `parse_latex` and reports loader failures as `ToolError` messages.

## Loader behavior

- Resolve an included path relative to the file containing the command.
- Append `.tex` when the included path has no suffix.
- Support nested `\\input` and `\\include` commands.
- Replace each include command in place, preserving document order.
- Ignore include commands whose command begins in a LaTeX comment.
- Decode files as UTF-8 with replacement for malformed bytes, matching v0.1 behavior.
- Raise `FileNotFoundError` with the resolved path when a root or included file is missing.
- Raise `ValueError` with the include chain when a file includes itself directly or indirectly.
- Track only the active recursion chain for cycle detection. If the same file is included twice from non-recursive locations, expand it twice, matching LaTeX semantics.

Commands containing dynamically computed paths, optional arguments, or packages with nonstandard include semantics are outside v0.2 scope.

## Public interfaces

`loader.py` provides:

```python
def resolve_tex_path(parent_file: Path, included_path: str) -> Path: ...
def load_latex_project(main_file: str | Path) -> str: ...
```

`parse_file` remains unchanged for callers that deliberately parse one physical file. The MCP server composes `load_latex_project` with `parse_latex` for project-aware parsing.

## Error handling

The loader exposes ordinary Python exceptions so it remains useful outside MCP. The server catches loader `OSError` and `ValueError` failures and converts them to `ToolError` without changing successful response fields. Non-`.tex` root paths remain rejected, with the message updated from v0.1 to describe root-file support.

## Tests

Add focused loader tests using temporary real files rather than mocks. Cover path resolution, implicit `.tex`, nested recursion, both include commands, source ordering, commented commands, repeated non-cyclic includes, missing files, and direct or indirect cycles.

Add an integration test that expands a multi-file fixture, parses it, and builds a `PaperGraph`, proving references resolve across file boundaries. Run the complete existing and new pytest suite after each implementation cycle and once more for final validation.

## Version and documentation

Update the project version from `0.1.0` to `0.2.0`. Add concise README usage describing that `load_paper` accepts a root `.tex` file and follows standard `\\input` and `\\include` commands.

## Acceptance criteria

v0.2 is complete when a nested multi-file fixture produces theorem nodes in source order, cross-file dependencies work through `PaperGraph`, missing or cyclic includes fail clearly, all v0.1 tests still pass, and the full test suite exits successfully with no failures.
