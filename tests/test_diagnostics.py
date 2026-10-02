from papergraph.diagnostics import environment_diagnostics


def test_environment_diagnostics_reports_candidate_and_stable_release_source():
    result = environment_diagnostics()

    assert result["package_name"] == "papergraph-mcp"
    assert result["version"] == "1.2.0.dev0"
    assert result["release_tag"] is None
    assert result['build_identity']['channel'] == 'development_candidate'
    assert (
        result["recommended_source"]
        == "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.7"
    )
    assert result["dependency_extraction_basis"] == "statement_explicit_latex_refs_only"
    assert isinstance(result["warnings"], list)


def test_diagnostics_distinguishes_statement_graph_proof_evidence_and_doi():
    result = environment_diagnostics()
    capabilities = result["dependency_capabilities"]
    assert capabilities["statement_graph"]["basis"] == result["dependency_extraction_basis"]
    assert "workspace_get_proof_dependencies" in capabilities["proof_local"]["tools"]
    assert capabilities["proof_local"]["complete_mathematical_dependencies"] is False
    assert result["paper_input_capabilities"]["doi_is_fulltext"] is False
    assert "local_pdf" in result["paper_input_capabilities"]["importable_sources"]


def test_environment_diagnostics_tolerates_missing_git(monkeypatch):
    import papergraph.diagnostics as diagnostics

    def fail(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(diagnostics.subprocess, "run", fail)

    result = environment_diagnostics()

    assert result["version"] == "1.2.0.dev0"
    assert result["git"] is None
    assert any("Git context unavailable" in warning for warning in result["warnings"])
