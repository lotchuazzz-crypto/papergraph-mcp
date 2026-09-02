import sqlite3
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from papergraph.arxiv import ArxivDownloadError, ArxivProject
from papergraph.workspace import WorkspaceError


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def make_paper(tmp_path: Path, name: str, body: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    main = root / "main.tex"
    main.write_text(body, encoding="utf-8")
    return main


@pytest.mark.parametrize(
    "call",
    [
        lambda: server.workspace_add_local_paper("paper.tex", "local:paper"),
        lambda: server.workspace_add_arxiv_paper("2401.12345"),
        server.workspace_list_papers,
        lambda: server.workspace_get_paper("local:paper"),
        lambda: server.workspace_search_theorems("result"),
        lambda: server.workspace_get_dependencies("local:paper::thm:x"),
        lambda: server.workspace_get_citations("local:paper"),
    ],
)
def test_workspace_tools_report_missing_workspace(call):
    with pytest.raises(ToolError, match="open_workspace"):
        call()


def test_open_workspace_returns_exact_payload(tmp_path: Path):
    database = tmp_path / "nested" / "workspace.sqlite3"

    assert server.open_workspace(str(database)) == {
        "path": str(database.resolve()),
        "schema_version": 1,
        "papers": 0,
        "theorems": 0,
    }


def test_failed_workspace_open_preserves_active_workspace(tmp_path: Path):
    server.open_workspace(str(tmp_path / "good.sqlite3"))
    future = tmp_path / "future.sqlite3"
    with sqlite3.connect(future) as connection:
        connection.execute(
            "CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO workspace_meta VALUES ('schema_version', '2')"
        )

    with pytest.raises(ToolError, match="schema version 2"):
        server.open_workspace(str(future))

    assert server.workspace_list_papers() == []
    assert server.require_workspace().path == (tmp_path / "good.sqlite3").resolve()


def test_workspace_local_import_and_all_query_payloads(tmp_path: Path):
    main = make_paper(
        tmp_path,
        "paper-a",
        r"\title{Paper A}\author{Ada Lovelace}"
        r"\begin{lemma}\label{lem:base}Compact base.\end{lemma}"
        r"\begin{theorem}\label{thm:main}Uses \ref{lem:base}.\end{theorem}",
    )
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    imported = server.workspace_add_local_paper(str(main), " local:paper-a ")

    assert imported["paper_id"] == "local:paper-a"
    assert imported["source_type"] == "local"
    assert imported["source_ref"] == str(main.resolve())
    assert imported["source_version"] is None
    assert imported["title"] == "Paper A"
    assert imported["authors"] == ["Ada Lovelace"]
    assert imported["main_file"] == "main.tex"
    assert imported["theorem_count"] == 2
    assert imported["citation_count"] == 0
    assert imported["unresolved_citation_count"] == 0
    assert server.workspace_list_papers() == [
        {key: value for key, value in imported.items() if key != "kinds"}
    ]
    assert imported["kinds"] == {"lemma": 1, "theorem": 1}
    assert server.workspace_get_paper("local:paper-a") == imported
    assert server.workspace_search_theorems(
        "compact", paper_id="local:paper-a", kind="lemma", limit=3
    ) == [
        {
            "global_id": "local:paper-a::lem:base",
            "paper_id": "local:paper-a",
            "local_id": "lem:base",
            "kind": "lemma",
            "title": None,
            "source_file": "main.tex",
            "excerpt": r"\label{lem:base}Compact base.",
        }
    ]
    assert server.workspace_get_dependencies(
        "local:paper-a::thm:main", recursive=True
    ) == [
        {
            "global_id": "local:paper-a::lem:base",
            "paper_id": "local:paper-a",
            "local_id": "lem:base",
            "kind": "lemma",
            "title": None,
            "label": "lem:base",
            "source_file": "main.tex",
            "refs": [],
        }
    ]
    assert server.workspace_get_citations(
        "local:paper-a", direction="outgoing", include_unresolved=False
    ) == []


def test_workspace_arxiv_import_passes_options_and_uses_canonical_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    main = make_paper(
        tmp_path,
        "arxiv-project",
        r"\begin{theorem}\label{thm:x}Result.\end{theorem}",
    )
    received: dict[str, object] = {}

    def prepare(arxiv_id: str, main_file: str | None, refresh: bool):
        received.update(arxiv_id=arxiv_id, main_file=main_file, refresh=refresh)
        return ArxivProject("2401.12345v3", main.parent, main, True)

    monkeypatch.setattr(server, "prepare_arxiv_project", prepare)
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    imported = server.workspace_add_arxiv_paper(
        "arXiv:2401.12345v3", main_file="main.tex", refresh=True
    )

    assert received == {
        "arxiv_id": "arXiv:2401.12345v3",
        "main_file": "main.tex",
        "refresh": True,
    }
    assert imported["paper_id"] == "arxiv:2401.12345"
    assert imported["source_type"] == "arxiv"
    assert imported["source_ref"] == "2401.12345"
    assert imported["source_version"] == "v3"


def test_workspace_state_is_independent_from_single_paper_state(tmp_path: Path):
    workspace_paper = make_paper(
        tmp_path,
        "workspace-paper",
        r"\begin{lemma}\label{lem:workspace}Workspace.\end{lemma}",
    )
    single = make_paper(
        tmp_path,
        "single-paper",
        r"\begin{theorem}\label{thm:single}Single.\end{theorem}",
    )
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))
    server.workspace_add_local_paper(str(workspace_paper), "local:paper-a")

    server.load_paper(str(single))

    assert server.workspace_list_papers()[0]["paper_id"] == "local:paper-a"
    assert [item["id"] for item in server.list_theorems()] == ["thm:single"]


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: server.workspace_get_paper("local:missing"), "Unknown paper"),
        (lambda: server.workspace_search_theorems("   "), "query"),
        (lambda: server.workspace_search_theorems("x", limit=True), "limit"),
        (lambda: server.workspace_get_dependencies("bad"), "global theorem"),
        (
            lambda: server.workspace_get_citations("local:missing", direction="sideways"),
            "direction",
        ),
    ],
)
def test_workspace_domain_errors_become_tool_errors(tmp_path: Path, call, message):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match=message):
        call()


def test_workspace_local_import_validates_paper_id(tmp_path: Path):
    main = make_paper(tmp_path, "paper", "No theorem.")
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Invalid paper id"):
        server.workspace_add_local_paper(str(main), "bad")


def test_arxiv_domain_error_becomes_workspace_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    def fail(*args, **kwargs):
        raise ArxivDownloadError("download unavailable")

    monkeypatch.setattr(server, "prepare_arxiv_project", fail)
    with pytest.raises(ToolError, match="download unavailable"):
        server.workspace_add_arxiv_paper("2401.12345")


def test_failed_import_preserves_workspace_and_single_paper_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    stored = make_paper(
        tmp_path,
        "stored",
        r"\begin{lemma}\label{lem:stored}Stored.\end{lemma}",
    )
    single = make_paper(
        tmp_path,
        "single",
        r"\begin{theorem}\label{thm:single}Single.\end{theorem}",
    )
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))
    server.workspace_add_local_paper(str(stored), "local:stored")
    server.load_paper(str(single))

    def fail(*args, **kwargs):
        raise WorkspaceError("import failed")

    monkeypatch.setattr(server.require_workspace(), "import_project", fail)
    with pytest.raises(ToolError, match="import failed"):
        server.workspace_add_local_paper(str(stored), "local:replacement")

    assert [paper["paper_id"] for paper in server.workspace_list_papers()] == [
        "local:stored"
    ]
    assert [item["id"] for item in server.list_theorems()] == ["thm:single"]


def test_workspace_adapters_do_not_catch_programming_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    def fail():
        raise RuntimeError("programming bug")

    monkeypatch.setattr(server.require_workspace(), "list_papers", fail)
    with pytest.raises(RuntimeError, match="programming bug"):
        server.workspace_list_papers()
