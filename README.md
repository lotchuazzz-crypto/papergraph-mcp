# PaperGraph MCP

PaperGraph turns theorem-like environments in local or arXiv LaTeX papers
into a dependency graph exposed through MCP.

## Development

```powershell
uv sync
uv run pytest -q -p no:cacheprovider
```

## Load a local paper

Call the MCP `load_paper` tool with the root `.tex` file. PaperGraph v0.2
recursively follows standard `\input{...}` and `\include{...}` commands.
Included paths are resolved relative to the file containing each command,
and `.tex` is optional in those commands.

The `list_theorems`, `get_theorem`, `get_dependencies`, and `where_used`
tools operate on the resulting combined graph.

## Load an arXiv paper

PaperGraph v0.3 adds a dedicated `load_arxiv_paper` MCP tool:

```text
load_arxiv_paper(
    arxiv_id="2401.12345",
    main_file=None,
    refresh=False,
)
```

It accepts modern identifiers (`2401.12345`, `2401.12345v2`), legacy
identifiers (`math/0307200`, `hep-th/9901001v3`), and an optional `arXiv:`
prefix. URLs are not accepted. The tool downloads only from arXiv's fixed
`https://export.arxiv.org/e-print/{id}` source endpoint, so network access is
required for a paper that is not already cached.

Downloaded sources are stored in the user's platform cache. A later call for
the same identifier reuses the validated cache without another request. Pass
`refresh=True` to fetch a replacement; a failed refresh leaves the existing
valid cache intact.

PaperGraph normally finds the root file by looking for uncommented
`\documentclass` and `\begin{document}` commands, preferring `main.tex`,
`paper.tex`, and `manuscript.tex` when needed. If multiple candidates remain,
the error lists them. Retry with a project-relative path such as
`main_file="src/article.tex"` to choose one explicitly.

For safety, PaperGraph streams downloads and extraction, limits a compressed
response to 100 MiB, limits extracted content to 500 MiB and 10,000 members,
and rejects path traversal, links, devices, FIFOs, and other special archive
members. Tar archives, compressed tar archives, gzip-compressed single TeX
files, and plain single-file TeX responses are supported.
