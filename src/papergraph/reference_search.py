"""Scholarly reference search, ranking, and payload helpers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from papergraph.evidence import bounded_excerpt, slug_fragment


SEARCH_SCHEMA_VERSION = 1
_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "in",
    "of",
    "on",
    "the",
}


def build_reference_search_query(blocked: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic provider query hints from blocked-reference evidence."""

    evidence = blocked.get("evidence", [])
    citation_keys = sorted(
        {
            str(item.get("citation_key")).strip()
            for item in evidence
            if item.get("citation_key") not in (None, "")
        }
    )
    raw_citation_texts: list[str] = []
    raw_bibliography_texts: list[str] = []
    seen_citations: set[str] = set()
    seen_bibliography: set[str] = set()
    for item in evidence:
        raw_text = str(item.get("raw_text") or "").strip()
        if not raw_text:
            continue
        if item.get("kind") == "bibliography_entry":
            if raw_text not in seen_bibliography:
                seen_bibliography.add(raw_text)
                raw_bibliography_texts.append(raw_text)
        elif raw_text not in seen_citations:
            seen_citations.add(raw_text)
            raw_citation_texts.append(raw_text)
    raw_bibliography_text = " ".join(raw_bibliography_texts)
    title_hint = _title_hint(raw_bibliography_text)
    return {
        "citation_keys": citation_keys,
        "raw_citation_texts": raw_citation_texts,
        "raw_bibliography_text": raw_bibliography_text,
        "title_hint": title_hint,
        "author_hints": _author_hints(raw_bibliography_text),
        "year_hint": _year_hint(raw_bibliography_text),
    }


def rank_reference_candidates(
    query: dict[str, Any],
    provider_results: list[dict[str, Any]],
    max_candidates: int = 10,
) -> dict[str, Any]:
    """Merge and rank provider records into PaperGraph reference candidates."""

    merged: dict[str, dict[str, Any]] = {}
    provider_warnings = []
    for provider_result in provider_results:
        provider = str(provider_result.get("provider") or "unknown")
        for warning in provider_result.get("warnings", []):
            provider_warnings.append({"provider": provider, "warning": str(warning)})
        for record in provider_result.get("records", []):
            target = _normalize_record_target(record)
            key = _merge_key(target)
            item = merged.setdefault(
                key,
                {
                    "target": target,
                    "providers": [],
                    "provider_records": [],
                },
            )
            item["providers"].append(provider)
            item["provider_records"].append({"provider": provider, "record": record})
            item["target"] = _merge_targets(item["target"], target)

    candidates = []
    for item in merged.values():
        score, evidence, warnings = _score_candidate(query, item)
        target = item["target"]
        confidence = _confidence(score, evidence, target)
        candidate_id = _candidate_id(query, target)
        candidates.append(
            {
                "candidate_schema_version": SEARCH_SCHEMA_VERSION,
                "candidate_id": candidate_id,
                "target": target,
                "score": round(score, 3),
                "confidence": confidence,
                "evidence": evidence,
                "providers": sorted(set(item["providers"])),
                "provider_records": item["provider_records"],
                "warnings": warnings,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            _confidence_rank(candidate["confidence"]),
            -candidate["score"],
            str(candidate["target"].get("kind") or ""),
            str(candidate["target"].get("title") or ""),
            candidate["candidate_id"],
        )
    )
    _mark_ambiguous(candidates)
    candidates = candidates[:max_candidates]
    boundaries = _boundaries(candidates, provider_warnings)
    return {
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "query": query,
        "candidates": candidates,
        "boundaries": boundaries,
        "provider_warnings": provider_warnings,
        "summary": {
            "candidate_count": len(candidates),
            "strong_candidate_count": sum(
                1 for item in candidates if item["confidence"] == "strong"
            ),
            "ambiguous_candidate_count": sum(
                1 for item in candidates if item["confidence"] == "ambiguous"
            ),
            "boundary_count": len(boundaries),
            "provider_warning_count": len(provider_warnings),
        },
    }


def search_run_id(source_paper_id: str, blocked_id: str, query: dict, ordinal: int) -> str:
    stable = "|".join([source_paper_id, blocked_id, str(ordinal), _compact_key(query)])
    return f"reference-search:{slug_fragment(stable)}"


def candidate_id_for(source_paper_id: str, blocked_id: str, target: dict) -> str:
    stable = "|".join([source_paper_id, blocked_id, _compact_key(target)])
    return f"reference-candidate:{slug_fragment(stable)}"


def _candidate_id(query: dict[str, Any], target: dict[str, Any]) -> str:
    stable = "|".join(
        [
            ",".join(query.get("citation_keys") or []),
            str(query.get("raw_bibliography_text") or ""),
            _compact_key(target),
        ]
    )
    return f"reference-candidate:{slug_fragment(stable)}"


def _normalize_record_target(record: dict[str, Any]) -> dict[str, Any]:
    kind = str(record.get("kind") or "").lower().strip()
    doi = _clean(record.get("doi"))
    arxiv_id = _clean(record.get("arxiv_id"))
    url = _clean(record.get("url"))
    if not kind:
        if doi:
            kind = "doi"
        elif arxiv_id:
            kind = "arxiv"
        elif url:
            kind = "url"
        else:
            kind = "metadata"
    target: dict[str, Any] = {"kind": kind}
    for field in ("doi", "arxiv_id", "arxiv_version", "url", "title", "year", "venue"):
        value = _clean(record.get(field))
        if value:
            target[field] = value
    authors = record.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    normalized_authors = [_clean(author) for author in authors]
    normalized_authors = [author for author in normalized_authors if author]
    if normalized_authors:
        target["authors"] = normalized_authors
    return target


def _merge_key(target: dict[str, Any]) -> str:
    if target.get("doi"):
        return f"doi:{str(target['doi']).lower()}"
    if target.get("arxiv_id"):
        return f"arxiv:{str(target['arxiv_id']).lower()}"
    title = _normalize_text(target.get("title"))
    first_author = _normalize_text((target.get("authors") or [""])[0])
    year = str(target.get("year") or "")
    return f"metadata:{title}:{first_author}:{year}"


def _merge_targets(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    if merged.get("kind") == "metadata" and right.get("kind") != "metadata":
        merged["kind"] = right["kind"]
    for key, value in right.items():
        if value not in (None, "", []) and not merged.get(key):
            merged[key] = value
    return merged


def _score_candidate(
    query: dict[str, Any],
    item: dict[str, Any],
) -> tuple[float, list[str], list[str]]:
    target = item["target"]
    evidence = []
    warnings = []
    score = 0.0
    title_hint = _normalize_text(query.get("title_hint"))
    title = _normalize_text(target.get("title"))
    if title_hint and title:
        ratio = SequenceMatcher(None, title_hint, title).ratio()
        if ratio >= 0.98:
            score += 4.0
            evidence.append("title_exact_match")
        elif ratio >= 0.75:
            score += 2.0
            evidence.append("title_close_match")
    query_authors = {_normalize_author(author) for author in query.get("author_hints", [])}
    target_authors = {_normalize_author(author) for author in target.get("authors", [])}
    author_overlap = len({author for author in query_authors & target_authors if author})
    if author_overlap:
        score += min(author_overlap, 3) * 1.2
        evidence.append(f"author_overlap:{author_overlap}")
    if query.get("year_hint") and str(target.get("year") or "") == str(query["year_hint"]):
        score += 1.2
        evidence.append("year_exact_match")
    if target.get("doi"):
        score += 1.5
        evidence.append("doi_present")
    if target.get("arxiv_id"):
        score += 1.2
        evidence.append("arxiv_present")
    providers = sorted(set(item.get("providers", [])))
    if len(providers) > 1:
        score += 1.0
        evidence.append("provider_agreement")
    if target.get("kind") == "metadata" and not any(
        target.get(field) for field in ("doi", "arxiv_id", "url")
    ):
        warnings.append("metadata_only")
    return score, evidence, warnings


def _confidence(score: float, evidence: list[str], target: dict[str, Any]) -> str:
    if target.get("kind") == "metadata" and "metadata_only" in _metadata_warnings(target):
        return "unavailable"
    if score >= 7.0 or "provider_agreement" in evidence:
        return "strong"
    if score >= 3.5:
        return "plausible"
    if target.get("kind") == "metadata":
        return "unavailable"
    return "weak"


def _metadata_warnings(target: dict[str, Any]) -> list[str]:
    if target.get("kind") == "metadata" and not any(
        target.get(field) for field in ("doi", "arxiv_id", "url")
    ):
        return ["metadata_only"]
    return []


def _mark_ambiguous(candidates: list[dict[str, Any]]) -> None:
    if len(candidates) < 2:
        return
    top = candidates[0]["score"]
    close = [
        item
        for item in candidates
        if item["score"] >= top - 0.05 and item["confidence"] != "unavailable"
    ]
    if len(close) > 1:
        for item in close:
            item["confidence"] = "ambiguous"
            if "ambiguous_candidates" not in item["warnings"]:
                item["warnings"].append("ambiguous_candidates")


def _boundaries(
    candidates: list[dict[str, Any]],
    provider_warnings: list[dict[str, str]],
) -> list[dict[str, str]]:
    boundaries = []
    if provider_warnings and not candidates:
        boundaries.append(
            {
                "kind": "provider_unavailable",
                "message": "All scholarly providers failed or returned no usable candidates.",
            }
        )
    for candidate in candidates:
        if candidate["confidence"] == "unavailable":
            boundaries.append(
                {
                    "kind": "metadata_only",
                    "candidate_id": candidate["candidate_id"],
                    "message": (
                        "PaperGraph found metadata for this reference but no DOI, "
                        "arXiv ID, stable URL, or local PDF. The trail stops until "
                        "the user supplies an importable source."
                    ),
                }
            )
        if candidate["confidence"] == "ambiguous":
            boundaries.append(
                {
                    "kind": "ambiguous_candidates",
                    "candidate_id": candidate["candidate_id"],
                    "message": (
                        "Multiple candidates have similar search evidence; manual "
                        "review is needed before applying a resolution."
                    ),
                }
            )
    deduped = {}
    for boundary in boundaries:
        key = (boundary["kind"], boundary.get("candidate_id"))
        deduped[key] = boundary
    return [deduped[key] for key in sorted(deduped)]


def _title_hint(text: str) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*", "", text)
    parts = [part.strip() for part in re.split(r"\.\s+", cleaned) if part.strip()]
    for part in parts:
        words = part.split()
        if 2 <= len(words) <= 12 and not _looks_like_author_list(part):
            return part.rstrip(".")
    return None


def _author_hints(text: str) -> list[str]:
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*", "", text)
    first = cleaned.split(".", 1)[0]
    if not first:
        return []
    authors = re.split(r"\s+and\s+|,\s*(?=[A-Z]\.)", first)
    return [author.strip() for author in authors if author.strip()]


def _year_hint(text: str) -> str | None:
    match = re.search(r"\b(18|19|20)\d{2}\b", text or "")
    return match.group(0) if match else None


def _looks_like_author_list(text: str) -> bool:
    return bool(re.search(r"\b[A-Z]\.\s+[A-Z][A-Za-z-]+", text))


def _normalize_text(value: Any) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return " ".join(word for word in words if word not in _TITLE_STOPWORDS)


def _normalize_author(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def _confidence_rank(confidence: str) -> int:
    return {
        "strong": 0,
        "plausible": 1,
        "ambiguous": 2,
        "weak": 3,
        "unavailable": 4,
    }.get(confidence, 5)


def _compact_key(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = bounded_excerpt(str(value), limit=500).strip()
    return text or None
