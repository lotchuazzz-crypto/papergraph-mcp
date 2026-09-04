import json
from pathlib import Path

import fitz
import pytest

import papergraph.server as server
from papergraph.workspace import Workspace


def write_slice_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2.",
        "Remark 1.3. Extra comment.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def write_recursive_dependency_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.1. Base estimate.",
        "Proof. This is direct.",
        "Lemma 1.2. Bootstrap estimate.",
        "Proof. By Lemma 1.1.",
        "Theorem 1.3. Main result.",
        "Proof. By Lemma 1.2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def create_slice_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def create_recursive_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "recursive.pdf"
    write_recursive_dependency_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def test_export_reading_bundle_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_slice_workspace(tmp_path)

    server.main(
        [
            "export-reading-bundle",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["bridge_schema_version"] == "1"
    assert payload["paper"]["paper_id"] == "local:paper"
    assert payload["uri_map"]["paper_uri"] == "paper:local:paper"


def test_export_result_reading_context_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_slice_workspace(tmp_path)

    server.main(
        [
            "export-result-reading-context",
            "--workspace",
            str(workspace_path),
            "--result-id",
            "local:paper::pdf:theorem:1.1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["result_id"] == "local:paper::pdf:theorem:1.1"
    assert payload["proof"]["known"]["proof"]["proof_id"] == "local:paper::proof:1"


def test_get_source_slice_cli_prints_bounded_json(tmp_path: Path, capsys):
    workspace_path = create_slice_workspace(tmp_path)

    server.main(
        [
            "get-source-slice",
            "--workspace",
            str(workspace_path),
            "--proof-id",
            "local:paper::proof:1",
            "--context",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["selector"] == {
        "kind": "proof_id",
        "value": "local:paper::proof:1",
    }
    assert payload["bounded"] is True
    assert [item["role"] for item in payload["slices"]] == [
        "before",
        "anchor",
        "after",
    ]


def test_get_result_reading_path_cli_supports_direct_mode(tmp_path: Path, capsys):
    workspace_path = create_recursive_workspace(tmp_path)

    server.main(
        [
            "get-result-reading-path",
            "--workspace",
            str(workspace_path),
            "--result-id",
            "local:paper::pdf:theorem:1.3",
            "--direct",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert [node["result_id"] for node in payload["top_down"]] == [
        "local:paper::pdf:theorem:1.3"
    ]
    assert [node["result_id"] for node in payload["bottom_up"]] == [
        "local:paper::pdf:theorem:1.3"
    ]
    assert payload["edges"] == [
        {
            "source_result_id": "local:paper::pdf:theorem:1.3",
            "target_result_id": "local:paper::pdf:lemma:1.2",
            "relation": "uses_local_result",
        }
    ]


def test_get_source_slice_cli_returns_json_error_for_invalid_selector(
    tmp_path: Path,
    capsys,
):
    workspace_path = tmp_path / "workspace.sqlite3"
    workspace = Workspace.open(workspace_path)
    workspace.close()

    with pytest.raises(SystemExit) as caught:
        server.main(["get-source-slice", "--workspace", str(workspace_path)])

    assert caught.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["action"] == "inspect_error"
    assert payload["command"] == "get-source-slice"
    assert "Exactly one source slice selector" in payload["message"]
