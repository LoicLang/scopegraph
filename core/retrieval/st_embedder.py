"""The real embedder. Only module allowed to import sentence_transformers — lazily."""

from core.retrieval.config import EMBED_MODEL


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str = EMBED_MODEL) -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # clear startup error (W2 spec: error handling)
            raise RuntimeError(
                "sentence-transformers is not installed — run: pip install -e '.[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        rows = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]
