import json
from pathlib import Path

import papergraph.server as server
from papergraph.workspace import Workspace
from tests.test_cli_reference_resolution import (
    blocked_id_for,
    create_missing_reference_workspace,
)


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_search_external_reference_cli_prints_json(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    workspace_path = create_missing_reference_workspace(tmp_path)
    blocked_id = blocked_id_for(workspace_path)
    seen = {}

    def fake_search(
        self,
        paper_id,
        requested_blocked_id,
        *,
        providers=None,
        max_candidates=10,
        refresh=False,
    ):
        seen.update(
            {
                "paper_id": paper_id,
                "blocked_id": requested_blocked_id,
                "providers": providers,
                "max_candidates": max_candidates,
                "refresh": refresh,
            }
        )
        return {
            "search_schema_version": 1,
            "search_run_id": "reference-search:test",
            "candidates": [],
            "summary": {"candidate_count": 0},
        }

    monkeypatch.setattr(Workspace, "search_external_reference", fake_search)

    server.main(
        [
            "search-external-reference",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--blocked-id",
            blocked_id,
            "--provider",
            "crossref",
            "--max-candidates",
            "3",
            "--refresh",
        ]
    )

    payload = read_json(capsys)
    assert payload["search_run_id"] == "reference-search:test"
    assert seen == {
        "paper_id": "local:paper",
        "blocked_id": blocked_id,
        "providers": ["crossref"],
        "max_candidates": 3,
        "refresh": True,
    }


def test_list_external_reference_searches_cli_prints_json(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    workspace_path = create_missing_reference_workspace(tmp_path)

    def fake_list(self, paper_id=None, blocked_id=None):
        return {
            "search_schema_version": 1,
            "scope": {"paper_id": paper_id, "blocked_id": blocked_id},
            "searches": [],
            "summary": {"search_run_count": 0},
        }

    monkeypatch.setattr(Workspace, "list_external_reference_searches", fake_list)

    server.main(
        [
            "list-external-reference-searches",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
        ]
    )

    payload = read_json(capsys)
    assert payload["scope"] == {"paper_id": "local:paper", "blocked_id": None}


def test_resolve_external_reference_candidate_cli_prints_json(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    workspace_path = create_missing_reference_workspace(tmp_path)
    blocked_id = blocked_id_for(workspace_path)
    seen = {}

    def fake_apply(
        self,
        paper_id,
        requested_blocked_id,
        candidate_id,
        *,
        import_target=False,
        artifact_dir=None,
        overwrite=False,
    ):
        seen.update(
            {
                "paper_id": paper_id,
                "blocked_id": requested_blocked_id,
                "candidate_id": candidate_id,
                "import_target": import_target,
                "artifact_dir": artifact_dir,
                "overwrite": overwrite,
            }
        )
        return {
            "candidate_resolution_schema_version": 1,
            "candidate": {"candidate_id": candidate_id},
            "resolution": {"status": "resolved_not_imported"},
        }

    monkeypatch.setattr(
        Workspace,
        "resolve_external_reference_candidate",
        fake_apply,
    )

    server.main(
        [
            "resolve-external-reference-candidate",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--blocked-id",
            blocked_id,
            "--candidate-id",
            "reference-candidate:test",
            "--import-target",
            "--overwrite",
            "--artifact-dir",
            "artifacts",
        ]
    )

    payload = read_json(capsys)
    assert payload["candidate"]["candidate_id"] == "reference-candidate:test"
    assert seen == {
        "paper_id": "local:paper",
        "blocked_id": blocked_id,
        "candidate_id": "reference-candidate:test",
        "import_target": True,
        "artifact_dir": "artifacts",
        "overwrite": True,
    }
