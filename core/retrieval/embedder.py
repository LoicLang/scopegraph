"""Embedder Protocol and the test-rigged FakeEmbedder (hermetic tests, no model)."""

import hashlib
import math
from typing import Protocol

DIM = 32
_HASH_OFFSET = DIM // 2  # hash vectors live in the upper half, fragments in the lower


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic embedder rigged by fragments.

    Texts sharing a registered fragment (case-insensitive substring) get overlapping
    one-hot components → high cosine similarity. Texts matching no fragment get a
    stable signed hash vector on disjoint axes → ~zero similarity with everything.
    """

    def __init__(self, fragments: list[str] | None = None) -> None:
        self._fragments = {f.lower(): i for i, f in enumerate(fragments or [])}
        if len(self._fragments) > _HASH_OFFSET:
            raise ValueError(f"FakeEmbedder supports at most {_HASH_OFFSET} fragments")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        lowered = text.lower()
        vector = [0.0] * DIM
        matched = False
        for fragment, axis in self._fragments.items():
            if fragment in lowered:
                vector[axis] = 1.0
                matched = True
        if not matched:
            digest = hashlib.sha256(lowered.encode()).digest()
            for i in range(_HASH_OFFSET, DIM):
                vector[i] = (digest[i - _HASH_OFFSET] - 127.5) / 127.5
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector]
