from pathlib import Path

from papergraph.graph import PaperGraph
from papergraph.parser import parse_file


SAMPLE = (
    Path(__file__).parent
    / "fixtures"
    / "sample.tex"
)


def build_graph() -> PaperGraph:
    return PaperGraph(
        parse_file(SAMPLE)
    )


def test_direct_dependencies():
    graph = build_graph()

    dependencies = graph.dependencies(
        "thm:main"
    )

    assert [
        node.id
        for node in dependencies
    ] == [
        "prop:key",
        "lem:vanishing",
    ]


def test_recursive_dependencies():
    graph = build_graph()

    dependencies = graph.dependencies(
        "thm:main",
        recursive=True,
    )

    ids = {
        node.id
        for node in dependencies
    }

    assert ids == {
        "prop:key",
        "lem:vanishing",
    }


def test_where_used():
    graph = build_graph()

    users = graph.where_used(
        "lem:vanishing"
    )

    assert {
        node.id
        for node in users
    } == {
        "prop:key",
        "thm:main",
    }