"""Deterministic embedding + cosine-similarity edge cases.

The portal ranks concepts/datasets by meaning via a dependency-free hashing
embedding; these pin the degenerate paths (empty text -> zero vector, and cosine
similarity on empty/mismatched/zero vectors -> 0.0) so KNN ranking stays safe on
edge input.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import embeddings as emb  # noqa: E402


def test_embed_empty_text_is_zero_vector() -> None:
    vec = emb.embed_text("")
    assert vec == [0.0] * emb.DEFAULT_DIMENSION  # no tokens -> zero norm -> raw vec


def test_embed_nonempty_is_l2_normalised() -> None:
    vec = emb.embed_text("고객 이탈 분석")
    norm = sum(c * c for c in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_cosine_similarity_reflects_overlap() -> None:
    a = emb.embed_text("customer churn analysis")
    same = emb.cosine_similarity(a, emb.embed_text("customer churn analysis"))
    diff = emb.cosine_similarity(a, emb.embed_text("weather forecast rainfall"))
    assert same > diff


def test_cosine_similarity_degenerate_inputs_are_zero() -> None:
    assert emb.cosine_similarity([], []) == 0.0  # empty
    assert emb.cosine_similarity([1.0, 2.0], [1.0]) == 0.0  # length mismatch
    assert emb.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero vector
