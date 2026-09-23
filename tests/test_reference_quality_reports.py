from papergraph.reading_report import _render_reference_search_candidates, _render_reference_search_boundaries
from papergraph.evidence_triage import build_evidence_triage


def test_saved_assessment_explanations_are_safe_markdown():
    data = {"searches": [{"candidates": [{"target": {"title": '<script>x</script> [click](https://evil)', "doi": '10.1000/`<img>'},
        "assessment": {"source_status": "review_required", "reason_codes": ["identifier_conflict"],
                       "auto_selection": {"eligible": False, "reason_codes": ["identifier_conflict"]}}}],
        "boundaries": [{"kind": "identifier_conflict", "message": "Review evidence", "next_actions": ["review_candidates"]}]}]}
    markdown = "\n".join(_render_reference_search_candidates(data) + _render_reference_search_boundaries(data))
    assert "<script>" not in markdown and "<img>" not in markdown
    assert "[click](" not in markdown
    assert "Source status:" in markdown and "Reason:" in markdown and "Next actions:" in markdown
    triage = build_evidence_triage({}, reference_searches=data)
    assert triage["scholarly_reference_search"]["next_actions"] == ["review_candidates"]
