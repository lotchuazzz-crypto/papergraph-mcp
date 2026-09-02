from pathlib import Path

import pytest

import papergraph.server as server


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "workspace"


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_readme_local_fixture_walkthrough_reports_unresolved_local_targets(
    tmp_path: Path,
):
    """The documented local sequence must not imply local citation resolution."""

    server.open_workspace(str(tmp_path / "papergraph-demo.sqlite3"))
    for directory, paper_id in (
        ("paper_a", "local:paper-a"),
        ("paper_b", "local:paper-b"),
        ("paper_c", "local:paper-c"),
    ):
        server.workspace_add_local_paper(
            str(FIXTURE_ROOT / directory / "main.tex"), paper_id
        )

    assert [paper["paper_id"] for paper in server.workspace_list_papers()] == [
        "local:paper-a",
        "local:paper-b",
        "local:paper-c",
    ]
    assert [result["global_id"] for result in server.workspace_search_theorems(
        "fixed point", limit=10
    )] == [
        "local:paper-a::thm:main",
        "local:paper-b::thm:main",
        "local:paper-c::thm:main",
    ]

    outgoing = server.workspace_get_citations(
        "local:paper-a", direction="outgoing", include_unresolved=True
    )
    assert [row["citation_key"] for row in outgoing] == [
        "absent",
        "missing",
        "paper-b",
    ]
    assert outgoing[2]["cited_arxiv_id"] == "2401.12346"
    assert outgoing[2]["target_paper_id"] is None
    assert outgoing[2]["resolution_status"] == "resolved_candidate"
    assert server.workspace_get_citations(
        "local:paper-b", direction="incoming"
    ) == []

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "does not resolve to `local:paper-b`" in readme
    assert "`target_paper_id: null`" in readme
    assert "`workspace_add_arxiv_paper`" in readme
    assert "cited arXiv ID is imported" in readme
