"""A caller could not reach the evidence rows their own 200 named.

``GET /policy/decisions``, ``GET /audit/events`` and
``GET /catalog/datasets/{id}/audit`` publish ``limit`` (≤500, ≤500 and ≤200) and
``resource``/``user``, and every store orders newest-first and then truncates -
``evidence.py``'s in-memory fallback with ``decisions[:limit]``, SQLite and
Postgres with ``ORDER BY recorded_at DESC LIMIT ?``. So the caller's own row is
the **first** to fall out. Measured at ``dba2403`` on the documented journey::

    policy_decision_id the caller holds from its own 200
      immediately       : reachable (2 rows in scope)
      after 600 requests: unreachable (500 rows in scope, all newer)

    published parameters: /policy/decisions -> limit(500), resource, user
                          /audit/events     -> limit(500), resource, user
    offset=500 / cursor=x / decision_id=abc -> accepted and ignored
    /policy/decisions?limit=1000            -> 422 less_than_equal

The response hands over ``request_id``, ``query_id`` and ``policy_decision_id``,
and the audit row carries all three, yet no read route accepted any of them as a
filter and there was no way to page back. An analyst proving what they ran, or an
auditor reconstructing who read a dataset, could do it on an idle ledger and not
after a demo afternoon - and ``resource``, the only selector offered, is exactly
the dimension that fills up.

Both evidence tables already carry a first-class ``decision_id`` column in both
SQL stores, so the id filter is an indexed comparison rather than a JSON probe.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app
from sdp_core.contracts import AuditEvent, PolicyDecision


client = TestClient(app)

DATASET = "crm-customer-master"
FLOOD = 600


def _one_governed_read() -> tuple[str, int]:
    """Drive one preview and return its decision id and the audit row count."""
    response = client.post(
        f"/browse/{DATASET}/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 2},
    )
    assert response.status_code == 200, response.text
    return response.json()["policy_decision_id"], len(catalog._AUDIT_LOG)


def _flood(count: int = FLOOD) -> None:
    """Record ``count`` newer rows the way ordinary traffic would.

    Recorded through the evidence recorders rather than through HTTP because the
    rows' provenance does not matter to retrieval and 600 requests is a slow way
    to say "newer rows exist".
    """
    for index in range(count):
        evidence.record_policy_decision(
            PolicyDecision(
                subject="anonymous",
                resource=DATASET,
                action="preview",
                effect="deny",
                obligations={"tenant_id": "demo"},
            )
        )
        catalog.ingest_event(
            event_type="browse.preview",
            actor="anonymous",
            dataset_id=DATASET,
            decision="denied",
            reason="flood",
            details={"index": index},
        )


def _rows(path: str, **params: Any) -> list[dict[str, Any]]:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(f"{path}?{query}")
    assert response.status_code == 200, response.text
    body = response.json()
    return body if isinstance(body, list) else body.get("items", [])


def test_the_decision_id_the_caller_holds_is_a_filter() -> None:
    """The most direct remedy for the complaint: ask for the row by its id."""
    decision_id, _ = _one_governed_read()
    _flood()

    decisions = _rows("/policy/decisions", user="admin", decision_id=decision_id)
    assert [row["decision_id"] for row in decisions] == [decision_id], len(decisions)

    events = _rows("/audit/events", user="admin", decision_id=decision_id)
    assert events, "the audit row carrying that decision id is unreachable"
    assert {row["decision_id"] for row in events} == {decision_id}


def test_an_older_row_is_reachable_by_paging_past_the_newer_ones() -> None:
    """Depth, not just identity: the window can be moved."""
    decision_id, _ = _one_governed_read()
    _flood()

    seen: set[str] = set()
    for offset in range(0, FLOOD + 500, 500):
        page = _rows("/policy/decisions", user="admin", limit=500, offset=offset, resource=DATASET)
        if not page:
            break
        seen.update(row["decision_id"] for row in page)
        if decision_id in seen:
            break
    assert decision_id in seen, (
        f"paging to offset {FLOOD + 500} never reached the caller's own row; "
        f"{len(seen)} rows were walked"
    )


def test_one_read_partitions_cleanly_and_two_reads_drift_by_their_own_rows() -> None:
    """What an offset guarantees here, measured rather than assumed.

    Within **one** snapshot the offset partitions exactly: rows 0-19 and rows
    20-39 of the same list share nothing. Across **two requests** it does not,
    and the reason is this product's own invariant - every policy evaluation is
    recorded, so authorizing an evidence read appends a row to the ledger being
    read, at the head, which shifts every later page by one. The first version of
    this test asserted a clean partition across two HTTP calls and failed on
    exactly that drift.

    A positional offset therefore reaches older rows (which is the defect being
    repaired: they were unreachable at any limit) without being a stable cursor.
    Making it one needs a ``before``-cursor, and that needs the decision's
    ``recorded_at`` published - which POL-005 records as absent.
    """
    _flood(40)
    # One snapshot, through the reader the route calls.
    whole = evidence.list_policy_decisions(limit=40, offset=0)
    first = evidence.list_policy_decisions(limit=20, offset=0)
    second = evidence.list_policy_decisions(limit=20, offset=20)
    assert len(first) == len(second) == 20
    assert not {row.decision_id for row in first} & {row.decision_id for row in second}
    assert [row.decision_id for row in whole] == [row.decision_id for row in first] + [
        row.decision_id for row in second
    ]

    # Two requests: the drift is the reads' own rows, and it is bounded by them.
    before = len(evidence._POLICY_DECISION_LOG)
    page_one = _rows("/policy/decisions", user="admin", limit=20, offset=0)
    page_two = _rows("/policy/decisions", user="admin", limit=20, offset=20)
    appended = len(evidence._POLICY_DECISION_LOG) - before
    overlap = {row["decision_id"] for row in page_one} & {row["decision_id"] for row in page_two}
    assert appended >= 1, "an evidence read records no decision at all"
    assert len(overlap) <= appended, (len(overlap), appended)


def test_the_dataset_scoped_audit_route_pages_too() -> None:
    """The per-dataset path a steward actually opens."""
    _flood(300)
    first = _rows(f"/catalog/datasets/{DATASET}/audit", user="admin", limit=200, offset=0)
    second = _rows(f"/catalog/datasets/{DATASET}/audit", user="admin", limit=200, offset=200)
    assert len(first) == 200, len(first)
    assert second, "the second page is empty although more rows exist"
    assert not {row["id"] for row in first} & {row["id"] for row in second}


def test_an_unknown_decision_id_is_an_empty_answer_not_a_wrong_one() -> None:
    """A filter that silently matches everything is worse than none."""
    _flood(5)
    assert _rows("/policy/decisions", user="admin", decision_id="no-such-decision") == []
    assert _rows("/audit/events", user="admin", decision_id="no-such-decision") == []


def test_the_published_parameters_name_what_the_routes_accept() -> None:
    """``offset`` and ``decision_id`` used to be accepted and ignored."""
    document = client.get("/openapi.json").json()
    for path in ("/policy/decisions", "/audit/events"):
        names = {item["name"] for item in document["paths"][path]["get"]["parameters"]}
        assert {"limit", "offset", "decision_id", "resource", "user"} <= names, (path, names)
    dataset_names = {
        item["name"]
        for item in document["paths"]["/catalog/datasets/{dataset_id}/audit"]["get"]["parameters"]
    }
    assert {"limit", "offset", "user"} <= dataset_names, dataset_names


def test_a_negative_offset_is_refused_rather_than_wrapped() -> None:
    """``[-1:]`` would answer with the oldest row and call it page -1."""
    assert client.get("/policy/decisions?user=admin&offset=-1").status_code == 422
    assert client.get("/audit/events?user=admin&offset=-1").status_code == 422
    assert client.get(f"/catalog/datasets/{DATASET}/audit?user=admin&offset=-1").status_code == 422


def test_the_sqlite_store_pages_and_filters_in_sql(tmp_path) -> None:
    """The documented store, driven directly, because the suite configures none.

    ``SDP_DATABASE_DSN``/``SDP_SQLITE_PATH`` are unset under pytest, so every
    other test here exercises the in-memory fallback and the ``LIMIT ? OFFSET ?``
    added to both SQL stores would otherwise be unmeasured. SQLite is the
    documented local store and needs no service, so it is driven here; the
    Postgres path shares the same code shape and stays covered only by the
    signature guard below, which this file says out loud rather than implying.
    """
    from sdp_core.stores import SQLiteEvidenceStore

    store = SQLiteEvidenceStore(str(tmp_path / "evidence.sqlite3"))
    recorded = []
    for index in range(5):
        decision = PolicyDecision(
            subject="analyst",
            resource=DATASET,
            action="preview",
            effect="allow",
            obligations={"tenant_id": "demo"},
        )
        store.record_decision(decision)
        recorded.append(decision.decision_id)
        store.append_event(
            AuditEvent(
                id=f"sqlite-probe-{index}",
                actor="analyst",
                action="browse.preview",
                resource=DATASET,
                result="allowed",
                decision_id=decision.decision_id,
                details={"index": index},
            )
        )

    newest_first = [row.decision_id for row in store.list_decisions(limit=5)]
    assert set(newest_first) == set(recorded)
    paged = [row.decision_id for row in store.list_decisions(limit=2, offset=2)]
    assert paged == newest_first[2:4], (paged, newest_first)
    assert [row.decision_id for row in store.list_decisions(decision_id=recorded[0])] == [
        recorded[0]
    ]
    assert store.list_decisions(decision_id="no-such-decision") == []
    assert [row.decision_id for row in store.list_events(decision_id=recorded[1])] == [
        recorded[1]
    ]
    events_paged = store.list_events(limit=2, offset=2)
    assert len(events_paged) == 2
    assert {row.id for row in events_paged}.isdisjoint(
        {row.id for row in store.list_events(limit=2, offset=0)}
    )


def test_a_deep_page_reaches_rows_only_the_store_holds(tmp_path) -> None:
    """The merge has to over-fetch, or the deeper page loses the store's rows.

    ``catalog.list_audit_events`` merges its own in-memory log with the store's
    page and then slices. If the store is asked for only ``limit`` rows, the rows
    at ``offset..offset+limit`` that exist **only** in the store are never
    fetched, so a deep page silently answers short. With no store configured -
    which is every other test here - that cannot be observed, so this one
    configures the documented SQLite store and restores it afterwards.
    """
    from sdp_core.stores import SQLiteEvidenceStore

    store = SQLiteEvidenceStore(str(tmp_path / "deep.sqlite3"))
    for index in range(60):
        store.append_event(
            AuditEvent(
                id=f"store-only-{index:03d}",
                actor="analyst",
                action="browse.preview",
                resource=DATASET,
                result="allowed",
                details={"index": index},
            )
        )
    previous = evidence.configure_evidence_store(store)
    try:
        deep = catalog.list_audit_events(limit=20, offset=40, resource=DATASET)
        assert len(deep) == 20, (
            "the deep page answered short, so the merge did not fetch the rows "
            f"only the store holds: {len(deep)}"
        )
        shallow_ids = {row.id for row in catalog.list_audit_events(limit=20, offset=0, resource=DATASET)}
        assert not shallow_ids & {row.id for row in deep}
    finally:
        evidence.configure_evidence_store(previous)


def test_the_in_memory_fallback_and_the_store_protocol_agree_on_the_signature() -> None:
    """Both read paths take the same two new arguments.

    The store is selected at import from the environment, so the suite normally
    exercises only the in-memory fallback; asserting the protocol's signature is
    what keeps the SQLite and Postgres paths from drifting out of it unnoticed.
    """
    import inspect

    from sdp_core.stores import PostgresEvidenceStore, SQLiteEvidenceStore

    # Both concrete stores, because ``evidence.EvidenceStore`` is a union alias
    # rather than a protocol class: there is nothing to assert a signature on but
    # the two implementations the documented deployments select.
    for owner in (SQLiteEvidenceStore, PostgresEvidenceStore):
        for name in ("list_decisions", "list_events"):
            parameters = inspect.signature(getattr(owner, name)).parameters
            assert "offset" in parameters, (owner.__name__, name)
            assert "decision_id" in parameters, (owner.__name__, name)
    # ``list_audit_events`` lives in ``catalog``, which merges the store's page
    # with its own in-memory log; ``evidence`` owns the decisions reader and the
    # persisted-events reader. Naming the wrong module here was how the first
    # version of this guard failed.
    for reader in (
        evidence.list_policy_decisions,
        catalog.list_audit_events,
        catalog.get_dataset_audit_events,
    ):
        parameters = inspect.signature(reader).parameters
        assert "offset" in parameters, reader.__name__
    for reader in (evidence.list_policy_decisions, catalog.list_audit_events):
        assert "decision_id" in inspect.signature(reader).parameters, reader.__name__
