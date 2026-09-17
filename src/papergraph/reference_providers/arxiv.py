"""arXiv reference-search provider."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx


class ArxivReferenceProvider:
    name = "arxiv"

    def __init__(self, client=None, timeout: float = 8.0):
        self._client = client or httpx.Client()
        self._timeout = timeout

    def search(self, query: dict) -> dict:
        text = query.get("title_hint") or query.get("raw_bibliography_text") or ""
        search_query = f'all:"{text}"' if text else "all:*"
        try:
            response = self._client.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": search_query,
                    "start": 0,
                    "max_results": 5,
                    "sortBy": "relevance",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            return {"provider": self.name, "records": [], "warnings": [str(exc)]}
        try:
            records = _records_from_atom(response.text)
        except Exception as exc:
            return {"provider": self.name, "records": [], "warnings": [str(exc)]}
        return {"provider": self.name, "records": records, "warnings": []}


def _records_from_atom(atom: str) -> list[dict]:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(atom)
    records = []
    for entry in root.findall("atom:entry", namespace):
        entry_id = _text(entry.find("atom:id", namespace))
        arxiv_id, arxiv_version = _split_arxiv_id(entry_id)
        title = " ".join(_text(entry.find("atom:title", namespace)).split())
        published = _text(entry.find("atom:published", namespace))
        authors = [
            _text(author.find("atom:name", namespace))
            for author in entry.findall("atom:author", namespace)
        ]
        url = entry_id
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("rel") == "alternate" and link.attrib.get("href"):
                url = link.attrib["href"]
                break
        records.append(
            {
                "kind": "arxiv",
                "arxiv_id": arxiv_id,
                "arxiv_version": arxiv_version,
                "title": title,
                "authors": [author for author in authors if author],
                "year": published[:4] if published else None,
                "url": url,
            }
        )
    return [
        {key: value for key, value in record.items() if value not in (None, "", [])}
        for record in records
    ]


def _split_arxiv_id(value: str) -> tuple[str, str | None]:
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", value)
    if not match:
        return value.rsplit("/", 1)[-1], None
    return match.group(1), match.group(2)


def _text(element) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()
