from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sdp_core.contracts import masked_column_rules
from sdp_core.stores import UNRESOLVED_TENANT_ID

from .authz import can_access_tenant, has_role, resolve_actor_context
from .catalog import get_dataset, list_datasets
from .domain import PolicyDecision
from .evidence import record_policy_decision


def _effective_tenant_id(subject: str, resource: str, target_tenant_id: str | None = None) -> str:
    """Resolve which tenant an evidence row for this decision belongs to.

    A decision about an existing dataset belongs to the tenant that owns the
    dataset - that is the scope a tenant-scoped auditor queries for its own
    assets' access history. A decision that names no existing dataset (a
    ``create``, a discovery query, an unknown resource) has no owning tenant, so
    it belongs to the actor's. When neither resolves, the row is marked
    unresolved rather than attributed to a real tenant.
    """
    if target_tenant_id and can_access_tenant(subject, target_tenant_id):
        # A create names a tenant the catalog cannot yet confirm, so the caller
        # supplies it - but only a caller who can actually reach that tenant
        # decides where the row is filed.
        #
        # It used to be honoured unconditionally, and the role check in
        # ``evaluate`` runs *after* the stamp, so a caller with no actor at all
        # could choose another tenant's ledger. Measured with an unauthenticated
        # ``POST /catalog/datasets`` carrying ``tenant_id: "zeta-bank"``::
        #
        #     response -> 403 "create 작업은 admin 권한만 가능"
        #     decision -> subject=anonymous action=create resource=forged-probe
        #                 effect=deny  filed under tenant: zeta-bank
        #
        # readable by ``GET /policy/decisions?user=zeta-analyst`` and invisible
        # to the caller's own tenant. ``tenant_id`` is a free-form string, so
        # rows could also be filed under tenants that do not exist.
        #
        # The comment that justified the unconditional branch - "the owning
        # tenant's auditor sees attempts on its own assets" - does not apply
        # here: this row is for a caller refused on *role* grounds against a
        # tenant nobody verified. Keeping it in the refused caller's own scope
        # preserves the auditability goal without letting an anonymous request
        # pick the ledger.
        return target_tenant_id
    # ``graph_node_dataset_id`` first, because a graph node id is
    # ``<dataset>:<column>`` and ``get_dataset`` returns ``None`` for it. The
    # stamp therefore fell through to the actor's tenant for every column node,
    # while ``can_see_graph_node`` and ``graph_node_target_tenant`` - in this
    # same module - already strip that suffix.
    #
    # The consequence was not only a misfiled row. Because the stamp depended on
    # whether the id happened to resolve, a foreign-but-existing node filed to
    # the owner (invisible to the prober) while an absent one filed to the
    # prober (visible), so the prober's own ``GET /policy/decisions`` answered
    # "does this dataset exist" - the oracle three other families were repaired
    # to close.
    dataset = get_dataset(graph_node_dataset_id(resource) or resource)
    if dataset and dataset.tenant_id:
        return dataset.tenant_id
    return resolve_actor_context(subject).tenant_id or UNRESOLVED_TENANT_ID


def _decision(
    *, tenant_id: str, provenance: Mapping[str, Any] | None = None, **kwargs: Any
) -> PolicyDecision:
    """Record one policy decision, stamped with the tenant it belongs to.

    The evidence store scopes rows by ``obligations['tenant_id']``, so the stamp
    is applied on every branch rather than only the ones whose obligations
    happen to mention a tenant. A branch that sets the key explicitly keeps its
    own value.

    ``provenance`` is merged last and is how a caller marks a row as something
    other than a real access attempt - see :func:`evaluate`'s own parameter.
    """
    obligations = dict(kwargs.pop("obligations", None) or {})
    obligations.setdefault("tenant_id", tenant_id)
    if provenance:
        obligations.update(provenance)
    return record_policy_decision(PolicyDecision(obligations=obligations, **kwargs))


def evaluate_dataset_scope_refusal(subject: str, resource: str) -> PolicyDecision:
    """Record the deny a catalog-family scope refusal deserves, filed away from the prober.

    ``evaluate`` is wrong for this one job, and using it reopened the very
    oracle the refusal is part of closing. Measured with ``evaluate(subject,
    dataset_id, "search", "catalog")`` behind the 404, as the probing analyst:

        foreign id -> deny, filed to the owning tenant   -> prober sees 0 rows
        absent  id -> allow "카탈로그 발견 정책 통과",
                      filed to the prober's own tenant   -> prober sees 1 row

    So ``GET /policy/decisions`` answered the question the 404 refused to: a row
    appears exactly when the id is free. Both refusals are therefore recorded
    here instead, each filed outside the prober's scope - the owning tenant when
    there is one, the reserved ``unresolved`` scope when there is not - so the
    ledger reads the same from the prober's side either way while the owning
    tenant's auditor still sees attempts on its own assets.

    The effect is ``deny`` in both cases because the read was in fact refused;
    an ``allow`` row behind a 404 describes something that did not happen.
    """
    # ``<dataset>:<column>`` resolves through the suffix-stripping helper, the
    # same way ``_effective_tenant_id`` does. Without it a graph column node
    # read as "dataset not found" and filed to the reserved unresolved scope,
    # so the owning tenant's auditor still saw nothing.
    owner = get_dataset(graph_node_dataset_id(resource) or resource)
    owner_tenant_id = owner.tenant_id if owner else None
    return _decision(
        subject=subject,
        resource=resource,
        action="search",
        decision_id=str(uuid4()),
        tenant_id=owner_tenant_id or UNRESOLVED_TENANT_ID,
        effect="deny",
        reason="tenant boundary denied" if owner_tenant_id else "dataset not found",
        obligations={
            "refusal_cause": "tenant_scope" if owner_tenant_id else "absent_dataset",
        },
    )


def _is_admin(subject: str) -> bool:
    return has_role(subject, "admin", "platform-admin")


def _can_mutate(subject: str, action: str) -> bool:
    return _is_admin(subject) and action.lower() in {"create", "publish", "patch", "deprecate"}


# The published RBAC matrix grants `security` discover_catalog + view_schema and
# *denies* preview_data + run_governed_query. One combined reader gate granted all
# of them, so the role over-granted against its own published contract - and the
# default OIDC map `sdp-security -> ['security']` carries no platform-admin, so a
# real federated security reviewer got data access the matrix publishes as denied.
_DATA_READER_ROLES = ("data-analyst", "admin", "platform-admin")
_METADATA_READER_ROLES = (*_DATA_READER_ROLES, "security")

# Actions that release rows, versus actions that release only metadata.
# The status every surface must publish beside the row-level predicate, and the
# wording that tells a caller what to do about it. One definition, read by
# ``browse.preview`` and ``orchestrator.draft_sql``, so the three cannot drift
# into saying different things about the same obligation.
ROW_FILTER_ENFORCEMENT_STATUS = "declared_not_enforced"
ROW_FILTER_ENFORCEMENT_NOTE = (
    "선언된 행 레벨 조건이며 이 응답의 행에는 적용되지 않았습니다. "
    "행 레벨 집행은 Phase 2 범위이므로, 이 조건이 필요한 조회는 원본 시스템에서 직접 적용해야 합니다."
)
ROW_FILTER_ABSENT_NOTE = "이 조회에 선언된 행 레벨 조건이 없습니다."

_DATA_READ_ACTIONS = {"query", "preview"}
_METADATA_READ_ACTIONS = {"schema", "search", "list"}


def _has_reader_role(subject: str) -> bool:
    """Report whether the subject may read dataset *metadata*."""
    return has_role(subject, *_METADATA_READER_ROLES)


def _has_data_reader_role(subject: str) -> bool:
    """Report whether the subject may read dataset *rows*."""
    return has_role(subject, *_DATA_READER_ROLES)


# Every action this engine can decide. `evaluate` fell through to an `allow` at
# the end of its branch chain, so any action it did not recognize was permitted:
#
#   evaluate(subject="analyst", action="administer_tenants", ...)  -> allow
#   evaluate(subject="analyst", action="totally_made_up",    ...)  -> allow
#
# and `POST /policy/decision` takes `action` verbatim from an unauthenticated
# request body, so the published policy API answered `allow` for anything and
# recorded that answer as evidence. Worse, the RBAC matrix's own
# `action_catalog` is spelled verb_noun (`patch_dataset`) while this engine
# matches bare verbs (`patch`), so *every one* of the ten published action names
# was unrecognized - including the four the matrix publishes as denied to
# data-analyst, and `administer_tenants`.
KNOWN_ACTIONS = frozenset(
    {
        "create",
        "deprecate",
        "discover",
        "list",
        "patch",
        "preview",
        "publish",
        "query",
        "schema",
        "search",
        "search_catalog",
    }
)

# The published RBAC vocabulary, mapped onto the engine's. These are two
# spellings of one action, not two policies: `patch_dataset` in the matrix and
# `patch` here decide the same thing, so the matrix becomes testable against the
# engine instead of being prose nobody can check.
CATALOG_ACTION_ALIASES = {
    "deprecate_dataset": "deprecate",
    "discover_catalog": "search",
    "patch_dataset": "patch",
    "preview_data": "preview",
    "publish_dataset": "publish",
    "register_dataset": "create",
    "run_governed_query": "query",
    "view_schema": "schema",
}

# The two published actions with no engine equivalent. They are refused with
# their own reason rather than folded into "unknown action": the matrix grants
# `review_security_evidence` to `security` and `administer_tenants` to
# `platform-admin`, so what they should decide is a product question, and a
# distinct refusal keeps that gap visible instead of making it look like a typo.
UNMAPPED_CATALOG_ACTIONS = frozenset({"administer_tenants", "review_security_evidence"})


# The discovery branch keys on the **action**, and four planes route through it:
# the catalog, the evidence ledgers, the ontology proposal queue and the
# knowledge graph. Its reason named one of them. The previous repair of this
# string set the right criterion for itself - "worded for every caller this
# branch refuses" - and met it for the callers it had enumerated, which is why
# an unauthenticated read of ``/policy/decisions`` or ``/graph/nodes/{id}`` was
# told that catalog access requires authentication.
#
# Worded from a declared plane rather than from ``resource`` itself, because the
# branch is also reached with values that are **assets**: ``_authorize_graph_read``
# forwards a node id, and ``evaluate(..., resource="crm-customer-master",
# action="search")`` returns this same decision. Echoing the resource would
# reopen the existence oracle the dataset routes' 404 exists to close - a reason
# may name the caller's plane and never the asset it asked about - so anything
# not declared here falls back to a sentence that names neither.
#
# Every variant keeps ``인증된 사용자만``: ``_catalog_mutation_refusal`` answers a
# scope-less mutation caller with this same decision and
# ``tests/test_api.py`` reads that phrase, so it is a contract across the
# variants rather than a property of one string.
REFUSAL_PLANES = {
    "catalog": "카탈로그 접근은 인증된 사용자만 가능합니다.",
    # ``접근``, not ``읽기``: ``POST /ontology/patches`` reaches this branch as a
    # write that reuses the discovery decision as its authentication check, and
    # the previous repair of this string generalized ``목록 조회`` to ``접근``
    # for the same reason. A plane word plus ``접근`` is true for every caller of
    # that plane, which is the criterion this vocabulary exists to meet.
    "evidence": "증빙 원장 접근은 인증된 사용자만 가능합니다.",
    "ontology/patches": "온톨로지 제안 큐 접근은 인증된 사용자만 가능합니다.",
    "graph": "지식 그래프 접근은 인증된 사용자만 가능합니다.",
}
# Names no plane and no asset, so it is true for every caller and leaks nothing.
REFUSAL_PLANE_UNDECLARED = "이 요청은 인증된 사용자만 가능합니다."


def discovery_refusal_reason(resource: str) -> str:
    """What an unauthenticated caller is told, by the plane it asked about.

    Two different asset ids must produce the identical sentence; that is the
    property ``tests/test_refusals_name_their_own_plane.py`` re-asserts, and the
    reason the lookup has no fallthrough to the resource.
    """
    return REFUSAL_PLANES.get(resource, REFUSAL_PLANE_UNDECLARED)


def evaluate(
    subject: str,
    resource: str,
    action: str,
    purpose: str,
    *,
    target_tenant_id: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> PolicyDecision:
    """Evaluate one policy question and record the decision.

    ``provenance``, when given, is merged into the recorded row's obligations.
    **Every** branch must pass it. Three did not, and they were reachable:
    measured as ``analyst`` asking about ``external-analyst``, the hypothetical
    answers for ``discover_catalog`` (allow), ``register_dataset`` (deny) and
    ``search`` (allow) landed in the other tenant's ledger with no label at all,
    so that tenant's steward read a question about their user as an event and
    nothing recorded who asked. ``tests/test_hypothetical_decisions_are_labelled.py``
    walks this function's AST so a new branch cannot omit the argument.
    It exists for ``POST /policy/decision``, whose whole purpose is answering
    "what would policy say for this subject" - a question whose answer is
    **hypothetical** and was being persisted into the compliance ledger
    unlabelled, attributed to a subject the caller named, with no record of who
    actually asked. Measured as ``analyst`` asking about ``external-analyst``::

        POST /policy/decision {"user": "analyst", "subject": "external-analyst",
                               "resource": "crm-event", "action": "preview"}
        -> 200 {"subject": "external-analyst", "effect": "deny",
                "reason": "tenant boundary denied", ...}
        rows now readable naming external-analyst:
          [{"subject": "external-analyst", "resource": "crm-event",
            "action": "preview", "effect": "deny", ...}]

    An auditor reading that row sees a refused preview attempt by a different
    identity in a different tenant. No such attempt happened, and nothing in the
    row named the caller who manufactured it. ``subject`` stays caller-supplied,
    because that is the route's purpose; what the row gains is the two facts that
    make it honest.
    """
    action_key = action.strip().lower()
    action_key = CATALOG_ACTION_ALIASES.get(action_key, action_key)
    # ``purpose`` is the other caller-controlled dimension this function
    # branches on, and it was compared raw while ``action`` was normalized four
    # lines above. The denial for ``external-export`` used ``.lower()`` with no
    # ``.strip()``, so the headline purpose-binding control was defeated by one
    # space. Measured against a data-analyst with no export approval::
    #
    #     preview  purpose='external-export'    -> 403 (operator approval required)
    #     preview  purpose='EXTERNAL-EXPORT'    -> 403
    #     preview  purpose=' external-export'   -> 200
    #     preview  purpose='external-export '   -> 200
    #     preview  purpose='external-export\t'  -> 200
    #     query    purpose='external-export'    -> 403 DENIED
    #     query    purpose=' external-export'   -> 200 SUCCEEDED
    #
    # and the recorded decision then read ``effect: allow``, so the evidence
    # ledger a compliance team reads certified the export as policy-approved.
    # Because the *casing* variant was blocked, nothing told an integrator the
    # field was whitespace-sensitive.
    #
    # The row-filter obligation had the mirror-image bug on the same field: it
    # compared ``purpose == "analysis"`` exactly, so the only row filter the
    # engine emits silently vanished for ``'Analysis'`` or ``' analysis'``::
    #
    #     crm-event (high) purpose='analysis'  -> applied_row_filter=[...]
    #     crm-event (high) purpose='Analysis'  -> applied_row_filter=None
    #     crm-event (high) purpose=' analysis' -> applied_row_filter=None
    #
    # One normalization at the entry point fixes both, and keeps the two
    # branches from drifting apart again.
    purpose_key = purpose.strip().lower()
    decision_id = str(uuid4())
    decision_base = {
        "subject": subject,
        "resource": resource,
        "action": action,
        "decision_id": decision_id,
        "tenant_id": _effective_tenant_id(subject, resource, target_tenant_id),
    }

    if action_key in UNMAPPED_CATALOG_ACTIONS:
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="이 action은 아직 정책 엔진에 매핑되지 않았습니다.",
            obligations={"unmapped_published_action": action_key},
        )

    if action_key not in KNOWN_ACTIONS:
        # Fail closed. An engine that answers "allow" to an action it does not
        # understand is wrong under any policy design, and this one is also the
        # published decision API. The known set is returned so the caller can see
        # what is evaluable instead of guessing.
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="평가할 수 없는 action입니다.",
            obligations={"known_actions": sorted(KNOWN_ACTIONS)},
        )

    if action_key == "create":
        if not _is_admin(subject):
            return _decision(
                **decision_base,
                provenance=provenance,
                effect="deny",
                reason="create 작업은 admin 권한만 가능",
                obligations={"required_role": "admin"},
            )
        # Every other action resolves the owning tenant from the catalog and checks
        # it below. A create cannot: the dataset does not exist yet, so the target
        # tenant arrives in the request. Without this check an admin in one tenant
        # writes into another tenant's catalog namespace - and is then correctly
        # refused on the asset it just planted, which is the tell.
        if target_tenant_id and not can_access_tenant(subject, target_tenant_id):
            return _decision(
                **decision_base,
                provenance=provenance,
                effect="deny",
                reason="tenant boundary denied",
                obligations={
                    "tenant_id": target_tenant_id,
                    "actor_tenant_id": resolve_actor_context(subject).tenant_id,
                },
            )
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="allow",
            reason="관리자 권한으로 catalog mutation 권한 통과",
            obligations={"required_role": "admin"},
        )

    if action_key in {"search", "search_catalog", "discover"}:
        if _has_reader_role(subject):
            return _decision(
                **decision_base,
                provenance=provenance,
                effect="allow",
                reason="카탈로그 발견 정책 통과",
                obligations={"masking": []},
            )
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason=discovery_refusal_reason(resource),
            obligations={"required_role": "data-analyst"},
        )

    dataset = get_dataset(resource)
    if not dataset:
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="존재하지 않는 데이터셋입니다.",
        )

    actor_context = resolve_actor_context(subject)
    if not can_access_tenant(subject, dataset.tenant_id):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="tenant boundary denied",
            obligations={"tenant_id": dataset.tenant_id, "actor_tenant_id": actor_context.tenant_id},
        )

    if dataset.sensitivity == "critical" and not _is_admin(subject):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="critical 민감도 자산은 별도 심사 필요",
            obligations={"redact": True, "masking": True},
        )

    if purpose_key == "external-export" and not _is_admin(subject):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="외부 반출 목적은 데이터 운영자 승인 필요",
            obligations={"required_role": "data-admin"},
        )

    if action_key in {"publish", "patch", "deprecate"} and not _can_mutate(subject, action_key):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="catalog mutation 작업은 admin 권한만 가능",
            obligations={"required_role": "admin"},
        )

    if action_key in _DATA_READ_ACTIONS and not _has_data_reader_role(subject):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="조회 권한이 없습니다.",
            obligations={"required_role": "data-analyst"},
        )

    if action_key in _METADATA_READ_ACTIONS and not _has_reader_role(subject):
        return _decision(
            **decision_base,
            provenance=provenance,
            effect="deny",
            reason="조회 권한이 없습니다.",
            obligations={"required_role": "data-analyst"},
        )

    row_filter = []
    if action_key in {"query", "preview"} and purpose_key == "analysis" and dataset.sensitivity == "high":
        row_filter.append("business_unit = current_user_unit")

    # POL-003 names three classification bases - PII, sensitive, confidential -
    # and this read only the ``pii`` bool, so a column classified sensitive or
    # confidential was released. Its acceptance criterion also asks the decision
    # to carry the masking *rule*; a bare list of names says which columns and
    # not on what grounds, so an auditor could not tell a PII mask from a
    # confidentiality mask, nor notice that two of the three declared bases were
    # never consulted. ``masking`` keeps its shape - ``browse.apply_mask`` and
    # the published response both read it - and ``masking_rules`` carries why.
    masking_rules = masked_column_rules(dataset.schema)
    obligations = {
        "tenant_id": dataset.tenant_id,
        "masking": [rule["column"] for rule in masking_rules],
        "masking_rules": masking_rules,
    }
    if row_filter:
        obligations["row_filter"] = row_filter
        # And what the engine does with it, because the answer is "nothing".
        # ``docs/prd-trd.md`` §6.2 puts row-level filtering in Phase 2, so the
        # absence of enforcement is the intended scope - but every surface
        # published the predicate as though it had governed the read. Measured on
        # ``crm-event``, the only ``sensitivity: high`` dataset this reaches::
        #
        #     published columns           ['event_id', 'customer_id',
        #                                  'event_timestamp', 'device_id']
        #     'business_unit' among them  False
        #     purpose='analysis'   applied_row_filter=[...]  row_count=2
        #     purpose='marketing'  applied_row_filter=None   row_count=2
        #     rows byte-identical         True
        #
        # The predicate names a column the dataset does not declare, and the rows
        # returned "with the filter" are the same bytes as the rows returned
        # without it. Carrying the status in the obligation itself - rather than at
        # each publishing surface - is what keeps a fifth consumer of the decision
        # from echoing the predicate bare.
        obligations["row_filter_enforcement"] = ROW_FILTER_ENFORCEMENT_STATUS

    return _decision(
        **decision_base,
        provenance=provenance,
        effect="allow",
        reason="거버넌스 정책 조건 충족",
        obligations=obligations,
    )


def is_mutable(subject: str, action: str, resource: str) -> bool:
    decision = evaluate(subject=subject, resource=resource, action=action, purpose="analysis")
    return decision.effect == "allow"


# --- graph read visibility ------------------------------------------------
#
# Graph dataset and column nodes carry the same governed content the catalog
# does - a column node's properties include its ``pii`` classification. Entry
# gating alone cannot scope the graph: traversal walks through shared business
# concept nodes, so a start node in one tenant reaches another tenant's datasets
# at depth 2. Visibility is therefore decided per node.


def graph_node_dataset_id(node_id: str) -> str | None:
    """Return the dataset a graph node belongs to, or ``None`` if it belongs to none.

    Dataset nodes are keyed by the dataset id and column nodes by
    ``"<dataset_id>:<column_name>"``, so the owning dataset is the part before the
    first colon. A node whose prefix names no dataset - a business concept or
    glossary term - is not dataset-owned.
    """
    dataset = get_dataset(node_id.split(":", 1)[0])
    return dataset.id if dataset else None


def can_see_graph_node(subject: str, node_id: str) -> bool:
    """Decide whether a subject may see one graph node.

    A dataset-owned node inherits its dataset's tenant, so the boundary that gates
    ``/browse/{id}/schema`` applies. Nodes that belong to no dataset are not
    tenant-owned and stay visible to any authorized reader.
    """
    dataset_id = graph_node_dataset_id(node_id)
    if dataset_id is None:
        return True
    dataset = get_dataset(dataset_id)
    if not dataset:
        return True
    return can_access_tenant(subject, dataset.tenant_id)


def graph_node_target_tenant(node_id: str) -> str | None:
    """The tenant that owns this graph node, or ``None`` if it is not dataset-owned.

    The write counterpart to :func:`can_see_graph_node`, and it exists because
    the two directions disagreed. ``_authorize_graph_write`` evaluated the
    ``create`` action with no ``target_tenant_id``, and ``create`` is the one
    branch that cannot resolve the owning tenant from the catalog itself, so it
    skipped the tenant check entirely. The role check ran; the boundary did not.
    Measured with a tenant-``zeta`` dataset and a ``data-admin`` whose tenant is
    ``demo``::

        READ  /graph/nodes/zeta-secret:customer_email  -> 404 node not found
        WRITE /graph/nodes  {node_id: zeta-secret:customer_email,
                             properties: {pii: false}}
                                                      -> 200 upserted
        READ as platform-admin, before -> {'datatype': 'string', 'pii': True}
        READ as platform-admin, after  -> {'pii': False, 'datatype': 'string'}

    So the tenant boundary was read-only: a foreign admin could flip the ``pii``
    classification of a column it cannot even read, silently, on governed
    metadata that feeds ``POST /search/semantic`` and ``POST /graph/query``.

    A node that belongs to no dataset (a concept) is shared vocabulary and has
    no owning tenant, which is the same answer :func:`can_see_graph_node` gives
    on the read side - the two must agree or the boundary is inconsistent again.
    """
    dataset_id = graph_node_dataset_id(node_id)
    if dataset_id is None:
        return None
    dataset = get_dataset(dataset_id)
    # An id shaped like a dataset node whose dataset does not exist is not
    # tenant-owned, matching the read predicate. It cannot reach another
    # tenant's content, because there is no content there to reach.
    return dataset.tenant_id if dataset else None


def filter_graph_traversal(subject: str, traversal: dict[str, Any]) -> dict[str, Any]:
    """Withhold traversal nodes the subject may not see, and the edges touching them.

    An edge left pointing at a withheld node would disclose that the node exists,
    so edges are dropped with their endpoints. The withheld count is reported
    rather than silently truncating the result.
    """
    nodes = traversal.get("nodes") or []
    visible_nodes = [node for node in nodes if can_see_graph_node(subject, node.get("node_id", ""))]
    visible_ids = {node.get("node_id") for node in visible_nodes}
    edges = traversal.get("edges") or []
    visible_edges = [
        edge
        for edge in edges
        if edge.get("source_id") in visible_ids and edge.get("target_id") in visible_ids
    ]
    return {
        **traversal,
        "nodes": visible_nodes,
        "edges": visible_edges,
        "withheld_node_count": len(nodes) - len(visible_nodes),
        "withheld_edge_count": len(edges) - len(visible_edges),
    }


def filter_graph_search_results(subject: str, results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Withhold semantic-search hits the subject may not see.

    Returns the visible hits and how many were withheld. The result count drops
    below the requested limit rather than being backfilled: backfilling would let
    a caller infer how many neighbours it cannot see.
    """
    visible = [result for result in results if can_see_graph_node(subject, result.get("node_id", ""))]
    return visible, len(results) - len(visible)


def scope_concept_graph(subject: str, graph: dict[str, Any]) -> dict[str, Any]:
    """Withhold the dataset identity in a concept graph the subject may not see.

    ``dataset_ids`` is dataset identity, and this payload has now leaked it
    three times through three different callers. The first two were
    ``POST /llm/search`` and ``GET /ontology/concept/{concept}``, both fixed by
    giving ``ontology.concept_assets`` a tenant scope. The third,
    ``GET /ontology/term/{term}/graph``, reads the *graph store's* own
    ``concept_graph`` instead and took no actor at all. Measured, with a
    tenant-``zeta`` dataset present and no credential of any kind::

        anon GET /ontology/concept/고객     -> dataset_ids [], withheld 4
        anon POST /llm/search              -> 403
        anon GET /ontology/term/고객/graph  -> 200, dataset_ids
            ['crm-customer-master', 'marketing-campaign', 'sales-order',
             'semantic-glossary', 'zeta-secret']
        ledger delta for that call: decisions +0  audits +0

    So the one fact two sibling routes refuse was handed over in full, including
    a foreign tenant's dataset, with no policy decision and no audit event -
    contradicting the product's own published guardrail ("No unauthorized
    dataset existence disclosure", ``sdp_core.kpis``) and the governance
    invariant that a governed read evaluates policy and records evidence.

    Scoping lives here rather than in the store so the store stays a data layer
    with no policy opinion, and
    ``tests/test_concept_graph_scope.py::test_every_route_returning_dataset_ids_is_scoped``
    enumerates the routes that return this field rather than trusting that the
    third caller was the last one.
    """
    dataset_ids = graph.get("dataset_ids")
    if not isinstance(dataset_ids, list):
        return graph
    tenant_ids = accessible_tenant_ids(subject)
    if tenant_ids is None:
        return {**graph, "withheld_dataset_count": 0}
    visible = {dataset.id for dataset in list_datasets(tenant_ids)}
    scoped = [dataset_id for dataset_id in dataset_ids if dataset_id in visible]
    return {
        **graph,
        "dataset_ids": scoped,
        # Declared, so a short list does not read as the whole mapping - the
        # same rule ``concept_assets`` follows.
        "withheld_dataset_count": len(dataset_ids) - len(scoped),
    }


def accessible_tenant_ids(subject: str) -> list[str] | None:
    """Return the tenants whose evidence a subject may read.

    ``None`` means every tenant and is reserved for the explicit platform-admin
    crossing. An actor with no resolvable tenant gets an empty list, which the
    store turns into "no rows" rather than an unscoped read - a reader with no
    tenant must not fall through to everyone's evidence.
    """
    context = resolve_actor_context(subject)
    if "platform-admin" in context.roles:
        return None
    return [context.tenant_id] if context.tenant_id else []
