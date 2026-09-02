from pathlib import Path

from papergraph.project import load_project
from papergraph.workspace import Workspace


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "workspace"


def import_fixture_papers(workspace: Workspace) -> None:
    for directory, paper_id, source_type, source_ref, source_version in (
        ("paper_a", "local:paper-a", "local", "paper_a/main.tex", None),
        (
            "paper_b",
            "arxiv:2401.12345",
            "arxiv",
            "2401.12345",
            "v1",
        ),
        ("paper_c", "local:paper-c", "local", "paper_c/main.tex", None),
    ):
        workspace.import_project(
            paper_id,
            source_type,
            source_ref,
            source_version,
            load_project(FIXTURE_ROOT / directory / "main.tex"),
        )


def test_three_paper_graph_survives_reopen(tmp_path):
    path = tmp_path / "knowledge.sqlite3"
    workspace = Workspace.open(path)
    import_fixture_papers(workspace)
    assert [
        row["citation_key"]
        for row in workspace.get_citations("local:paper-a", "outgoing")
    ] == ["missing", "paper-b"]
    assert workspace.get_citations("local:paper-a", "outgoing") == [
        {
            "source_paper_id": "local:paper-a",
            "citation_key": "missing",
            "command": "cite",
            "source_file": "main.tex",
            "bib_file": None,
            "bib_entry_type": None,
            "cited_arxiv_id": None,
            "cited_version": None,
            "target_paper_id": None,
            "resolution_status": "missing_bib_entry",
        },
        {
            "source_paper_id": "local:paper-a",
            "citation_key": "paper-b",
            "command": "cite",
            "source_file": "main.tex",
            "bib_file": "refs.bib",
            "bib_entry_type": "article",
            "cited_arxiv_id": "2401.12345",
            "cited_version": None,
            "target_paper_id": "arxiv:2401.12345",
            "resolution_status": "resolved_candidate",
        },
    ]
    assert [
        row["citation_key"]
        for row in workspace.get_citations("arxiv:2401.12345", "outgoing")
    ] == ["paper-c"]
    assert [
        row["citation_key"]
        for row in workspace.get_citations("local:paper-c", "outgoing")
    ] == ["paper-a"]
    absent = workspace.get_citations("arxiv:2401.12345", "outgoing")[0]
    assert (
        absent["bib_file"],
        absent["cited_arxiv_id"],
        absent["target_paper_id"],
        absent["resolution_status"],
    ) == ("refs.bib", "2401.99999", None, "resolved_candidate")
    before = {
        "papers": workspace.list_papers(),
        "search": workspace.search_theorems("fixed point"),
        "citations": {
            paper_id: workspace.get_citations(paper_id, "outgoing")
            for paper_id in (
                "local:paper-a",
                "arxiv:2401.12345",
                "local:paper-c",
            )
        },
    }
    workspace.close()

    reopened = Workspace.open(path)
    try:
        assert reopened.list_papers() == before["papers"]
        assert reopened.search_theorems("fixed point") == before["search"]
        assert {
            paper_id: reopened.get_citations(paper_id, "outgoing")
            for paper_id in before["citations"]
        } == before["citations"]
        assert {
            item["global_id"]
            for item in reopened.search_theorems("theorem")
        } == {
            "local:paper-a::thm:main",
            "arxiv:2401.12345::thm:main",
            "local:paper-c::thm:main",
        }
    finally:
        reopened.close()
