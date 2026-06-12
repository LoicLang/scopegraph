"""The real embedder. Only module allowed to import sentence_transformers — lazily."""

from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
from core.retrieval.embedder import prefixed


class SentenceTransformersEmbedder:
    def __init__(self, profile: RetrievalProfile = DEFAULT_PROFILE) -> None:
        self.model_name = profile.model_name  # embedder_id() folds this into fingerprints
        self.prefixes = (profile.query_prefix, profile.passage_prefix)  # part of embedder_id
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # clear startup error (W2 spec: error handling)
            raise RuntimeError(
                "sentence-transformers is not installed — run: pip install -e '.[embeddings]'"
            ) from exc
        extra: dict = {}
        if profile.model_kwargs:
            extra["model_kwargs"] = dict(profile.model_kwargs)
        if profile.tokenizer_kwargs:
            # sentence-transformers 5.x renamed tokenizer_kwargs → processor_kwargs;
            # the profile keeps the semantic name (these ARE tokenizer settings).
            extra["processor_kwargs"] = dict(profile.tokenizer_kwargs)
        self._model = SentenceTransformer(profile.model_name, **extra)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        rows = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        query_prefix, _ = self.prefixes
        return self._encode(prefixed(query_prefix, texts))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        _, passage_prefix = self.prefixes
        return self._encode(prefixed(passage_prefix, texts))
