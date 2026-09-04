from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from papergraph.arxiv import ArxivDownloadError, ArxivProject


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def make_multifile_project(tmp_path: Path) -> ArxivProject:
    project = tmp_path / "project"
    sections = project / "sections"
    sections.mkdir(parents=True)
    main = project / "main.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        "\\input{sections/lemma}\n"
        "\\input{sections/theorem}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "lemma.tex").write_text(
        "\\begin{lemma}Base.\\label{lem:base}\\end{lemma}",
        encoding="utf-8",
    )
    (sections / "theorem.tex").write_text(
        "\\begin{theorem}By \\ref{lem:base}."
        "\\label{thm:result}\\end{theorem}",
        encoding="utf-8",
    )
    return ArxivProject("2401.12345", project, main, False)


def test_load_arxiv_paper_activates_downloaded_multifile_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = make_multifile_project(tmp_path)
    monkeypatch.setattr(server, "prepare_arxiv_project", lambda *args, **kwargs: project)

    result = server.load_arxiv_paper("arXiv:2401.12345")

    assert result == {
        "arxiv_id": "2401.12345",
        "path": str(project.main_file),
        "cached": False,
        "nodes": 2,
        "kinds": {"lemma": 1, "theorem": 1},
    }
    assert [node["id"] for node in server.list_theorems()] == [
        "lem:base",
        "thm:result",
    ]
    assert [node["id"] for node in server.get_dependencies("thm:result")] == [
        "lem:base"
    ]


def test_load_arxiv_paper_passes_options_to_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = make_multifile_project(tmp_path)
    received: dict[str, object] = {}

    def prepare(arxiv_id: str, main_file: str | None, refresh: bool):
        received.update(
            arxiv_id=arxiv_id,
            main_file=main_file,
            refresh=refresh,
        )
        return ArxivProject(
            project.arxiv_id,
            project.project_dir,
            project.main_file,
            True,
        )

    monkeypatch.setattr(server, "prepare_arxiv_project", prepare)

    result = server.load_arxiv_paper(
        "2401.12345",
        main_file="main.tex",
        refresh=True,
    )

    assert received == {
        "arxiv_id": "2401.12345",
        "main_file": "main.tex",
        "refresh": True,
    }
    assert result["cached"] is True


def test_arxiv_domain_error_becomes_tool_error(monkeypatch: pytest.MonkeyPatch):
    def fail(*args, **kwargs):
        raise ArxivDownloadError("download unavailable")

    monkeypatch.setattr(server, "prepare_arxiv_project", fail)

    with pytest.raises(ToolError, match="download unavailable"):
        server.load_arxiv_paper("2401.12345")


@pytest.mark.parametrize("failure", [OSError("cannot read"), ValueError("bad include")])
def test_arxiv_loader_error_becomes_tool_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
):
    project = make_multifile_project(tmp_path)
    monkeypatch.setattr(server, "prepare_arxiv_project", lambda *args, **kwargs: project)

    def fail(path: Path):
        raise failure

    monkeypatch.setattr(server, "load_latex_project", fail)

    with pytest.raises(ToolError, match=str(failure)):
        server.load_arxiv_paper("2401.12345")


def test_failed_arxiv_import_preserves_active_local_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    local = tmp_path / "local.tex"
    local.write_text(
        "\\newtheorem{lemma}{Lemma}\n"
        "\\begin{lemma}Local.\\label{lem:local}\\end{lemma}",
        encoding="utf-8",
    )
    server.load_paper(str(local))

    def fail(*args, **kwargs):
        raise ArxivDownloadError("download unavailable")

    monkeypatch.setattr(server, "prepare_arxiv_project", fail)

    with pytest.raises(ToolError):
        server.load_arxiv_paper("2401.12345")

    assert [node["id"] for node in server.list_theorems()] == ["lem:local"]
    assert server._current_path == local.resolve()


def test_missing_graph_message_mentions_both_load_tools():
    with pytest.raises(ToolError) as caught:
        server.require_graph()

    message = str(caught.value)
    assert "load_paper" in message
    assert "load_arxiv_paper" in message


def test_get_environment_diagnostics_returns_runtime_metadata(monkeypatch):
    monkeypatch.setattr(
        server,
        "environment_diagnostics",
        lambda: {
            "package_name": "papergraph-mcp",
            "version": "0.6.0",
            "release_tag": "v0.6.0",
            "recommended_source": (
                "git+https://github.com/lotchuazzz-crypto/"
                "papergraph-mcp.git@v0.6.0"
            ),
            "dependency_extraction_basis": "statement_explicit_latex_refs_only",
            "git": None,
            "warnings": [],
        },
    )

    assert server.get_environment_diagnostics()["release_tag"] == "v0.6.0"


def test_validate_arxiv_input_tool_reports_conflict():
    result = server.validate_arxiv_input(
        text_id="math/0307200",
        url="https://arxiv.org/abs/2609.01574",
    )

    assert result["status"] == "conflict"
    assert result["action"] == "ask_user_to_choose"
    assert result["selected_id"] is None


def test_validate_arxiv_request_tool_reports_markdown_conflict():
    result = server.validate_arxiv_request(
        "[math/0307200](https://arxiv.org/abs/2609.01574)"
    )

    assert result["status"] == "conflict"
    assert result["action"] == "ask_user_to_choose"
    assert result["selected_id"] is None
    assert result["normalized_ids"] == ["math/0307200", "2609.01574"]


def test_load_arxiv_request_loads_valid_request_and_includes_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = make_multifile_project(tmp_path)
    monkeypatch.setattr(server, "prepare_arxiv_project", lambda *args, **kwargs: project)

    result = server.load_arxiv_request("Please load arXiv:2401.12345")

    assert result["arxiv_id"] == "2401.12345"
    assert result["nodes"] == 2
    assert result["validation"]["status"] == "single_input"
    assert result["validation"]["selected_id"] == "2401.12345"
    assert [node["id"] for node in server.list_theorems()] == [
        "lem:base",
        "thm:result",
    ]


def test_load_arxiv_request_conflict_preserves_active_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    local = tmp_path / "local.tex"
    local.write_text(
        "\\newtheorem{lemma}{Lemma}\n"
        "\\begin{lemma}Local.\\label{lem:local}\\end{lemma}",
        encoding="utf-8",
    )
    server.load_paper(str(local))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("conflicting raw requests must not prepare a project")

    monkeypatch.setattr(server, "prepare_arxiv_project", fail_if_called)

    with pytest.raises(ToolError, match="multiple different arXiv IDs"):
        server.load_arxiv_request(
            "[math/0307200](https://arxiv.org/abs/2609.01574)"
        )

    assert [node["id"] for node in server.list_theorems()] == ["lem:local"]
    assert server._current_path == local.resolve()


def test_get_dependency_diagnostics_reports_single_paper_basis(tmp_path: Path):
    local = tmp_path / "local.tex"
    local.write_text(
        r"\begin{lemma}\label{lem:base}Base.\end{lemma}"
        r"\begin{theorem}\label{thm:main}"
        r"Uses \ref{lem:base} and \ref{missing}."
        r"\end{theorem}",
        encoding="utf-8",
    )
    server.load_paper(str(local))

    diagnostics = server.get_dependency_diagnostics("thm:main")

    assert diagnostics["extraction_basis"] == "statement_explicit_latex_refs_only"
    assert diagnostics["referenced_labels"] == ["lem:base", "missing"]
    assert diagnostics["resolved_labels"] == ["lem:base"]
    assert diagnostics["unresolved_labels"] == ["missing"]
    assert diagnostics["dependency_ids"] == ["lem:base"]
