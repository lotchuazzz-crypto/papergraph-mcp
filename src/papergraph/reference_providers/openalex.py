"""OpenAlex reference-search provider."""

from __future__ import annotations

import re

import httpx


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
            payload = response.json()
        except Exception as exc:
            return {"provider": self.name, "records": [], "warnings": [str(exc)]}
        records = [_record_from_work(item) for item in payload.get("results", [])]
        return {
            "provider": self.name,
            "records": [record for record in records if record],
            "warnings": [],
        }


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
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", text)
    return match.group(1) if match else text.removeprefix("arxiv:")


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
