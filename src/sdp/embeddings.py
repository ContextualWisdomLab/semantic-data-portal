"""Deterministic, dependency-free text embeddings.

The portal must rank concepts/datasets by meaning ("찾아주는") using pgvector
KNN. A production deployment would swap in a hosted embedding model, but the
service must also run standalone and in CI with no network and no secrets.

This module implements a deterministic *hashing embedding* (a.k.a. the hashing
trick / feature hashing) over character n-grams and word tokens. Because the
same function embeds both the stored text and the query, cosine similarity
still reflects lexical/semantic overlap -- enough to make KNN ranking
meaningful and testable. It is multilingual-friendly: Korean text is embedded
via character n-grams so partial-token overlap contributes signal.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import List

DEFAULT_DIMENSION = 128

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> List[str]:
    normalized = text.lower().strip()
    if not normalized:
        return []
    words = _WORD_RE.findall(normalized)
    # Character 3-grams over the whitespace-collapsed string capture partial
    # overlap for languages without whitespace tokenisation (e.g. Korean).
    compact = re.sub(r"\s+", " ", normalized)
    trigrams = [compact[i : i + 3] for i in range(max(0, len(compact) - 2))]
    return words + trigrams


def embed_text(text: str, dimension: int = DEFAULT_DIMENSION) -> List[float]:
    """Return an L2-normalised embedding vector for ``text``."""

    vec = [0.0] * dimension
    for token in _tokens(text):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dimension
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(component * component for component in vec))
    if norm == 0.0:
        return vec
    return [component / norm for component in vec]


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """Cosine similarity for two equal-length vectors (0.0 on degenerate input)."""

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
