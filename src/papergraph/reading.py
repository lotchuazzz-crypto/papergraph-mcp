"""Deterministic bridge payload helpers for paper-reading consumers."""

from __future__ import annotations

from papergraph.evidence import slug_fragment


BRIDGE_SCHEMA_VERSION = "1"

_KIND_ABBREVIATIONS = {
    "theorem": "Thm",
    "lemma": "Lemma",
    "proposition": "Prop",
    "corollary": "Cor",
    "definition": "Def",
    "claim": "Claim",
    "remark": "Rem",
    "example": "Ex",
    "conjecture": "Conj",
}


def base_bridge_payload(papergraph_version: str) -> dict:
    """Return common metadata for every reading bridge payload."""

    return {
        "bridge_schema_version": BRIDGE_SCHEMA_VERSION,
        "papergraph_version": papergraph_version,
        "source_policy": {
            "facts_from": "papergraph_evidence_graph",
            "interpretation_from": "consumer",
            "proof_verification": False,
            "semantic_matching": False,
        },
        "warnings": [],
    }


def reading_paper_uri(paper_id: str) -> str:
    """Return the consumer-facing URI for a PaperGraph paper."""

    return f"paper:{paper_id}"


def reading_result_uri(
    paper_id: str,
    display_kind: str,
    visible_number: str | None,
    local_id: str,
) -> str:
    """Return the consumer-facing URI for a PaperGraph result."""

    abbreviation = _kind_abbreviation(display_kind)
    fragment = visible_number if visible_number else slug_fragment(local_id)
    return f"{reading_paper_uri(paper_id)}#{abbreviation}-{fragment}"


def source_handle(kind: str, value: str, paper_id: str, role: str) -> dict:
    """Return a selector handle suitable for later source-slice lookup."""

    return {
        "kind": kind,
        "value": value,
        "paper_id": paper_id,
        "role": role,
    }


def result_to_reading_entity(
    result: dict,
    dependencies: dict,
    source_handles: list[dict],
    proof_methods: list[dict] | None = None,
) -> dict:
    """Map a PaperGraph result and dependency payload to an AI4Math-like entity."""

    return {
        "type": str(result["display_kind"]).upper(),
        "label": _result_label(result),
        "papergraph_id": result["result_id"],
        "reading_uri": reading_result_uri(
            result["paper_id"],
            result["display_kind"],
            result.get("visible_number"),
            result["local_id"],
        ),
        "statement": result["statement"],
        "location": _location_from_result(result),
        "dependencies": _known_local_dependency_labels(dependencies),
        "uncertain_dependencies": _uncertain_local_dependency_labels(dependencies),
        "external_refs": _external_refs(dependencies),
        "proof_methods": list(proof_methods or []),
        "source_handles": source_handles,
        "method": result["method"],
        "confidence": result["confidence"],
        "shared_node": False,
        "auto_labeled": False,
    }


def result_to_reading_result(result: dict, source_handles: list[dict]) -> dict:
    """Map one result to the bridge's result payload."""

    return {
        **result,
        "papergraph_id": result["result_id"],
        "reading_uri": reading_result_uri(
            result["paper_id"],
            result["display_kind"],
            result.get("visible_number"),
            result["local_id"],
        ),
        "type": str(result["display_kind"]).upper(),
        "location": _location_from_result(result),
        "source_handles": source_handles,
    }


def reading_uri_map(results: list[dict]) -> dict:
    """Return reversible PaperGraph ID to reading URI mappings."""

    paper_id = results[0]["paper_id"] if results else None
    papergraph_to_reading = {
        result["result_id"]: reading_result_uri(
            result["paper_id"],
            result["display_kind"],
            result.get("visible_number"),
            result["local_id"],
        )
        for result in results
    }
    return {
        "paper_uri": reading_paper_uri(paper_id) if paper_id else None,
        "papergraph_to_reading": papergraph_to_reading,
        "reading_to_papergraph": {
            reading_uri: papergraph_id
            for papergraph_id, reading_uri in papergraph_to_reading.items()
        },
    }


def interpretation_policy() -> dict:
    """Return fields the consumer, not PaperGraph, is expected to create."""

    return {
        "paper_summary": "requires_consumer_interpretation",
        "proof_gap_filling": "requires_bounded_source_slice",
        "main_result_detection": "not_provided",
    }


def interpretation_prompts() -> dict:
    """Return allowed consumer interpretation tasks for result contexts."""

    return {
        "allowed": [
            "plain_language_explanation",
            "proof_gap_filling",
            "symbol_table",
            "uncertainty_review",
        ],
        "requires_source_slice_for": [
            "proof_gap_filling",
            "implicit_claim_extraction",
        ],
    }


def proof_methods_from_proof_payload(proof_payload: dict) -> list[dict]:
    """Return proof association metadata in AI4Math-like proof_methods form."""

    proof = proof_payload.get("known", {}).get("proof")
    if not proof:
        return []
    return [
        {
            "proof_variant": 1,
            "association_basis": proof["association_basis"],
            "association_confidence": proof["association_confidence"],
            "method": proof["method"],
            "source_handles": [
                source_handle(
                    "proof_id",
                    proof["proof_id"],
                    proof["paper_id"],
                    "proof",
                )
            ],
        }
    ]


def _kind_abbreviation(display_kind: str) -> str:
    return _KIND_ABBREVIATIONS.get(display_kind.casefold(), display_kind[:3])


def _result_label(result: dict) -> str:
    label = result.get("label")
    if label:
        return label
    visible_number = result.get("visible_number")
    if visible_number:
        return f"{result['display_kind']} {visible_number}"
    return result["reading_uri"] if "reading_uri" in result else result["result_id"]


def _known_local_dependency_labels(dependencies: dict) -> list[str]:
    return [
        _result_label(result)
        for result in dependencies.get("known", {}).get(
            "resolved_local_results",
            [],
        )
    ]


def _uncertain_local_dependency_labels(dependencies: dict) -> list[str]:
    labels = []
    unresolved = dependencies.get("unresolved", {})
    for mention in unresolved.get("local_result_mentions", []):
        reason = mention.get("resolution_status", "unresolved")
        labels.append(f"{mention['raw_text']} [UNCERTAIN: {reason}]")
    return labels


def _external_refs(dependencies: dict) -> list[str]:
    refs = []
    known = dependencies.get("known", {})
    unresolved = dependencies.get("unresolved", {})
    for mention in known.get("external_result_mentions", []):
        refs.append(_external_ref_label(mention))
    for mention in unresolved.get("external_result_mentions", []):
        refs.append(_external_ref_label(mention))
    return refs


def _external_ref_label(mention: dict) -> str:
    status = mention.get("resolution_status", "unresolved")
    return f"{mention['raw_text']} [EXTERNAL: {status}]"


def _location_from_result(result: dict) -> dict:
    spans = result.get("spans", [])
    if not spans:
        first_location = result.get("first_location")
        if isinstance(first_location, dict):
            return first_location
        return {}
    span = spans[0]
    return {
        "source_type": span.get("source_type"),
        "source_ref": span.get("source_ref"),
        "page": span.get("page"),
        "block_index": span.get("block_index"),
        "span_id": span.get("span_id"),
    }
