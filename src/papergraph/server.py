import argparse
import json
import sqlite3
from collections.abc import Sequence
from functools import wraps
from importlib.metadata import version as distribution_version
from pathlib import Path
from threading import RLock

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from papergraph.arxiv import (
    ArxivImportError,
    ArxivProject,
    prepare_arxiv_project,
    validate_arxiv_input as validate_arxiv_input_result,
    validate_arxiv_request as validate_arxiv_request_result,
)
from papergraph.diagnostics import environment_diagnostics
from papergraph.graph import PaperGraph
from papergraph.identity import paper_id_from_arxiv
from papergraph.loader import load_latex_project
from papergraph.parser import parse_latex
from papergraph.pdf import PdfExtractionError
from papergraph.project import load_project
from papergraph.workspace import SCHEMA_VERSION, Workspace, WorkspaceError


mcp = MCPServer("PaperGraph MCP")


_current_graph: PaperGraph | None = None
_current_path: Path | None = None
_current_workspace: Workspace | None = None
_workspace_state_lock = RLock()

_WORKSPACE_TOOL_ERRORS = (
    WorkspaceError,
    PdfExtractionError,
    sqlite3.DatabaseError,
    OSError,
    ValueError,
    KeyError,
)
_ARXIV_WORKSPACE_TOOL_ERRORS = (ArxivImportError, *_WORKSPACE_TOOL_ERRORS)


def _serialized_workspace_tool(function):
    """Keep active-workspace access and replacement in one critical section."""

    @wraps(function)
    def serialized(*args, **kwargs):
        with _workspace_state_lock:
            return function(*args, **kwargs)

    return serialized


def _reset_server_state() -> None:
    """Reset process state, closing any active workspace connection."""

    global _current_graph
    global _current_path
    global _current_workspace

    with _workspace_state_lock:
        if _current_workspace is not None:
            _current_workspace.close()
        _current_workspace = None
        _current_graph = None
        _current_path = None


def require_graph() -> PaperGraph:
    if _current_graph is None:
        raise ToolError(
            "No paper is loaded. "
            "Call load_paper(path) or load_arxiv_paper(arxiv_id) first."
        )

    return _current_graph


def require_workspace() -> Workspace:
    with _workspace_state_lock:
        if _current_workspace is None:
            raise ToolError(
                "No workspace is open. Call open_workspace(path) first."
            )

        return _current_workspace


@mcp.tool()
def get_environment_diagnostics() -> dict:
    """Return PaperGraph version and reproducible launch diagnostics."""

    return environment_diagnostics()


@mcp.tool()
def validate_arxiv_input(
    text_id: str | None = None,
    url: str | None = None,
) -> dict:
    """Normalize arXiv ID and URL inputs and return the safe next action."""

    return validate_arxiv_input_result(text_id=text_id, url=url)


@mcp.tool()
def validate_arxiv_request(input: str) -> dict:
    """Validate a raw user arXiv request and return the safe next action."""

    return validate_arxiv_request_result(input)


@mcp.tool()
@_serialized_workspace_tool
def open_workspace(path: str) -> dict:
    """Open or initialize a persistent multi-paper workspace."""

    global _current_workspace

    try:
        replacement = Workspace.open(path)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc

    previous = _current_workspace
    _current_workspace = replacement
    if previous is not None:
        previous.close()

    return {
        "path": str(replacement.path),
        "schema_version": SCHEMA_VERSION,
        **replacement.counts(),
    }


@mcp.tool()
@_serialized_workspace_tool
def workspace_add_local_paper(path: str, paper_id: str) -> dict:
    """Add or replace a local LaTeX project in the active workspace."""

    workspace = require_workspace()
    paper_path = Path(path).expanduser().resolve()
    try:
        project = load_project(paper_path)
        result = workspace.import_project(
            paper_id,
            "local",
            str(paper_path),
            None,
            project,
        )
        return workspace.get_paper(result.paper_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_add_arxiv_paper(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
) -> dict:
    """Add or replace an arXiv LaTeX project in the active workspace."""

    workspace = require_workspace()
    try:
        prepared = prepare_arxiv_project(arxiv_id, main_file, refresh)
        paper_id, source_version = paper_id_from_arxiv(prepared.arxiv_id)
        project = load_project(prepared.main_file)
        result = workspace.import_project(
            paper_id,
            "arxiv",
            paper_id.removeprefix("arxiv:"),
            source_version,
            project,
        )
        return workspace.get_paper(result.paper_id)
    except _ARXIV_WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_add_pdf_paper(path: str, paper_id: str) -> dict:
    """Add or replace a born-digital PDF paper in the active workspace."""

    workspace = require_workspace()
    try:
        result = workspace.import_pdf(path, paper_id)
        return {
            **workspace.get_paper(result.paper_id),
            **result.evidence_import_summary(),
        }
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_list_papers() -> list[dict]:
    """List all papers stored in the active workspace."""

    try:
        return require_workspace().list_papers()
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_paper(paper_id: str) -> dict:
    """Return metadata and counts for one stored paper."""

    try:
        return require_workspace().get_paper(paper_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_search_theorems(
    query: str,
    paper_id: str | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search theorem titles and bodies across the active workspace."""

    try:
        return require_workspace().search_theorems(
            query,
            paper_id=paper_id,
            kind=kind,
            limit=limit,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_dependencies(
    global_theorem_id: str,
    recursive: bool = False,
) -> list[dict]:
    """Return dependencies of a globally identified stored theorem."""

    try:
        return require_workspace().get_dependencies(
            global_theorem_id,
            recursive=recursive,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_dependency_diagnostics(
    global_theorem_id: str,
    recursive: bool = False,
) -> dict:
    """Explain how workspace dependencies were extracted for one theorem."""

    try:
        return require_workspace().get_dependency_diagnostics(
            global_theorem_id,
            recursive=recursive,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_citations(
    paper_id: str,
    direction: str = "outgoing",
    include_unresolved: bool = True,
) -> list[dict]:
    """Return incoming or outgoing citation evidence for a stored paper."""

    try:
        return require_workspace().get_citations(
            paper_id,
            direction=direction,
            include_unresolved=include_unresolved,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_list_results(
    paper_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List stored evidence results across the active workspace."""

    try:
        return require_workspace().list_results(
            paper_id=paper_id,
            kind=kind,
            limit=limit,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_result(result_id: str) -> dict:
    """Return one stored evidence result with source spans."""

    try:
        return require_workspace().get_result(result_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_result_proof(result_id: str) -> dict:
    """Return proof evidence for one stored evidence result."""

    try:
        return require_workspace().get_result_proof(result_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_proof_dependencies(
    result_id: str,
    recursive: bool = False,
) -> dict:
    """Return proof dependency evidence for one stored evidence result."""

    try:
        return require_workspace().get_proof_dependencies(
            result_id,
            recursive=recursive,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_external_result_mentions(result_id: str) -> list[dict]:
    """Return external result mentions from a result's proof evidence."""

    try:
        return require_workspace().get_external_result_mentions(result_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_evidence(node_or_edge_id: str) -> dict:
    """Return metadata and source spans for one evidence node or edge."""

    try:
        evidence = require_workspace().get_evidence(node_or_edge_id)
        return {
            "node_or_edge_id": node_or_edge_id,
            **evidence,
        }
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_export_reading_bundle(paper_id: str) -> dict:
    """Export a paper-level evidence bundle for paper-reading consumers."""

    try:
        return require_workspace().export_reading_bundle(paper_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_export_result_reading_context(result_id: str) -> dict:
    """Export focused evidence context for reading one result's proof."""

    try:
        return require_workspace().export_result_reading_context(result_id)
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_source_slice(
    span_id: str | None = None,
    result_id: str | None = None,
    proof_id: str | None = None,
    context: int = 1,
) -> dict:
    """Return bounded source text around one span, result, or proof."""

    try:
        return require_workspace().get_source_slice(
            span_id=span_id,
            result_id=result_id,
            proof_id=proof_id,
            context=context,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
@_serialized_workspace_tool
def workspace_get_result_reading_path(
    result_id: str,
    recursive: bool = True,
) -> dict:
    """Return deterministic local reading paths for one result."""

    try:
        return require_workspace().get_result_reading_path(
            result_id,
            recursive=recursive,
        )
    except _WORKSPACE_TOOL_ERRORS as exc:
        raise ToolError(str(exc)) from exc


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


def _load_prepared_arxiv_project(project: ArxivProject) -> dict:
    global _current_graph
    global _current_path

    try:
        text = load_latex_project(project.main_file)
    except (OSError, ValueError) as exc:
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
def load_arxiv_paper(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
) -> dict:
    """Download an arXiv source project and build its theorem graph."""

    try:
        project = prepare_arxiv_project(
            arxiv_id,
            main_file,
            refresh,
        )
    except ArxivImportError as exc:
        raise ToolError(str(exc)) from exc

    return _load_prepared_arxiv_project(project)


@mcp.tool()
def load_arxiv_request(
    input: str,
    main_file: str | None = None,
    refresh: bool = False,
) -> dict:
    """Validate a raw arXiv request, then load it only if unambiguous."""

    validation = validate_arxiv_request_result(input)
    if validation["action"] != "safe_to_load" or validation["selected_id"] is None:
        raise ToolError(validation["message"])

    try:
        project = prepare_arxiv_project(
            validation["selected_id"],
            main_file,
            refresh,
        )
    except ArxivImportError as exc:
        raise ToolError(str(exc)) from exc

    result = _load_prepared_arxiv_project(project)
    result["validation"] = validation
    return result


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
def get_dependency_diagnostics(
    theorem_id: str,
    recursive: bool = False,
) -> dict:
    """Explain how dependencies were extracted for one theorem-like node."""

    graph = require_graph()

    try:
        return graph.dependency_diagnostics(
            theorem_id,
            recursive=recursive,
        )
    except KeyError as exc:
        raise ToolError(str(exc)) from exc


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


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="papergraph-mcp",
        description="Expose LaTeX theorem dependency graphs through MCP.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {distribution_version('papergraph-mcp')}",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "doctor",
        help="Print PaperGraph environment diagnostics as JSON.",
    )
    validate_parser = subparsers.add_parser(
        "validate-arxiv",
        help="Validate arXiv ID and URL inputs before loading a paper.",
    )
    validate_parser.add_argument("--id", dest="text_id")
    validate_parser.add_argument("--url")
    validate_request_parser = subparsers.add_parser(
        "validate-arxiv-request",
        help="Validate a raw arXiv request before loading a paper.",
    )
    validate_request_parser.add_argument("input")
    load_request_parser = subparsers.add_parser(
        "load-arxiv-request",
        help="Validate and load a raw arXiv request as JSON.",
    )
    load_request_parser.add_argument("input")
    load_request_parser.add_argument("--main-file")
    load_request_parser.add_argument("--refresh", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        _print_json(environment_diagnostics())
        return
    if args.command == "validate-arxiv":
        _print_json(
            validate_arxiv_input_result(
                text_id=args.text_id,
                url=args.url,
            )
        )
        return
    if args.command == "validate-arxiv-request":
        _print_json(validate_arxiv_request_result(args.input))
        return
    if args.command == "load-arxiv-request":
        validation = validate_arxiv_request_result(args.input)
        if validation["action"] != "safe_to_load" or validation["selected_id"] is None:
            _print_json(validation)
            raise SystemExit(1)
        try:
            _print_json(
                load_arxiv_request(
                    args.input,
                    main_file=args.main_file,
                    refresh=args.refresh,
                )
            )
        except ToolError as exc:
            _print_json(
                {
                    "status": "error",
                    "action": "inspect_error",
                    "selected_id": validation["selected_id"],
                    "message": str(exc),
                    "validation": validation,
                }
            )
            raise SystemExit(1) from exc
        return
    mcp.run()


if __name__ == "__main__":
    main()
