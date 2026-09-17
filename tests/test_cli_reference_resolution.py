import json
from pathlib import Path

import pytest

import papergraph.server as server
from papergraph.workspace import Workspace
from tests.test_workspace_reference_resolution import write_missing_reference_pdf


def create_missing_reference_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_missing_reference_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def blocked_id_for(workspace_path: Path) -> str:
    workspace = Workspace.open(workspace_path)
    try:
        return workspace.plan_external_imports_for_paper("local:paper")["blocked"][0][
            "blocked_id"
        ]
    finally:
        workspace.close()


def test_resolve_external_reference_cli_records_doi(tmp_path: Path, capsys):
    workspace_path = create_missing_reference_workspace(tmp_path)
    blocked_id = blocked_id_for(workspace_path)

    server.main(
        [
            "resolve-external-reference",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--blocked-id",
            blocked_id,
            "--doi",
            "10.1000/example",
            "--title",
            "Published target",
        ]
    )

    payload = read_json(capsys)
    assert payload["status"] == "resolved_not_imported"
    assert payload["target"]["doi"] == "10.1000/example"

    server.main(
        [
            "list-external-reference-resolutions",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
        ]
    )

    listed = read_json(capsys)
    assert listed["summary"]["resolved_not_imported_count"] == 1


def test_resolve_external_reference_cli_rejects_ambiguous_target(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_missing_reference_workspace(tmp_path)
    blocked_id = blocked_id_for(workspace_path)

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "resolve-external-reference",
                "--workspace",
                str(workspace_path),
                "--paper-id",
                "local:paper",
                "--blocked-id",
                blocked_id,
                "--doi",
                "10.1000/example",
                "--url",
                "https://publisher.example/paper",
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert "Exactly one reference target" in payload["message"]
