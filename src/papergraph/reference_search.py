"""Versioned scholarly resolver facade; historic identifiers stay stable."""
from papergraph.evidence import slug_fragment
from papergraph import reference_search_legacy as legacy
from papergraph.reference_search_legacy import _compact_key

RESOLVER_VERSIONS = ("legacy_v1", "deterministic_v2")
SEARCH_SCHEMA_VERSION = 2

def validate_resolver_version(value: str) -> str:
    if value not in RESOLVER_VERSIONS:
        raise ValueError(f"Unsupported resolver version: {value!r}")
    return value

def build_reference_search_query(blocked, *, resolver_version="legacy_v1"):
    validate_resolver_version(resolver_version)
    if resolver_version == "legacy_v1":
        return legacy.build_reference_search_query(blocked)
    from papergraph.reference_query import build_query_v2
    return build_query_v2(blocked)

def rank_reference_candidates(query, provider_results, max_candidates=10, *, resolver_version="legacy_v1"):
    validate_resolver_version(resolver_version)
    if resolver_version == "legacy_v1":
        return legacy.rank_reference_candidates(query, provider_results, max_candidates)
    from papergraph.reference_assessment import rank_candidates_v2
    return rank_candidates_v2(query, provider_results, max_candidates)

def search_run_id(source_paper_id: str, blocked_id: str, query: dict, ordinal: int) -> str:
    stable = "|".join([source_paper_id, blocked_id, str(ordinal), _compact_key(query)])
    return f"reference-search:{slug_fragment(stable)}"


def candidate_id_for(source_paper_id: str, blocked_id: str, target: dict) -> str:
    stable = "|".join([source_paper_id, blocked_id, _compact_key(target)])
    return f"reference-candidate:{slug_fragment(stable)}"
