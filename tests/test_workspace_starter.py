import json
from pathlib import Path

import pytest

import papergraph.starter as starter
from papergraph.arxiv import ArxivProject
from papergraph.workspace import Workspace
from tests.test_workspace_cross_paper_reading_plan import insert_empty_paper
from tests.test_workspace_paper_map import import_paper_map_pdf
from tests.test_workspace_reading_queue import write_queue_pdf


def write_minimal_tex(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\newtheorem{theorem}{Theorem}",
                r"\begin{document}",
                r"\begin{theorem}\label{main}",
                "Main starter theorem.",
                r"\end{theorem}",
                r"\begin{proof}",
                "Direct proof.",
                r"\end{proof}",
                r"\end{document}",
            ]
        ),
        encoding="utf-8",
    )


def test_plan_starter_project_describes_artifacts_without_writing(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    try:
        plan = workspace.plan_starter_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[
                {
                    "kind": "local_tex",
                    "path": tmp_path / "paper-a" / "main.tex",
                    "paper_id": "local:paper-a",
                }
            ],
            project_title="Example reading project",
            focus="fixed point",
            create_queue=False,
            create_session=False,
        )

        assert plan["starter_schema_version"] == 1
        assert plan["status"] == "ready"
        assert plan["action"] == "bootstrap_reading_project"
        assert plan["workspace_path"] == str(tmp_path / "workspace.sqlite3")
        assert plan["artifact_dir"] == str(artifact_dir)
        assert plan["project_title"] == "Example reading project"
        assert plan["planned_papers"] == [
            {
                "kind": "local_tex",
                "paper_id": "local:paper-a",
                "path": str(tmp_path / "paper-a" / "main.tex"),
            }
        ]
        assert [
            artifact["kind"] for artifact in plan["planned_artifacts"]
        ] == ["starter_summary", "starter_manifest", "reading_report"]
        assert plan["planned_state_changes"] == [
            {"kind": "open_workspace", "path": str(tmp_path / "workspace.sqlite3")},
            {"kind": "add_paper", "paper_id": "local:paper-a"},
        ]
        assert not artifact_dir.exists()
    finally:
        workspace.close()


def test_plan_starter_project_rejects_duplicate_paper_ids(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(ValueError, match="paper_ids must be distinct"):
            workspace.plan_starter_project(
                workspace_path=tmp_path / "workspace.sqlite3",
                artifact_dir=tmp_path / "artifacts",
                papers=[
                    {"kind": "pdf", "path": tmp_path / "a.pdf", "paper_id": "local:a"},
                    {"kind": "pdf", "path": tmp_path / "b.pdf", "paper_id": "local:a"},
                ],
            )
    finally:
        workspace.close()


def test_plan_starter_project_requires_explicit_local_ids(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(ValueError, match="paper_id is required for pdf inputs"):
            workspace.plan_starter_project(
                workspace_path=tmp_path / "workspace.sqlite3",
                artifact_dir=tmp_path / "artifacts",
                papers=[{"kind": "pdf", "path": tmp_path / "paper.pdf"}],
            )
    finally:
        workspace.close()


def test_bootstrap_reading_project_writes_starter_artifacts(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    try:
        import_paper_map_pdf(workspace, tmp_path)

        result = workspace.bootstrap_reading_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[],
            project_title="Bootstrap example",
            create_queue=False,
            create_session=False,
        )

        assert result["starter_schema_version"] == 1
        assert result["status"] == "written"
        assert result["workspace"]["paper_count"] == 1
        assert [artifact["kind"] for artifact in result["artifacts"]] == [
            "starter_summary",
            "starter_manifest",
            "reading_report",
        ]
        start_here = artifact_dir / "START_HERE.md"
        manifest_path = artifact_dir / "papergraph-starter-manifest.json"
        assert start_here.exists()
        assert manifest_path.exists()
        markdown = start_here.read_text(encoding="utf-8")
        assert markdown.startswith("# PaperGraph Reading Project: Bootstrap example")
        assert "## Papers Loaded" in markdown
        assert "## Evidence Boundaries" in markdown
        assert "PaperGraph does not verify proofs." in markdown
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["starter_schema_version"] == 1
        assert manifest["paper_ids"] == ["local:paper"]
        assert all("created_at" not in json.dumps(value) for value in manifest.values())
        assert any(
            command.startswith("papergraph-mcp get-paper-map --workspace")
            for command in manifest["next_commands"]
        )
    finally:
        workspace.close()


def test_bootstrap_reading_project_writes_cross_paper_plan(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    try:
        import_paper_map_pdf(workspace, tmp_path)
        insert_empty_paper(workspace, "local:empty")

        result = workspace.bootstrap_reading_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[],
            create_queue=False,
            create_session=False,
        )

        assert any(
            artifact["kind"] == "cross_paper_reading_plan"
            for artifact in result["artifacts"]
        )
        assert (artifact_dir / "cross-paper-reading-plan.md").exists()
    finally:
        workspace.close()


def test_bootstrap_reading_project_imports_explicit_local_inputs(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    tex = tmp_path / "paper-a" / "main.tex"
    pdf = tmp_path / "paper-b.pdf"
    write_minimal_tex(tex)
    write_queue_pdf(pdf)
    try:
        result = workspace.bootstrap_reading_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[
                {"kind": "local_tex", "path": tex, "paper_id": "local:tex"},
                {"kind": "pdf", "path": pdf, "paper_id": "local:pdf"},
            ],
            create_queue=False,
            create_session=False,
        )

        assert result["workspace"]["paper_count"] == 2
        assert [paper["paper_id"] for paper in result["papers"]] == [
            "local:pdf",
            "local:tex",
        ]
        assert workspace.get_paper("local:tex")["source_type"] == "local"
        assert workspace.get_paper("local:pdf")["source_type"] == "pdf"
    finally:
        workspace.close()


def test_bootstrap_reading_project_rejects_existing_artifacts_without_overwrite(
    tmp_path: Path,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "START_HERE.md").write_text("old", encoding="utf-8")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        with pytest.raises(ValueError, match="already exists"):
            workspace.bootstrap_reading_project(
                workspace_path=tmp_path / "workspace.sqlite3",
                artifact_dir=artifact_dir,
                papers=[],
                create_queue=False,
                create_session=False,
            )
    finally:
        workspace.close()


def test_bootstrap_reading_project_can_create_queue_and_session(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    try:
        import_paper_map_pdf(workspace, tmp_path)

        result = workspace.bootstrap_reading_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[],
            create_queue=True,
            create_session=True,
        )

        assert result["reading_queue"]["target_result_id"].startswith(
            "local:paper::"
        )
        assert result["reading_session"]["target_result_id"] == result[
            "reading_queue"
        ]["target_result_id"]
    finally:
        workspace.close()


def test_plan_starter_project_blocks_ambiguous_arxiv_request(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        plan = workspace.plan_starter_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=tmp_path / "artifacts",
            papers=[
                {
                    "kind": "arxiv",
                    "input": "[math/0307200](https://arxiv.org/abs/2609.01574)",
                }
            ],
        )

        assert plan["status"] == "blocked"
        assert plan["action"] == "ask_user_to_choose"
        assert plan["planned_artifacts"] == []
        assert plan["blocking_issues"][0]["kind"] == "arxiv_conflict"
    finally:
        workspace.close()


def test_bootstrap_reading_project_imports_arxiv_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    artifact_dir = tmp_path / "artifacts"
    tex = tmp_path / "arxiv" / "main.tex"
    write_minimal_tex(tex)

    def prepare(arxiv_id: str, main_file: str | None, refresh: bool):
        assert arxiv_id == "2401.12345"
        assert main_file is None
        assert refresh is False
        return ArxivProject("2401.12345", tex.parent, tex, True)

    monkeypatch.setattr(starter, "prepare_arxiv_project", prepare)
    try:
        result = workspace.bootstrap_reading_project(
            workspace_path=tmp_path / "workspace.sqlite3",
            artifact_dir=artifact_dir,
            papers=[{"kind": "arxiv", "input": "2401.12345"}],
            create_queue=False,
            create_session=False,
        )

        assert result["workspace"]["paper_count"] == 1
        assert workspace.get_paper("arxiv:2401.12345")["source_type"] == "arxiv"
    finally:
        workspace.close()
