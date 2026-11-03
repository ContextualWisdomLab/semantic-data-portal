"""``POST /ontology/resolve``'s ``aliases`` asserted synonymy the vocabulary denies.

The field accumulated three different things into one list: the concept itself,
the concept's declared aliases that appear in the text, and - the contamination -
**the first mapped dataset's business terms** that appear in the text. The two
sibling routes publishing a field of the same name return the concept's real
alias set, and measured identical to each other. At ``bb32066``::

    POST /ontology/resolve {"text": "이탈 고객"}
      term=고객        aliases=['고객', '이탈']
      term=활성 고객    aliases=['고객', '이탈']
      term=이탈        aliases=['고객', '이탈']
      term=비즈니스 용어 aliases=['고객', '이탈']
      term=이탈 고객    aliases=['churn 고객', '이탈 고객', '탈퇴 고객', '휴면 고객']   <- correct

    GET  /ontology/search?q=고객        aliases=['고객','customer','클라이언트','이용자','회원']
    GET  /ontology/concept/고객         aliases=['고객','customer','클라이언트','이용자','회원']

    POST /ontology/resolve {"text": "매출"}
      term=매출  aliases=['매출']   defined_in_vocabulary=True
      term=전환  aliases=['매출']   defined_in_vocabulary=False

So concept 전환 - which the glossary does not define at all - was published with
매출 as its alias, and the one row carrying a genuine alias set (the exact-phrase
match, which comes from the other branch) made the field look trustworthy. A
glossary or synonym-expansion UI built on this route records false synonymy.

The matched tokens are real information - they are *why* the concept scored - so
they keep their place under a name that says what they are.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app)


def _resolved(text: str) -> dict[str, dict]:
    response = client.post("/ontology/resolve", json={"text": text})
    assert response.status_code == 200, response.text
    return {row["term"]: row for row in response.json()["resolved"]}


def _sibling_aliases(concept: str) -> list[str]:
    search = client.get(f"/ontology/search?q={concept}").json()
    rows = [row for row in search["matches"] if row["concept"] == concept]
    assert rows, (concept, search)
    detail = client.get(f"/ontology/concept/{concept}?user=analyst").json()
    assert sorted(rows[0]["aliases"]) == sorted(detail["aliases"]), (
        "the two sibling routes already disagree; fix that first"
    )
    return sorted(rows[0]["aliases"])


def test_resolve_publishes_the_same_alias_set_as_its_two_siblings() -> None:
    """One field name, one meaning, across the three routes that publish it."""
    rows = _resolved("이탈 고객")
    for concept in ("고객", "이탈", "활성 고객"):
        assert concept in rows, sorted(rows)
        assert sorted(rows[concept]["aliases"]) == _sibling_aliases(concept), (
            concept,
            rows[concept]["aliases"],
        )


def test_a_dataset_term_is_not_published_as_a_concepts_alias() -> None:
    """매출 is not a synonym of 전환, and 전환 is not even defined."""
    rows = _resolved("매출")
    assert "전환" in rows, sorted(rows)
    assert rows["전환"]["defined_in_vocabulary"] is False, rows["전환"]
    assert "매출" not in rows["전환"]["aliases"], (
        "a dataset's business term is published as this concept's alias: "
        f"{rows['전환']['aliases']}"
    )


def test_the_tokens_that_matched_are_still_published_under_their_own_name() -> None:
    """The information is kept; only the claim it made is corrected."""
    rows = _resolved("이탈 고객")
    assert "matched_terms" in rows["고객"], sorted(rows["고객"])
    matched = rows["고객"]["matched_terms"]
    assert "고객" in matched, matched
    # ``이탈`` matched because the first mapped dataset declares it as a term; it
    # is a match, not a synonym of 고객.
    assert "이탈" in matched, matched
    assert "이탈" not in rows["고객"]["aliases"], rows["고객"]["aliases"]


def test_matched_terms_names_only_what_the_text_contains() -> None:
    """The new field must not become the old field under a new name.

    The exact-phrase row comes from the other branch, where the alias set is
    already the concept's own; the only way that branch can lie is by reporting
    names the text never held. 이탈 고객 declares 탈퇴 고객 and 휴면 고객 as
    aliases, and neither appears in the query.
    """
    rows = _resolved("이탈 고객")
    row = rows["이탈 고객"]
    assert row["matched_terms"] == ["이탈 고객"], row["matched_terms"]
    assert "탈퇴 고객" in row["aliases"], row["aliases"]


def test_a_concept_the_glossary_does_not_define_has_no_invented_aliases() -> None:
    """An undefined concept's alias set is empty, not borrowed."""
    rows = _resolved("캠페인 전환")
    for term, row in rows.items():
        if row["defined_in_vocabulary"]:
            continue
        assert row["aliases"] == [] or row["aliases"] == [term], (term, row["aliases"])


def test_the_score_is_unchanged_by_the_repair() -> None:
    """The matched dataset terms still contribute to the score.

    The contamination and the scoring shared one loop, so moving the field could
    quietly change ranking. ``requirements-coverage.md`` records the ranking
    artifact (a sibling dataset's terms lift a parent concept to 1.0) as a known,
    separate gap - this repair must not silently alter it, in either direction.
    """
    rows = _resolved("이탈 고객")
    assert rows["고객"]["score"] == 1.0, rows["고객"]
    assert rows["이탈 고객"]["score"] == 0.55, rows["이탈 고객"]
    # Unconditional on purpose: written as ``== 0.5 if "전환" in rows else True``
    # the clause passes vacuously when the row disappears, which is exactly what
    # dropping the contribution does.
    assert "전환" in rows, sorted(rows)
    assert rows["전환"]["score"] == 0.5, rows["전환"]


def test_the_resolution_record_carries_both_fields() -> None:
    """The library seam, not only the route."""
    resolutions = ontology.resolve_terms("이탈 고객")
    assert resolutions
    for item in resolutions:
        assert isinstance(item.aliases, list)
        assert isinstance(item.matched_terms, list)
