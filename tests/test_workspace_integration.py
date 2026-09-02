from pathlib import Path

from papergraph.project import load_project
from papergraph.workspace import Workspace


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "workspace"


def import_fixture_papers(workspace: Workspace) -> None:
    for directory, paper_id, source_type, source_ref, source_version in (
        (
            "paper_a",
            "arxiv:2401.12345",
            "arxiv",
            "2401.12345",
            "v1",
        ),
        (
            "paper_b",
            "arxiv:2401.12346",
            "arxiv",
            "2401.12346",
            "v1",
        ),
        (
            "paper_c",
            "arxiv:2401.12347",
            "arxiv",
            "2401.12347",
            "v1",
        ),
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
    outgoing_citations = {
        paper_id: workspace.get_citations(paper_id, "outgoing")
        for paper_id in (
            "arxiv:2401.12345",
            "arxiv:2401.12346",
            "arxiv:2401.12347",
        )
    }
    assert {
        paper_id: [row["citation_key"] for row in rows]
        for paper_id, rows in outgoing_citations.items()
    } == {
        "arxiv:2401.12345": ["absent", "missing", "paper-b"],
        "arxiv:2401.12346": ["paper-c"],
        "arxiv:2401.12347": ["paper-a"],
    }
    citations = {
        paper_id: {
            row["citation_key"]: row
            for row in rows
        }
        for paper_id, rows in outgoing_citations.items()
    }
    assert (
        citations["arxiv:2401.12345"]["paper-b"]["target_paper_id"],
        citations["arxiv:2401.12345"]["paper-b"]["resolution_status"],
    ) == (
        "arxiv:2401.12346",
        "resolved_candidate",
    )
    assert (
        citations["arxiv:2401.12346"]["paper-c"]["target_paper_id"],
        citations["arxiv:2401.12346"]["paper-c"]["resolution_status"],
    ) == (
        "arxiv:2401.12347",
        "resolved_candidate",
    )
    assert (
        citations["arxiv:2401.12347"]["paper-a"]["target_paper_id"],
        citations["arxiv:2401.12347"]["paper-a"]["resolution_status"],
    ) == (
        "arxiv:2401.12345",
        "resolved_candidate",
    )
    missing = citations["arxiv:2401.12345"]["missing"]
    assert (missing["target_paper_id"], missing["resolution_status"]) == (
        None,
        "missing_bib_entry",
    )
    absent = citations["arxiv:2401.12345"]["absent"]
    assert (
        absent["cited_arxiv_id"],
        absent["target_paper_id"],
        absent["resolution_status"],
    ) == (
        "2401.99999",
        None,
        "resolved_candidate",
    )
    before = {
        "papers": workspace.list_papers(),
        "search": workspace.search_theorems("fixed point"),
        "citations": {
            paper_id: workspace.get_citations(paper_id, "outgoing")
            for paper_id in (
                "arxiv:2401.12345",
                "arxiv:2401.12346",
                "arxiv:2401.12347",
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
            "arxiv:2401.12345::thm:main",
            "arxiv:2401.12346::thm:main",
            "arxiv:2401.12347::thm:main",
        }
    finally:
        reopened.close()
