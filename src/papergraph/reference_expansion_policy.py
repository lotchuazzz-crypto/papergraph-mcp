"""Pure, versioned authorization rules for bounded reference expansion."""
from __future__ import annotations

import copy
import re

from papergraph.identity import paper_id_from_arxiv

LIMITS = {"max_depth": (2, 10), "max_new_papers": (10, 100),
          "max_searches": (100, 1000), "max_edges": (500, 10000)}
PROVIDERS = {"crossref", "openalex", "arxiv"}
POLICY_RESOLVERS = {'unique_strong_v1':'legacy_v1', 'unique_strong_v2':'deterministic_v2'}


def resolver_for_policy(policy: dict) -> str:
    name = policy.get('auto_select_policy', 'unique_strong_v1')
    if name not in POLICY_RESOLVERS:
        raise ValueError('Unsupported automatic selection policy')
    expected = POLICY_RESOLVERS[name]
    if policy.get('resolver_version', expected) != expected:
        raise ValueError('Policy and resolver version disagree')
    return expected


def validate_policy(policy: dict | None) -> dict:
    policy = {} if policy is None else policy
    if not isinstance(policy, dict) or set(policy) - {*LIMITS, "providers", "auto_select_policy", "resolver_version"}:
        raise ValueError("Unknown expansion policy fields")
    result = {key: policy.get(key, default) for key, (default, _) in LIMITS.items()}
    for key, (_, ceiling) in LIMITS.items():
        if type(result[key]) is not int or not 1 <= result[key] <= ceiling:
            raise ValueError(f"{key} must be an integer between 1 and {ceiling}")
    providers = policy.get("providers", sorted(PROVIDERS))
    if not isinstance(providers, list) or not providers or any(p not in PROVIDERS for p in providers):
        raise ValueError("providers must be a nonempty list of supported providers")
    result["providers"] = sorted(set(providers))
    result["auto_select_policy"] = policy.get("auto_select_policy", "unique_strong_v2")
    result['resolver_version'] = resolver_for_policy({**policy, 'auto_select_policy':result['auto_select_policy']})
    return result


def text(value) -> str:
    return " ".join(re.findall(r"\w+", str(value or "").casefold()))


def identifiers(target: dict) -> set[str]:
    result = set()
    if target.get("doi"):
        result.add("doi:" + re.sub(r"^(?:https?://(?:dx\.)?doi.org/|doi:)", "", target["doi"], flags=re.I).lower().strip())
    if target.get("arxiv_id"):
        result.add(paper_id_from_arxiv(target["arxiv_id"])[0])
    return result


def importable_target(target: dict, *, manual: bool = False) -> dict | None:
    if target.get("arxiv_id"):
        pid, version = paper_id_from_arxiv(target["arxiv_id"])
        explicit = target.get("arxiv_version")
        if explicit and version and explicit != version:
            raise ValueError("Conflicting arXiv versions")
        version = explicit or version or ""
        if version and not re.fullmatch(r"v[1-9]\d*", version):
            raise ValueError("Invalid arXiv version")
        return {"kind": "arxiv", "arxiv_id": pid.removeprefix("arxiv:") + version}
    if manual and target.get("kind") == "pdf" and target.get("path"):
        return copy.deepcopy(target)
    return None


def select_candidate(search: dict, *, policy_version: str = 'unique_strong_v1') -> dict:
    """Never interpret a search score alone as permission to import."""
    if policy_version == 'unique_strong_v2':
        from papergraph.reference_assessment import select_v2
        return select_v2(search)
    if policy_version != 'unique_strong_v1':
        raise ValueError('Unsupported automatic selection policy')
    result = {"eligible": False, "reason_codes": [], "policy_version": "unique_strong_v1"}
    candidates = copy.deepcopy(search.get("candidates", []))
    groups = []
    for c in candidates:
        ids = identifiers(c["target"])
        matching = [g for g in groups if ids & g["ids"]]
        group = {"ids": set(ids), "items": [c]}
        for g in matching:
            group["ids"].update(g["ids"])
            group["items"].extend(g["items"])
            groups.remove(g)
        groups.append(group)
    strong = [g for g in groups if any(c.get("confidence") == "strong" for c in g["items"])]
    if len(strong) != 1 or any(c.get("confidence") == "ambiguous" for c in candidates):
        result["reason_codes"] = ["ambiguous_or_insufficient_candidates"]
        return result
    items = strong[0]["items"]
    selected = next(c for c in items if c.get("confidence") == "strong")
    target = dict(selected["target"])
    records = [r.get("record", {}) for c in items for r in c.get("provider_records", [])]
    for c in items:
        for key, value in c["target"].items():
            if value and not target.get(key):
                target[key] = value
    warnings = [str(w).lower() for c in items for w in c.get("warnings", [])]
    conflict = any(any(word in w for word in ("conflict", "version", "withdraw", "retract", "ambiguous")) for w in warnings)
    for field in ("title", "year", "arxiv_id", "arxiv_version", "doi"):
        values = {text(r[field]) for r in [c["target"] for c in items] + records if r.get(field)}
        if len(values) > 1:
            conflict = True
    author_sets = [{text(a) for a in r.get("authors", [])} for r in [target] + records if r.get("authors")]
    if author_sets and not set.intersection(*author_sets):
        conflict = True
    if any(r.get("is_retracted") or r.get("withdrawn") or r.get("retracted") for r in records):
        conflict = True
    for group in groups:
        if group is strong[0]:
            continue
        for c in group["items"]:
            other = c["target"]
            if c.get("confidence") in {"plausible", "strong"} and (
                (text(target.get("title")) and text(target.get("title")) == text(other.get("title"))) or
                (target.get("year") and target.get("year") == other.get("year") and
                 {text(a) for a in target.get("authors", [])} & {text(a) for a in other.get("authors", [])})
            ):
                conflict = True
    query = search.get("query", {})
    raw = " ".join([str(query.get("raw_bibliography_text", "")), *query.get("raw_citation_texts", [])])
    source_ids = {"doi:" + s.lower().rstrip(".,;") for s in re.findall(r"10\.\d{4,9}/[^\s<>\"{}]+", raw, re.I)}
    arxiv_values = re.findall(r"(?:arxiv\s*:\s*|arxiv.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z.-]+/\d{7}(?:v\d+)?)", raw, re.I)
    for value in arxiv_values:
        source_ids.add(paper_id_from_arxiv(value)[0])
        if paper_id_from_arxiv(value)[1] and target.get("arxiv_id"):
            if paper_id_from_arxiv(value)[1] != (paper_id_from_arxiv(target["arxiv_id"])[1] or target.get("arxiv_version")):
                conflict = True
    exact = bool(source_ids & identifiers(target))
    if source_ids - identifiers(target):
        conflict = True
    providers = {p for c in items for p in c.get("providers", [])}
    providers.update(r.get("provider") for c in items for r in c.get("provider_records", []) if r.get("provider"))
    metadata = (bool(text(query.get("title_hint"))) and text(query["title_hint"]) == text(target.get("title"))
                and bool({text(a).split()[-1] for a in query.get("author_hints", []) if text(a)} &
                         {text(a).split()[-1] for a in target.get("authors", []) if text(a)})
                and bool(query.get("year_hint")) and str(query["year_hint"]) == str(target.get("year"))
                and len(providers) >= 2 and not search.get("provider_warnings"))
    linked = not (target.get("doi") and target.get("arxiv_id")) or any(
        r.get("doi") and r.get("arxiv_id") and identifiers(r) == identifiers(target) for r in records)
    try:
        imported = importable_target(target)
    except ValueError:
        imported, conflict = None, True
    reason = "identity_conflict" if conflict else "insufficient_identity_evidence" if not (exact or metadata) else "unproven_version_link" if not linked else "no_importable_source" if not imported else None
    result.update(reason_codes=[reason] if reason else ["exact_source_identifier" if exact else "corroborated_metadata"],
                  eligible=reason is None, candidate=selected, target=imported, identity_target=target)
    return result
