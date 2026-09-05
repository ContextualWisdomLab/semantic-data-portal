from __future__ import annotations

from sdp_core.demo_seed import BuyerDemoDomain, buyer_demo_domains


def _buyer_demo_domain(**overrides: object) -> BuyerDemoDomain:
    domain_payload: dict[str, object] = {
        "demo_domain_id": "customer_intelligence",
        "demo_domain_label": "customer intelligence",
        "demo_domain_description": "Buyer demo domain for governed customer intelligence.",
        "default_connectors": ["sql_connector", "rdf_connector"],
        "analyst_questions": [],
        "governance_questions": [],
        "acceptance_questions": [],
        "dataset_ids": [],
        "glossary_terms": [],
    }
    domain_payload.update(overrides)
    return BuyerDemoDomain(**domain_payload)


def test_buyer_demo_domain_owns_semantic_domain_fields() -> None:
    demo_domain = _buyer_demo_domain()

    assert "demo_domain_id" in BuyerDemoDomain.model_fields
    assert "demo_domain_label" in BuyerDemoDomain.model_fields
    assert "demo_domain_description" in BuyerDemoDomain.model_fields
    assert "id" not in BuyerDemoDomain.model_fields
    assert "label" not in BuyerDemoDomain.model_fields
    assert "description" not in BuyerDemoDomain.model_fields
    assert demo_domain.demo_domain_id == "customer_intelligence"
    assert demo_domain.demo_domain_label == "customer intelligence"


def test_buyer_demo_domain_preserves_legacy_wire_aliases() -> None:
    demo_domain = BuyerDemoDomain(
        id="customer_intelligence",
        label="customer intelligence",
        description="Buyer demo domain for governed customer intelligence.",
        default_connectors=["sql_connector", "rdf_connector"],
        analyst_questions=[],
        governance_questions=[],
        acceptance_questions=[],
        dataset_ids=[],
        glossary_terms=[],
    )

    assert demo_domain.demo_domain_id == "customer_intelligence"
    assert demo_domain.demo_domain_label == "customer intelligence"
    assert demo_domain.demo_domain_description.startswith("Buyer demo domain")

    wire_payload = demo_domain.model_dump(mode="json", by_alias=True)
    assert wire_payload["id"] == "customer_intelligence"
    assert wire_payload["label"] == "customer intelligence"
    assert wire_payload["description"].startswith("Buyer demo domain")
    assert "demo_domain_id" not in wire_payload
    assert "demo_domain_label" not in wire_payload
    assert "demo_domain_description" not in wire_payload


def test_seeded_buyer_demo_domain_uses_semantic_owned_names() -> None:
    demo_domain = buyer_demo_domains()[0]

    assert demo_domain.demo_domain_id == "customer_intelligence"
    assert demo_domain.demo_domain_label == "customer intelligence"
    assert demo_domain.demo_domain_description
