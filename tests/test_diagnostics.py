from papergraph.diagnostics import environment_diagnostics


def test_environment_diagnostics_reports_version_and_release_source():
    result = environment_diagnostics()

    assert result["package_name"] == "papergraph-mcp"
    assert result["version"] == "0.6.0"
    assert result["release_tag"] == "v0.6.0"
    assert (
        result["recommended_source"]
        == "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.0"
    )
    assert result["dependency_extraction_basis"] == "statement_explicit_latex_refs_only"
    assert isinstance(result["warnings"], list)


def test_environment_diagnostics_tolerates_missing_git(monkeypatch):
    import papergraph.diagnostics as diagnostics

    def fail(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(diagnostics.subprocess, "run", fail)

    result = environment_diagnostics()

    assert result["version"] == "0.6.0"
    assert result["git"] is None
    assert any("Git context unavailable" in warning for warning in result["warnings"])
