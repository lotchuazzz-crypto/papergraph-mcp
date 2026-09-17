"""Crossref reference-search provider."""

from __future__ import annotations

import httpx


class CrossrefReferenceProvider:
    name = "crossref"

    def __init__(self, client=None, timeout: float = 8.0):
        self._client = client or httpx.Client()
        self._timeout = timeout

    def search(self, query: dict) -> dict:
        text = _query_text(query)
        try:
            response = self._client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": text, "rows": 5},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {"provider": self.name, "records": [], "warnings": [str(exc)]}
        records = [_record_from_item(item) for item in payload.get("message", {}).get("items", [])]
        return {
            "provider": self.name,
            "records": [record for record in records if record],
            "warnings": [],
        }


def _record_from_item(item: dict) -> dict:
    doi = _clean(item.get("DOI"))
    title = _first(item.get("title"))
    if not (doi or title):
        return {}
    record = {
        "kind": "doi" if doi else "metadata",
        "doi": doi,
        "title": title,
        "authors": _authors(item.get("author", [])),
        "year": _year(item),
        "venue": _first(item.get("container-title")),
        "url": _clean(item.get("URL")),
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def _query_text(query: dict) -> str:
    return (
        query.get("raw_bibliography_text")
        or query.get("title_hint")
        or " ".join(query.get("raw_citation_texts") or [])
        or " ".join(query.get("citation_keys") or [])
    )


def _authors(items: list[dict]) -> list[str]:
    authors = []
    for item in items:
        name = " ".join(
            part for part in [_clean(item.get("given")), _clean(item.get("family"))] if part
        )
        if name:
            authors.append(name)
    return authors


def _year(item: dict) -> str | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = item.get(key, {}).get("date-parts") if isinstance(item.get(key), dict) else None
        if parts and parts[0]:
            return str(parts[0][0])
    return None


def _first(value) -> str | None:
    if isinstance(value, list) and value:
        return _clean(value[0])
    return _clean(value)


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

