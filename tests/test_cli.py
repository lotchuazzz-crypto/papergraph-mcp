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
    assert capsys.readouterr().out == "papergraph-mcp 0.4.2\n"


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
