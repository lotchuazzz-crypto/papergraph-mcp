"""OpenAlex reference-search provider."""

from __future__ import annotations

import re

import httpx
from papergraph.reference_providers.base import failure_result, parsed_result
from papergraph.arxiv import extract_arxiv_id_from_url, normalize_arxiv_id


class OpenAlexReferenceProvider:
    name = "openalex"

    def __init__(self, client=None, timeout: float = 8.0):
        self._client = client or httpx.Client()
        self._timeout = timeout

    def search(self, query: dict) -> dict:
        text = (
            query.get("title_hint")
            or query.get("raw_bibliography_text")
            or " ".join(query.get("raw_citation_texts") or [])
        )
        try:
            response = self._client.get(
                "https://api.openalex.org/works",
                params={"search": text, "per_page": 5},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            return failure_result(self.name, exc)
        try:
            return parsed_result(self.name, response.json()['results'], _record_from_work)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return failure_result(self.name, exc, parsing=True)


def _record_from_work(item: dict) -> dict:
    doi = _doi(item.get("doi"))
    title = _clean(item.get("display_name") or item.get("title"))
    if not (doi or title):
        return {}
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    ids = item.get("ids") or {}
    arxiv_id = _arxiv_id(ids.get("arxiv") or ids.get("arxiv_id"))
    record = {
        "kind": "doi" if doi else ("arxiv" if arxiv_id else "metadata"),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": _authors(item.get("authorships", [])),
        "year": str(item["publication_year"]) if item.get("publication_year") else None,
        "venue": _clean(source.get("display_name")),
        "url": _clean(location.get("landing_page_url") or item.get("id")),
        "is_retracted": item.get("is_retracted", False),
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def _authors(items: list[dict]) -> list[str]:
    authors = []
    for item in items:
        name = _clean((item.get("author") or {}).get("display_name"))
        if name:
            authors.append(name)
    return authors


def _doi(value) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return text.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def _arxiv_id(value) -> str | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return extract_arxiv_id_from_url(text) if text.startswith(('http://', 'https://')) else normalize_arxiv_id(text)
    except ValueError:
        return text  # Preserve invalid provider evidence for the v2 assessment.


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
