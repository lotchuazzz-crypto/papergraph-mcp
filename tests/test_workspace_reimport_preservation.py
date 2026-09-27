"""A source refresh must not erase human reading and resolution work."""

from pathlib import Path

import fitz

from papergraph.project import load_project
from papergraph.workspace import Workspace


def _pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    for y, line in enumerate((
        "Theorem 1.1. Main result.",
        "Proof. By [17, Theorem 2.1].",
        "References",
        "[17] A. Author. Published target. Journal 2020.",
    ), start=1):
        page.insert_text((72, y * 22 + 50), line, fontsize=11)
    document.save(path)
    document.close()


def test_pdf_reimport_preserves_reading_and_resolution_state(tmp_path: Path):
    pdf = tmp_path / "source.pdf"
    _pdf(pdf)
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_pdf(pdf, "local:paper")
        result_id = workspace.list_results("local:paper")[0]["result_id"]
        session = workspace.create_reading_session("local:paper", "Keep my work", result_id)
        checkpoint = workspace.record_reading_checkpoint(
            session["session_id"], "result_id", result_id, "reviewed", "My summary", {"own": "evidence"}
        )
        note = workspace.add_reading_note(session["session_id"], "A hard-won insight")
        queue = workspace.create_reading_queue(result_id, "Keep my queue")
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]
        resolution = workspace.resolve_external_reference(
            "local:paper", blocked["blocked_id"], {"kind": "doi", "doi": "10.1000/example"}
        )
        workspace.reference_search_provider = lambda query: [{
            "provider": "crossref", "records": [{"doi": "10.1000/example", "title": "Published target"}]
        }]
        workspace.search_external_reference("local:paper", blocked["blocked_id"])
        assert workspace.list_external_reference_searches("local:paper")["searches"]

        workspace.import_pdf(pdf, "local:paper")

        saved_session = workspace.list_reading_sessions("local:paper")[0]
        assert saved_session["session_id"] == session["session_id"]
        assert saved_session["target_result_id"] == result_id
        summary = workspace.export_reading_session_summary(session["session_id"])
        assert any(item["note_id"] == note["note_id"] and item["text"] == "A hard-won insight"
                   for item in summary["latest_notes"])
        assert any(item["note_type"] == "warning" and "re-import" in item["text"]
                   for item in summary["latest_notes"])
        saved_checkpoint = next(item for item in summary["blocked_targets"]
                                if item["checkpoint_id"] == checkpoint["checkpoint_id"])
        assert saved_checkpoint["status"] == "blocked"
        assert saved_checkpoint["summary"] == "My summary"
        assert saved_checkpoint["evidence"]["reimport_review_required"] is True
        saved_queue = workspace.get_reading_queue(queue["queue_id"])
        assert saved_queue["queue"]["target_result_id"] == result_id
        assert all(item["evidence"]["reimport_review_required"] is True
                   for item in saved_queue["items"])
        saved_resolution = workspace.list_external_reference_resolutions("local:paper")["resolutions"][0]
        assert saved_resolution["resolution_id"] == resolution["resolution_id"]
        assert saved_resolution["source"]["review"]["reimport_review_required"] is True
        assert workspace.list_external_reference_searches("local:paper")["searches"] == []

        confirmed = workspace.resolve_external_reference(
            "local:paper", blocked["blocked_id"], {"kind": "doi", "doi": "10.1000/example"}
        )
        assert confirmed["resolution_id"] == resolution["resolution_id"]
        assert not confirmed["source"]["review"].get("reimport_review_required")
    finally:
        workspace.close()


def test_latex_reimport_preserves_reading_session(tmp_path: Path):
    project = load_project(Path(__file__).parent / "fixtures/workspace/paper_a/main.tex")
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_project("local:paper", "local", str(project.root_file), None, project)
        session = workspace.create_reading_session("local:paper", "Keep this session")
        workspace.import_project("local:paper", "local", str(project.root_file), None, project)
        assert workspace.list_reading_sessions("local:paper")[0]["session_id"] == session["session_id"]
        assert any(note["note_type"] == "warning" for note in
                   workspace.export_reading_session_summary(session["session_id"])["latest_notes"])
    finally:
        workspace.close()
