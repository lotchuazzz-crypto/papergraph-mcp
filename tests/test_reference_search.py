from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from papergraph.reference_search import (
    build_reference_search_query,
    rank_reference_candidates,
)
from papergraph.reference_providers.arxiv import ArxivReferenceProvider
from papergraph.reference_providers.crossref import CrossrefReferenceProvider
from papergraph.reference_providers.openalex import OpenAlexReferenceProvider
from papergraph.workspace import Workspace


def write_search_source_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Theorem 1.1. Main result.",
        "Proof. By [17, Theorem 2.1].",
        "References",
        "[17] A. Author and B. Writer. Published target. Journal of Examples 2020.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def import_search_source_pdf(workspace: Workspace, tmp_path: Path) -> dict:
    pdf = tmp_path / "source.pdf"
    write_search_source_pdf(pdf)
    workspace.import_pdf(pdf, "local:paper")
    return workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]


def provider_result(
    provider: str,
    *,
    records: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "provider": provider,
        "records": records or [],
        "warnings": warnings or [],
    }


class FakeResponse:
    def __init__(self, payload=None, text: str = ""):
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url: str, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def test_rank_reference_candidates_prefers_published_metadata_over_arxiv_only():
    query = {
        "citation_keys": ["17"],
        "raw_citation_texts": ["[17, Theorem 2.1]"],
        "raw_bibliography_text": (
            "[17] A. Author and B. Writer. Published target. "
            "Journal of Examples 2020."
        ),
        "title_hint": "Published target",
        "author_hints": ["A. Author", "B. Writer"],
        "year_hint": "2020",
    }

    ranked = rank_reference_candidates(
        query,
        [
            provider_result(
                "crossref",
                records=[
                    {
                        "kind": "doi",
                        "doi": "10.1000/example",
                        "title": "Published target",
                        "authors": ["A. Author", "B. Writer"],
                        "year": "2020",
                        "venue": "Journal of Examples",
                        "url": "https://doi.org/10.1000/example",
                    }
                ],
            ),
            provider_result(
                "arxiv",
                records=[
                    {
                        "kind": "arxiv",
                        "arxiv_id": "2401.12345",
                        "title": "A related target",
                        "authors": ["A. Author"],
                        "year": "2019",
                    }
                ],
            ),
        ],
    )

    assert ranked["summary"]["candidate_count"] == 2
    assert ranked["candidates"][0]["target"]["kind"] == "doi"
    assert ranked["candidates"][0]["target"]["doi"] == "10.1000/example"
    assert ranked["candidates"][0]["confidence"] == "strong"
    assert "title_exact_match" in ranked["candidates"][0]["evidence"]
    assert ranked["candidates"][0]["score"] > ranked["candidates"][1]["score"]


def test_rank_reference_candidates_labels_close_results_as_ambiguous():
    query = {
        "raw_bibliography_text": "A. Author. Common fixed point theorem. 1980.",
        "title_hint": "Common fixed point theorem",
        "author_hints": ["A. Author"],
        "year_hint": "1980",
        "citation_keys": ["4"],
        "raw_citation_texts": [],
    }

    ranked = rank_reference_candidates(
        query,
        [
            provider_result(
                "crossref",
                records=[
                    {
                        "kind": "doi",
                        "doi": "10.1/a",
                        "title": "Common fixed point theorem",
                        "authors": ["A. Author"],
                        "year": "1980",
                    },
                    {
                        "kind": "doi",
                        "doi": "10.1/b",
                        "title": "Common fixed point theorem",
                        "authors": ["A. Author"],
                        "year": "1980",
                    },
                ],
            )
        ],
    )

    assert ranked["summary"]["ambiguous_candidate_count"] == 2
    assert [candidate["confidence"] for candidate in ranked["candidates"]] == [
        "ambiguous",
        "ambiguous",
    ]


def test_rank_reference_candidates_reports_metadata_only_boundary():
    query = {
        "raw_bibliography_text": (
            "D. Classic. Old proceedings note. Proceedings of the 1932 seminar."
        ),
        "title_hint": "Old proceedings note",
        "author_hints": ["D. Classic"],
        "year_hint": "1932",
        "citation_keys": ["21"],
        "raw_citation_texts": [],
    }

    ranked = rank_reference_candidates(
        query,
        [
            provider_result(
                "openalex",
                records=[
                    {
                        "kind": "metadata",
                        "title": "Old proceedings note",
                        "authors": ["D. Classic"],
                        "year": "1932",
                        "venue": "Proceedings of the 1932 seminar",
                    }
                ],
            )
        ],
    )

    assert ranked["candidates"][0]["confidence"] == "unavailable"
    assert ranked["boundaries"][0]["kind"] == "metadata_only"
    assert "no DOI, arXiv ID, stable URL, or local PDF" in ranked["boundaries"][0][
        "message"
    ]


def test_rank_reference_candidates_preserves_provider_warnings():
    ranked = rank_reference_candidates(
        {"raw_bibliography_text": "target", "citation_keys": ["1"]},
        [
            provider_result("crossref", warnings=["crossref timed out"]),
            provider_result(
                "openalex",
                records=[
                    {
                        "kind": "doi",
                        "doi": "10.1000/example",
                        "title": "Target",
                    }
                ],
            ),
        ],
    )

    assert ranked["provider_warnings"] == [
        {"provider": "crossref", "warning": "crossref timed out"}
    ]
    assert ranked["candidates"][0]["target"]["doi"] == "10.1000/example"


def test_build_reference_search_query_uses_blocked_evidence():
    blocked = {
        "blocked_id": "external-import:blocked:abc",
        "evidence": [
            {
                "kind": "bibliography_entry",
                "citation_key": "17",
                "raw_text": "[17] A. Author. Published target. 2020.",
            },
            {
                "kind": "external_result_mention",
                "citation_key": "17",
                "raw_text": "[17, Theorem 2.1]",
            },
        ],
    }

    query = build_reference_search_query(blocked)

    assert query["citation_keys"] == ["17"]
    assert query["raw_citation_texts"] == ["[17, Theorem 2.1]"]
    assert query["raw_bibliography_text"] == "[17] A. Author. Published target. 2020."
    assert query["title_hint"] == "Published target"
    assert query["year_hint"] == "2020"


def test_crossref_provider_normalizes_work_records():
    client = FakeClient(
        FakeResponse(
            {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/example",
                            "title": ["Published target"],
                            "author": [
                                {"given": "Ada", "family": "Lovelace"},
                                {"given": "Emmy", "family": "Noether"},
                            ],
                            "published-print": {"date-parts": [[2020]]},
                            "container-title": ["Journal of Examples"],
                            "URL": "https://doi.org/10.1000/example",
                        }
                    ]
                }
            }
        )
    )

    result = CrossrefReferenceProvider(client=client).search(
        {"raw_bibliography_text": "Published target", "title_hint": "Published target"}
    )

    assert client.calls[0]["url"] == "https://api.crossref.org/works"
    assert result["provider"] == "crossref"
    assert result["records"] == [
        {
            "kind": "doi",
            "doi": "10.1000/example",
            "title": "Published target",
            "authors": ["Ada Lovelace", "Emmy Noether"],
            "year": "2020",
            "venue": "Journal of Examples",
            "url": "https://doi.org/10.1000/example",
        }
    ]


def test_openalex_provider_normalizes_work_records():
    client = FakeClient(
        FakeResponse(
            {
                "results": [
                    {
                        "display_name": "Published target",
                        "doi": "https://doi.org/10.1000/example",
                        "publication_year": 2020,
                        "primary_location": {
                            "source": {"display_name": "Journal of Examples"},
                            "landing_page_url": "https://publisher.example/paper",
                        },
                        "authorships": [
                            {"author": {"display_name": "Ada Lovelace"}},
                        ],
                        "ids": {"arxiv": "https://arxiv.org/abs/2401.12345"},
                    }
                ]
            }
        )
    )

    result = OpenAlexReferenceProvider(client=client).search(
        {"raw_bibliography_text": "Published target", "title_hint": "Published target"}
    )

    assert client.calls[0]["url"] == "https://api.openalex.org/works"
    assert result["records"][0]["doi"] == "10.1000/example"
    assert result["records"][0]["arxiv_id"] == "2401.12345"
    assert result["records"][0]["venue"] == "Journal of Examples"


def test_arxiv_provider_normalizes_atom_records():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2401.12345v2</id>
        <title>Published target</title>
        <published>2020-01-01T00:00:00Z</published>
        <author><name>Ada Lovelace</name></author>
        <link href="http://arxiv.org/abs/2401.12345v2" rel="alternate"/>
      </entry>
    </feed>
    """
    client = FakeClient(FakeResponse(text=atom))

    result = ArxivReferenceProvider(client=client).search(
        {"raw_bibliography_text": "Published target", "title_hint": "Published target"}
    )

    assert client.calls[0]["url"] == "https://export.arxiv.org/api/query"
    assert result["records"][0] == {
        "kind": "arxiv",
        "arxiv_id": "2401.12345",
        "arxiv_version": "v2",
        "title": "Published target",
        "authors": ["Ada Lovelace"],
        "year": "2020",
        "url": "http://arxiv.org/abs/2401.12345v2",
    }


def test_workspace_search_external_reference_persists_and_reuses_cached_run(
    tmp_path: Path,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        blocked = import_search_source_pdf(workspace, tmp_path)
        calls = []

        def fake_provider(query: dict) -> list[dict]:
            calls.append(query)
            return [
                provider_result(
                    "crossref",
                    records=[
                        {
                            "kind": "doi",
                            "doi": "10.1000/example",
                            "title": "Published target",
                            "authors": ["A. Author", "B. Writer"],
                            "year": "2020",
                            "venue": "Journal of Examples",
                        }
                    ],
                )
            ]

        workspace.reference_search_provider = fake_provider

        first = workspace.search_external_reference(
            "local:paper", blocked["blocked_id"]
        )
        second = workspace.search_external_reference(
            "local:paper", blocked["blocked_id"]
        )

        assert len(calls) == 1
        assert first["search_run_id"] == second["search_run_id"]
        assert first["summary"]["candidate_count"] == 1
        listed = workspace.list_external_reference_searches("local:paper")
        assert listed["summary"]["search_run_count"] == 1
        assert listed["searches"][0]["candidates"][0]["target"]["doi"] == (
            "10.1000/example"
        )
    finally:
        workspace.close()


def test_workspace_search_external_reference_refresh_creates_new_run(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        blocked = import_search_source_pdf(workspace, tmp_path)
        call_count = 0

        def fake_provider(query: dict) -> list[dict]:
            nonlocal call_count
            call_count += 1
            return [
                provider_result(
                    "crossref",
                    records=[
                        {
                            "kind": "doi",
                            "doi": f"10.1000/example{call_count}",
                            "title": "Published target",
                        }
                    ],
                )
            ]

        workspace.reference_search_provider = fake_provider

        first = workspace.search_external_reference(
            "local:paper", blocked["blocked_id"]
        )
        second = workspace.search_external_reference(
            "local:paper", blocked["blocked_id"], refresh=True
        )

        assert call_count == 2
        assert first["search_run_id"] != second["search_run_id"]
        assert second["candidates"][0]["target"]["doi"] == "10.1000/example2"
    finally:
        workspace.close()


def test_workspace_resolve_external_reference_candidate_applies_resolution(
    tmp_path: Path,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        blocked = import_search_source_pdf(workspace, tmp_path)

        workspace.reference_search_provider = lambda query: [
            provider_result(
                "crossref",
                records=[
                    {
                        "kind": "doi",
                        "doi": "10.1000/example",
                        "title": "Published target",
                        "authors": ["A. Author"],
                        "year": "2020",
                    }
                ],
            )
        ]
        search = workspace.search_external_reference("local:paper", blocked["blocked_id"])
        candidate_id = search["candidates"][0]["candidate_id"]

        result = workspace.resolve_external_reference_candidate(
            "local:paper",
            blocked["blocked_id"],
            candidate_id,
        )

        assert result["candidate"]["candidate_id"] == candidate_id
        assert result["resolution"]["status"] == "resolved_not_imported"
        assert result["resolution"]["target"]["doi"] == "10.1000/example"
    finally:
        workspace.close()


def test_workspace_resolve_external_reference_candidate_requires_overwrite(
    tmp_path: Path,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        blocked = import_search_source_pdf(workspace, tmp_path)
        blocked_id = blocked["blocked_id"]
        workspace.resolve_external_reference(
            "local:paper",
            blocked_id,
            {"kind": "doi", "doi": "10.1000/existing"},
        )
        workspace.reference_search_provider = lambda query: [
            provider_result(
                "crossref",
                records=[
                    {
                        "kind": "doi",
                        "doi": "10.1000/new",
                        "title": "Published target",
                    }
                ],
            )
        ]
        search = workspace.search_external_reference("local:paper", blocked_id)

        with pytest.raises(ValueError, match="existing resolution"):
            workspace.resolve_external_reference_candidate(
                "local:paper",
                blocked_id,
                search["candidates"][0]["candidate_id"],
            )

        result = workspace.resolve_external_reference_candidate(
            "local:paper",
            blocked_id,
            search["candidates"][0]["candidate_id"],
            overwrite=True,
        )
        assert result["resolution"]["target"]["doi"] == "10.1000/new"
    finally:
        workspace.close()
