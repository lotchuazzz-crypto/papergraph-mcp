import json

import pytest

import papergraph.server as server


def fail_if_mcp_runs() -> None:
    raise AssertionError("MCP server must not start for informational options")


def test_version_prints_distribution_version_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    with pytest.raises(SystemExit) as caught:
        server.main(["--version"])

    assert caught.value.code == 0
    assert capsys.readouterr().out == "papergraph-mcp 0.6.0\n"


def test_help_describes_theorem_dependency_server_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    with pytest.raises(SystemExit) as caught:
        server.main(["--help"])

    assert caught.value.code == 0
    output = capsys.readouterr().out
    assert "papergraph-mcp" in output
    assert "theorem dependency" in output


def test_no_arguments_starts_mcp_once(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    def record_run() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(server.mcp, "run", record_run)

    server.main([])

    assert calls == 1


def test_unknown_argument_is_rejected_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    with pytest.raises(SystemExit) as caught:
        server.main(["--unknown"])

    assert caught.value.code == 2
    assert "unrecognized arguments: --unknown" in capsys.readouterr().err


def test_doctor_prints_json_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)
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

    server.main(["doctor"])

    assert json.loads(capsys.readouterr().out)["version"] == "0.6.0"


def test_validate_arxiv_cli_prints_conflict_json_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    server.main(
        [
            "validate-arxiv",
            "--id",
            "math/0307200",
            "--url",
            "https://arxiv.org/abs/2609.01574",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "conflict"
    assert payload["action"] == "ask_user_to_choose"
    assert payload["selected_id"] is None


def test_validate_arxiv_request_cli_prints_conflict_json_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    server.main(
        [
            "validate-arxiv-request",
            "[math/0307200](https://arxiv.org/abs/2609.01574)",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "conflict"
    assert payload["action"] == "ask_user_to_choose"
    assert payload["selected_id"] is None
    assert payload["normalized_ids"] == ["math/0307200", "2609.01574"]


def test_load_arxiv_request_cli_stops_on_conflict_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "load-arxiv-request",
                "[math/0307200](https://arxiv.org/abs/2609.01574)",
            ]
        )

    assert caught.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "conflict"
    assert payload["action"] == "ask_user_to_choose"
    assert payload["selected_id"] is None


def test_load_arxiv_request_cli_prints_loaded_json_without_starting_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(server.mcp, "run", fail_if_mcp_runs)

    def load(input: str, main_file: str | None = None, refresh: bool = False) -> dict:
        return {
            "arxiv_id": "2609.02842",
            "path": "paper.tex",
            "cached": False,
            "nodes": 1,
            "kinds": {"theorem": 1},
            "main_file": main_file,
            "refresh": refresh,
            "validation": {
                "status": "single_input",
                "selected_id": "2609.02842",
            },
        }

    monkeypatch.setattr(server, "load_arxiv_request", load)

    server.main(
        [
            "load-arxiv-request",
            "https://arxiv.org/abs/2609.02842",
            "--main-file",
            "paper.tex",
            "--refresh",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["arxiv_id"] == "2609.02842"
    assert payload["main_file"] == "paper.tex"
    assert payload["refresh"] is True
    assert payload["validation"]["selected_id"] == "2609.02842"
