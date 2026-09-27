"""Regression cases for v1.1.6's input and provider boundaries."""

from pathlib import Path

import pytest

from papergraph.reference_assessment import rank_candidates_v2
from papergraph.reference_expansion_policy import validate_policy
from papergraph.reference_identity import normalize_identifier
from papergraph.reference_query import build_query_v2
from papergraph.workspace import Workspace


def test_uppercase_doi_resolver_url_remains_exact_identity():
    identifier = normalize_identifier("HTTPS://DOI.ORG/10.1000/ABC", "doi")
    assert identifier["canonical"] == "10.1000/abc"
    assert identifier["exact_eligible"] is True
    query = build_query_v2({"evidence": [{
        "kind": "bibliography_entry", "raw_text": "See HTTPS://DOI.ORG/10.1000/ABC"
    }]})
    assert query["identifier_hints"][0]["identity"] == "doi:10.1000/abc"
    assert query["identifier_hints"][0]["exact_eligible"] is True


def test_unserializable_provider_record_does_not_discard_valid_sibling():
    result = rank_candidates_v2(
        {"identifier_hints": [], "title_hint": None, "author_hints": [], "year_hint": None},
        [{"provider": "crossref", "records": [
            {"title": "Valid result", "year": "2020"},
            {"title": "Broken result", "extra": object()},
        ]}],
    )
    assert [candidate["target"]["title"] for candidate in result["candidates"]] == ["Valid result"]
    assert result["provider_outcomes"] == [{"provider": "crossref", "outcome": "partial"}]


def test_provider_elements_raise_actionable_validation_error(tmp_path: Path):
    with pytest.raises(ValueError, match="providers"):
        validate_policy({"providers": [{}]})
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(ValueError, match="providers"):
            workspace.search_external_reference("local:missing", "missing", providers=[{}])
    finally:
        workspace.close()
