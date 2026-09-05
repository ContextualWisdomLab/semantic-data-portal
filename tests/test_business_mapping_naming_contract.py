from __future__ import annotations

from sdp_core import BusinessMapping, MappingStatus


def test_business_mapping_owns_semantic_fields() -> None:
    mapping = BusinessMapping(
        business_concept="활성 고객",
        mapping_status=MappingStatus.APPROVED,
        mapping_source="buyer-demo",
        mapping_steward="data-governance",
    )

    assert {
        "business_concept",
        "mapping_status",
        "mapping_source",
        "mapping_steward",
        "approved_at",
    } <= set(BusinessMapping.model_fields)
    assert {"concept", "status", "source", "steward"}.isdisjoint(BusinessMapping.model_fields)
    assert mapping.business_concept == "활성 고객"
    assert mapping.mapping_status == MappingStatus.APPROVED
    assert mapping.mapping_source == "buyer-demo"
    assert mapping.mapping_steward == "data-governance"


def test_business_mapping_preserves_legacy_wire_and_python_contract() -> None:
    mapping = BusinessMapping(
        concept="활성 고객",
        status=MappingStatus.APPROVED,
        source="buyer-demo",
        steward="data-governance",
    )

    assert mapping.concept == mapping.business_concept
    assert mapping.status == mapping.mapping_status
    assert mapping.source == mapping.mapping_source
    assert mapping.steward == mapping.mapping_steward

    wire_payload = mapping.model_dump(mode="json", by_alias=True)
    assert wire_payload["concept"] == "활성 고객"
    assert wire_payload["status"] == MappingStatus.APPROVED
    assert wire_payload["source"] == "buyer-demo"
    assert wire_payload["steward"] == "data-governance"
    assert "business_concept" not in wire_payload
    assert "mapping_status" not in wire_payload
    assert "mapping_source" not in wire_payload
    assert "mapping_steward" not in wire_payload
