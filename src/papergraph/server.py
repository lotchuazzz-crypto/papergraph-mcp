from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from papergraph.arxiv import ArxivImportError, prepare_arxiv_project
from papergraph.graph import PaperGraph
from papergraph.loader import load_latex_project
from papergraph.parser import parse_latex


mcp = MCPServer("PaperGraph MCP")


_current_graph: PaperGraph | None = None
_current_path: Path | None = None


def require_graph() -> PaperGraph:
    if _current_graph is None:
        raise ToolError(
            "No paper is loaded. "
            "Call load_paper(path) or load_arxiv_paper(arxiv_id) first."
        )

    return _current_graph


@mcp.tool()
def load_paper(path: str) -> dict:
    """Load a local LaTeX paper and build its theorem graph."""

    global _current_graph
    global _current_path

    paper_path = Path(path).expanduser().resolve()

    if not paper_path.exists():
        raise ToolError(
            f"File does not exist: {paper_path}"
        )

    if not paper_path.is_file():
        raise ToolError(
            f"Path is not a file: {paper_path}"
        )

    if paper_path.suffix.lower() != ".tex":
        raise ToolError(
            "PaperGraph only accepts a .tex root file."
        )

    try:
        text = load_latex_project(paper_path)
    except (OSError, ValueError) as exc:
        raise ToolError(str(exc)) from exc

    nodes = parse_latex(text)

    _current_graph = PaperGraph(nodes)
    _current_path = paper_path

    kinds: dict[str, int] = {}

    for node in nodes:
        kinds[node.kind] = (
            kinds.get(node.kind, 0) + 1
        )

    return {
        "path": str(paper_path),
        "nodes": len(nodes),
        "kinds": kinds,
    }


@mcp.tool()
def load_arxiv_paper(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
) -> dict:
    """Download an arXiv source project and build its theorem graph."""

    global _current_graph
    global _current_path

    try:
        project = prepare_arxiv_project(
            arxiv_id,
            main_file,
            refresh,
        )
        text = load_latex_project(project.main_file)
    except (ArxivImportError, OSError, ValueError) as exc:
        raise ToolError(str(exc)) from exc

    nodes = parse_latex(text)
    graph = PaperGraph(nodes)

    kinds: dict[str, int] = {}
    for node in nodes:
        kinds[node.kind] = kinds.get(node.kind, 0) + 1

    _current_graph = graph
    _current_path = project.main_file

    return {
        "arxiv_id": project.arxiv_id,
        "path": str(project.main_file),
        "cached": project.cached,
        "nodes": len(nodes),
        "kinds": kinds,
    }


@mcp.tool()
def list_theorems(
    kind: str | None = None,
) -> list[dict]:
    """List theorem-like environments in the currently loaded paper."""

    graph = require_graph()

    nodes = graph.nodes

    if kind is not None:
        nodes = [
            node
            for node in nodes
            if node.kind == kind
        ]

    return [
        node.summary()
        for node in nodes
    ]


@mcp.tool()
def get_theorem(
    theorem_id: str,
) -> dict:
    """Return the full text and metadata for one theorem-like node."""

    graph = require_graph()

    try:
        node = graph.get(theorem_id)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    return node.full()


@mcp.tool()
def get_dependencies(
    theorem_id: str,
    recursive: bool = False,
) -> list[dict]:
    """Return theorem-like nodes referenced by the given theorem."""

    graph = require_graph()

    try:
        nodes = graph.dependencies(
            theorem_id,
            recursive=recursive,
        )
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    return [
        node.summary()
        for node in nodes
    ]


@mcp.tool()
def where_used(
    theorem_id: str,
) -> list[dict]:
    """Return theorem-like nodes that reference the given theorem."""

    graph = require_graph()

    try:
        nodes = graph.where_used(
            theorem_id
        )
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    return [
        node.summary()
        for node in nodes
    ]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
