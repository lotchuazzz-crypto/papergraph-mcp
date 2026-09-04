from papergraph.reading import (
    BRIDGE_SCHEMA_VERSION,
    base_bridge_payload,
    reading_result_uri,
    result_to_reading_entity,
    source_handle,
)


def test_base_bridge_payload_declares_evidence_boundary():
    payload = base_bridge_payload("0.6.0")

    assert payload["bridge_schema_version"] == BRIDGE_SCHEMA_VERSION == "1"
    assert payload["papergraph_version"] == "0.6.0"
    assert payload["source_policy"] == {
        "facts_from": "papergraph_evidence_graph",
        "interpretation_from": "consumer",
        "proof_verification": False,
        "semantic_matching": False,
    }
    assert payload["warnings"] == []


def test_reading_result_uri_uses_visible_number_and_kind_abbreviation():
    assert (
        reading_result_uri("local:paper", "Theorem", "1.1", "pdf:theorem:1.1")
        == "paper:local:paper#Thm-1.1"
    )


def test_reading_result_uri_falls_back_to_slugged_local_id():
    assert (
        reading_result_uri("local:paper", "Remark", None, "pdf:remark:2")
        == "paper:local:paper#Rem-pdf-remark-2"
    )


def test_source_handle_is_selector_payload():
    assert source_handle(
        "proof_id",
        "local:paper::proof:1",
        "local:paper",
        "proof",
    ) == {
        "kind": "proof_id",
        "value": "local:paper::proof:1",
        "paper_id": "local:paper",
        "role": "proof",
    }


def test_result_to_reading_entity_maps_known_and_unresolved_dependencies():
    result = {
        "result_id": "local:paper::pdf:theorem:1.1",
        "paper_id": "local:paper",
        "local_id": "pdf:theorem:1.1",
        "display_kind": "Theorem",
        "visible_number": "1.1",
        "label": None,
        "statement": "Theorem 1.1. Main result.",
        "method": "pdf_heading_regex",
        "confidence": 0.85,
    }
    dependencies = {
        "known": {
            "resolved_local_results": [
                {
                    "result_id": "local:paper::pdf:lemma:1.2",
                    "display_kind": "Lemma",
                    "visible_number": "1.2",
                    "local_id": "pdf:lemma:1.2",
                    "paper_id": "local:paper",
                }
            ],
            "external_result_mentions": [
                {
                    "raw_text": "[12, Theorem 3.5]",
                    "external_kind": "Theorem",
                    "external_number": "3.5",
                    "resolution_status": "resolved_bibliography_entry",
                }
            ],
        },
        "unresolved": {
            "local_result_mentions": [
                {
                    "raw_text": "Lemma 9.9",
                    "resolution_status": "unresolved",
                }
            ],
            "citation_mentions": [],
            "external_result_mentions": [],
        },
    }

    entity = result_to_reading_entity(
        result,
        dependencies,
        [
            source_handle(
                "result_id",
                result["result_id"],
                "local:paper",
                "statement",
            )
        ],
    )

    assert entity["type"] == "THEOREM"
    assert entity["label"] == "Theorem 1.1"
    assert entity["statement"] == "Theorem 1.1. Main result."
    assert entity["dependencies"] == ["Lemma 1.2"]
    assert entity["uncertain_dependencies"] == [
        "Lemma 9.9 [UNCERTAIN: unresolved]"
    ]
    assert entity["external_refs"] == [
        "[12, Theorem 3.5] [EXTERNAL: resolved_bibliography_entry]"
    ]
    assert entity["source_handles"][0]["kind"] == "result_id"
