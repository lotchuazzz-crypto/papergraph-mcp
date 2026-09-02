from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from papergraph import server
from papergraph.graph import PaperGraph
from papergraph.loader import load_latex_project
from papergraph.parser import parse_latex


PROJECT = (
    Path(__file__).parent
    / "fixtures"
    / "multifile"
    / "main.tex"
)


def test_multifile_project_builds_cross_file_graph():
    nodes = parse_latex(load_latex_project(PROJECT))
    graph = PaperGraph(nodes)

    assert [node.id for node in nodes] == [
        "lem:base",
        "thm:result",
    ]
    assert [
        node.id
        for node in graph.dependencies("thm:result")
    ] == ["lem:base"]


def test_mcp_load_paper_loads_the_complete_project():
    result = server.load_paper(str(PROJECT))

    assert result["nodes"] == 2
    assert result["kinds"] == {
        "lemma": 1,
        "theorem": 1,
    }


def test_mcp_load_paper_translates_missing_include_error(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    main.write_text("\\input{missing}", encoding="utf-8")

    with pytest.raises(
        ToolError,
        match="missing[.]tex",
    ):
        server.load_paper(str(main))
