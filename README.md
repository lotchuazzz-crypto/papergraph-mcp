# PaperGraph MCP

PaperGraph turns theorem-like environments in local LaTeX papers into a
dependency graph exposed through MCP.

## Development

```powershell
uv sync
uv run pytest -q -p no:cacheprovider
```

## Load a paper

Call the MCP `load_paper` tool with the root `.tex` file. PaperGraph v0.2
recursively follows standard `\input{...}` and `\include{...}` commands.
Included paths are resolved relative to the file containing each command,
and `.tex` is optional in those commands.

The `list_theorems`, `get_theorem`, `get_dependencies`, and `where_used`
tools operate on the resulting combined graph.
