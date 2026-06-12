"""The real embedder. Only module allowed to import sentence_transformers — lazily."""

from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
from core.retrieval.embedder import prefixed


class SentenceTransformersEmbedder:
    def __init__(self, profile: RetrievalProfile = DEFAULT_PROFILE) -> None:
        self.model_name = profile.model_name  # embedder_id() folds this into fingerprints
        self._query_prefix = profile.query_prefix
        self._passage_prefix = profile.passage_prefix
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # clear startup error (W2 spec: error handling)
            raise RuntimeError(
                "sentence-transformers is not installed — run: pip install -e '.[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(profile.model_name)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        rows = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._encode(prefixed(self._query_prefix, texts))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode(prefixed(self._passage_prefix, texts))
