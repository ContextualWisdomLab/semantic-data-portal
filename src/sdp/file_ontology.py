"""Standards-aligned contracts for content-addressed file knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from importlib.resources import files
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .graph_store import GraphStore


StorageProvider = Literal["filesystem", "s3", "s3_compatible", "azure_blob"]
AssertionRelation = Literal[
    "belongsToProject",
    "usesSystem",
    "hasWorkPhase",
    "hasArtifactType",
    "hasTopic",
    "wasDerivedFrom",
    "previousVersion",
]
TargetKind = Literal[
    "business_project",
    "system",
    "work_phase",
    "artifact_type",
    "topic",
    "file_asset",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELATION_TARGETS: dict[str, str] = {
    "belongsToProject": "business_project",
    "usesSystem": "system",
    "hasWorkPhase": "work_phase",
    "hasArtifactType": "artifact_type",
    "hasTopic": "topic",
    "wasDerivedFrom": "file_asset",
    "previousVersion": "file_asset",
}
_CONTEXT = {
    "cwl": "https://contextualwisdomlab.github.io/semantic-data-portal/ontology/file#",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "spdx": "http://spdx.org/rdf/terms#",
}


class StorageDistribution(BaseModel):
    id: str = Field(min_length=1)
    provider: StorageProvider
    locator: str = Field(min_length=1)
    endpoint_id: str = Field(min_length=1)
    available: bool = True
    bucket: str | None = None
    container: str | None = None
    object_key: str | None = None
    version_id: str | None = None
    etag: str | None = None

    @field_validator("locator")
    @classmethod
    def stable_locator_without_credentials(cls, value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.scheme:
            raise ValueError("locator must be an absolute IRI")
        if parsed.query or parsed.fragment:
            raise ValueError("locator must not contain a query or fragment")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("locator must not contain userinfo credentials")
        return value


class SemanticAssertion(BaseModel):
    relation: AssertionRelation
    target_kind: TargetKind
    target_label: str = Field(min_length=1)
    target_asset_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_chunk_sha256: str
    evidence_start: int
    evidence_end: int
    method: str = Field(min_length=1)
    review_status: Literal["proposed", "approved", "rejected"] = "proposed"

    @model_validator(mode="after")
    def validate_file_target(self) -> "SemanticAssertion":
        if self.target_kind == "file_asset":
            if not self.target_asset_id or not re.fullmatch(
                r"urn:sha256:[0-9a-f]{64}", self.target_asset_id
            ):
                raise ValueError("file_asset assertions require a content-addressed target_asset_id")
        elif self.target_asset_id is not None:
            raise ValueError("target_asset_id is only valid for file_asset assertions")
        return self


class FileAsset(BaseModel):
    sha256: str
    tenant_id: str = Field(default="demo", min_length=1)
    title: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    byte_size: int = Field(ge=0)
    modified_at: datetime | None = None
    distributions: list[StorageDistribution]
    assertions: list[SemanticAssertion] = Field(default_factory=list)

    @property
    def asset_id(self) -> str:
        return f"urn:sha256:{self.sha256}"


class FileAssetIngestRequest(FileAsset):
    model_config = ConfigDict(extra="forbid")


def _violation(path: str, message: str) -> dict[str, str]:
    return {
        "shape": "CWLFileAssetShape",
        "path": path,
        "severity": "violation",
        "message": message,
    }


def _shacl_violations(asset: FileAsset) -> list[dict[str, str]]:
    from pyshacl import validate as shacl_validate
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    resources = files("sdp").joinpath("resources")
    data_graph = Graph().parse(
        data=json.dumps(file_asset_jsonld(asset, include_locations=True), ensure_ascii=False),
        format="json-ld",
    )
    shapes_graph = Graph().parse(
        data=resources.joinpath("cwl-file-shapes.ttl").read_text(encoding="utf-8"),
        format="turtle",
    )
    ontology_graph = Graph().parse(
        data=resources.joinpath("cwl-file-profile.ttl").read_text(encoding="utf-8"),
        format="turtle",
    )
    conforms, results_graph, _text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        ont_graph=ontology_graph,
        inference="rdfs",
        advanced=True,
    )
    if conforms:
        return []
    sh = Namespace("http://www.w3.org/ns/shacl#")
    violations: list[dict[str, str]] = []
    for result in results_graph.subjects(RDF.type, sh.ValidationResult):
        path = results_graph.value(result, sh.resultPath)
        message = results_graph.value(result, sh.resultMessage)
        violations.append(
            _violation(
                str(path) if path is not None else "shacl",
                str(message) if message is not None else "SHACL constraint violated",
            )
        )
    return violations or [_violation("shacl", "SHACL graph did not conform")]


def validate_file_asset(asset: FileAsset) -> dict[str, Any]:
    """Return the SHACL-compatible structural validation report for an asset."""

    violations: list[dict[str, str]] = []
    if not _SHA256_RE.fullmatch(asset.sha256):
        violations.append(_violation("sha256", "must be a lowercase SHA-256 hex digest"))
    if not asset.distributions:
        violations.append(_violation("distributions", "at least one distribution is required"))

    for distribution in asset.distributions:
        if distribution.provider in {"s3", "s3_compatible"} and not distribution.bucket:
            violations.append(_violation("distributions.bucket", "S3 distributions require a bucket"))
        if distribution.provider == "azure_blob" and not distribution.container:
            violations.append(
                _violation("distributions.container", "Azure Blob distributions require a container")
            )
        if distribution.provider != "filesystem" and not distribution.object_key:
            violations.append(
                _violation("distributions.object_key", "object storage distributions require an object key")
            )

    for assertion in asset.assertions:
        expected_kind = _RELATION_TARGETS[assertion.relation]
        if assertion.target_kind != expected_kind:
            violations.append(
                _violation(
                    "assertions.target_kind",
                    f"{assertion.relation} requires target_kind={expected_kind}",
                )
            )
        if assertion.target_kind == "file_asset" and not assertion.target_asset_id:
            violations.append(
                _violation(
                    "assertions.target_asset_id",
                    "file relationships require a content-addressed target asset IRI",
                )
            )
        if not _SHA256_RE.fullmatch(assertion.evidence_chunk_sha256):
            violations.append(
                _violation("assertions.evidence_chunk_sha256", "must be a lowercase SHA-256 hex digest")
            )
        if assertion.evidence_start < 0:
            violations.append(_violation("assertions.evidence_start", "must be non-negative"))
        if assertion.evidence_end <= assertion.evidence_start:
            violations.append(
                _violation("assertions.evidence_end", "must be greater than evidence_start")
            )

    violations.extend(_shacl_violations(asset))

    return {
        "asset_id": asset.asset_id,
        "shacl_compatible": True,
        "shacl_engine": "pyshacl",
        "shape": "CWLFileAssetShape",
        "conforms": not violations,
        "violations": violations,
    }


def concept_id(kind: str, label: str) -> str:
    digest = hashlib.sha256(label.strip().casefold().encode("utf-8")).hexdigest()[:24]
    return f"urn:cwl:{kind}:{digest}"


def assertion_target_id(assertion: SemanticAssertion) -> str:
    if assertion.target_kind == "file_asset":
        if not assertion.target_asset_id:
            raise ValueError("file assertion target is missing")
        return assertion.target_asset_id
    return concept_id(assertion.target_kind, assertion.target_label)


def distribution_node_id(asset: FileAsset, distribution: StorageDistribution) -> str:
    digest = hashlib.sha256(distribution.id.encode("utf-8")).hexdigest()[:24]
    return f"urn:cwl:distribution:{asset.sha256}:{digest}"


def file_asset_jsonld(asset: FileAsset, *, include_locations: bool = False) -> dict[str, Any]:
    """Export one file asset using the CWL application profile."""

    distributions: list[dict[str, Any]] = []
    for distribution in asset.distributions:
        item: dict[str, Any] = {
            "@id": distribution_node_id(asset, distribution),
            "@type": "dcat:Distribution",
            "cwl:storageProvider": distribution.provider,
            "cwl:endpointId": distribution.endpoint_id,
            "cwl:available": distribution.available,
        }
        if include_locations:
            item["dcat:accessURL"] = distribution.locator
        if distribution.version_id:
            item["dcat:version"] = distribution.version_id
        if distribution.etag:
            item["cwl:etag"] = distribution.etag
        distributions.append(item)

    subjects = []
    for assertion in asset.assertions:
        if assertion.target_kind == "file_asset":
            continue
        subject = {
            "@id": assertion_target_id(assertion),
            "@type": "skos:Concept",
        }
        subject["skos:prefLabel"] = assertion.target_label
        subjects.append(subject)
    assertions = [
        {
            "@type": "cwl:SemanticAssertion",
            "cwl:relation": {"@id": f"cwl:{assertion.relation}"},
            "cwl:target": {"@id": assertion_target_id(assertion)},
            "cwl:targetKind": assertion.target_kind,
            "cwl:confidence": assertion.confidence,
            "cwl:evidenceChunkSha256": assertion.evidence_chunk_sha256,
            "cwl:evidenceStart": assertion.evidence_start,
            "cwl:evidenceEnd": assertion.evidence_end,
            "cwl:extractionMethod": assertion.method,
            "cwl:reviewStatus": assertion.review_status,
        }
        for assertion in asset.assertions
    ]
    payload: dict[str, Any] = {
        "@context": _CONTEXT,
        "@id": asset.asset_id,
        "@type": ["dcat:Resource", "prov:Entity", "cwl:FileAsset"],
        "dcterms:identifier": asset.asset_id,
        "cwl:tenantId": asset.tenant_id,
        "dcterms:title": asset.title,
        "dcterms:format": asset.media_type,
        "dcat:byteSize": asset.byte_size,
        "spdx:checksum": {
            "@type": "spdx:Checksum",
            "spdx:algorithm": "spdx:checksumAlgorithm_sha256",
            "spdx:checksumValue": asset.sha256,
        },
        "dcat:distribution": distributions,
        "dcterms:subject": subjects,
        "cwl:assertion": assertions,
    }
    if asset.modified_at:
        payload["dcterms:modified"] = asset.modified_at.isoformat()
    return payload


_EDGE_TYPES = {
    "belongsToProject": "BELONGS_TO_PROJECT",
    "usesSystem": "USES_SYSTEM",
    "hasWorkPhase": "HAS_WORK_PHASE",
    "hasArtifactType": "HAS_ARTIFACT_TYPE",
    "hasTopic": "HAS_TOPIC",
    "wasDerivedFrom": "WAS_DERIVED_FROM",
    "previousVersion": "PREVIOUS_VERSION",
}


def get_file_asset(store: GraphStore, asset_id: str) -> FileAsset | None:
    node = store.get_node(asset_id)
    if node is None or node.kind != "file_asset":
        return None
    payload = node.properties.get("file_asset")
    return FileAsset.model_validate(payload) if isinstance(payload, dict) else None


def _merge_asset(existing: FileAsset | None, incoming: FileAsset) -> FileAsset:
    if existing is None:
        return incoming
    distributions = {item.id: item for item in existing.distributions}
    distributions.update({item.id: item for item in incoming.distributions})
    assertions = {
        (
            item.relation,
            item.target_kind,
            item.target_asset_id or item.target_label.strip().casefold(),
        ): item
        for item in existing.assertions
    }
    for item in incoming.assertions:
        key = (
            item.relation,
            item.target_kind,
            item.target_asset_id or item.target_label.strip().casefold(),
        )
        existing_assertion = assertions.get(key)
        if (
            existing_assertion is None
            or item.review_status != "proposed"
            or (
                existing_assertion.review_status == "proposed"
                and item.confidence > existing_assertion.confidence
            )
        ):
            assertions[key] = item
    return existing.model_copy(
        update={
            "distributions": list(distributions.values()),
            "assertions": list(assertions.values()),
            "modified_at": max(
                filter(None, (existing.modified_at, incoming.modified_at)),
                default=None,
            ),
        }
    )


def upsert_file_asset(store: GraphStore, asset: FileAsset) -> FileAsset:
    """Validate, merge and project one content-addressed asset into the graph."""

    report = validate_file_asset(asset)
    if not report["conforms"]:
        messages = "; ".join(item["message"] for item in report["violations"])
        raise ValueError(f"file asset does not conform: {messages}")
    existing_node = store.get_node(asset.asset_id)
    if existing_node is not None and existing_node.kind != "file_asset":
        raise ValueError("file asset identifier is occupied by a non-file node")
    existing = get_file_asset(store, asset.asset_id)
    existing_tenant = (
        existing.tenant_id
        if existing is not None
        else str((existing_node.properties if existing_node else {}).get("tenant_id") or "")
    )
    if existing_tenant and existing_tenant != asset.tenant_id:
        raise PermissionError("file asset tenant boundary denied")
    for assertion in asset.assertions:
        if assertion.target_kind != "file_asset":
            continue
        target = store.get_node(assertion_target_id(assertion))
        if target is not None and target.kind != "file_asset":
            raise ValueError("file relationship target is not a file asset node")
        target_tenant = str((target.properties if target else {}).get("tenant_id") or "")
        if target_tenant and target_tenant != asset.tenant_id:
            raise PermissionError("file relationship target tenant boundary denied")
    merged = _merge_asset(existing, asset)
    embedding_text = " ".join(
        [merged.title] + [assertion.target_label for assertion in merged.assertions]
    )
    store.upsert_node(
        merged.asset_id,
        "file_asset",
        label=merged.title,
        properties={
            "profile": "CWL File Knowledge Profile 0.1",
            "tenant_id": merged.tenant_id,
            "file_asset": merged.model_dump(mode="json"),
        },
        text=embedding_text,
    )

    for distribution in merged.distributions:
        distribution_id = distribution_node_id(merged, distribution)
        store.upsert_node(
            distribution_id,
            "distribution",
            label=distribution.id,
            properties={
                **distribution.model_dump(mode="json"),
                "tenant_id": merged.tenant_id,
            },
            text=f"{distribution.provider} {distribution.endpoint_id}",
        )
        store.upsert_edge("DISTRIBUTION", merged.asset_id, distribution_id)

    for assertion in merged.assertions:
        target_id = assertion_target_id(assertion)
        target_kind = assertion.target_kind
        if target_kind != "file_asset" or store.get_node(target_id) is None:
            store.upsert_node(
                target_id,
                target_kind,
                label=assertion.target_label,
                properties={
                    "skos_pref_label": assertion.target_label,
                    "review_status": assertion.review_status,
                    **(
                        {"tenant_id": merged.tenant_id}
                        if target_kind == "file_asset"
                        else {}
                    ),
                },
                text=assertion.target_label,
            )
        store.upsert_edge(
            _EDGE_TYPES[assertion.relation],
            merged.asset_id,
            target_id,
            properties={
                "confidence": assertion.confidence,
                "evidence_chunk_sha256": assertion.evidence_chunk_sha256,
                "evidence_start": assertion.evidence_start,
                "evidence_end": assertion.evidence_end,
                "method": assertion.method,
                "review_status": assertion.review_status,
            },
        )
    return merged
