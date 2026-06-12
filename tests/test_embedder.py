import math
import sys

import pytest

from core.retrieval.embedder import DIM, FakeEmbedder, prefixed


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_vectors_are_unit_norm() -> None:
    emb = FakeEmbedder(["app mobile"])
    for vector in emb.embed_queries(["projet dans l'app mobile", "texte sans fragment"]):
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)
        assert len(vector) == DIM


def test_shared_fragment_gives_high_similarity() -> None:
    emb = FakeEmbedder(["app mobile"])
    [a, b, c] = emb.embed_queries(
        ["projet dans l'App Mobile", "Application — app mobile bancaire", "moteur de crédit"]
    )
    assert cosine(a, b) == pytest.approx(1.0)
    assert cosine(a, c) == pytest.approx(0.0)  # fragment axes and hash axes are disjoint


def test_two_fragments_give_partial_overlap() -> None:
    emb = FakeEmbedder(["app mobile", "crédit"])
    [both, one] = emb.embed_queries(["app mobile et crédit", "le crédit conso"])
    assert cosine(both, one) == pytest.approx(1 / math.sqrt(2))


def test_unknown_texts_are_deterministic_and_distinct() -> None:
    emb = FakeEmbedder()
    [v1] = emb.embed_queries(["texte inconnu"])
    [v2] = emb.embed_queries(["texte inconnu"])
    [v3] = emb.embed_queries(["autre texte"])
    assert v1 == v2
    assert v1 != v3


def test_too_many_fragments_rejected() -> None:
    with pytest.raises(ValueError, match="at most"):
        FakeEmbedder([f"frag-{i}" for i in range(DIM)])


def test_importing_st_module_does_not_import_sentence_transformers() -> None:
    import core.retrieval.st_embedder  # noqa: F401

    assert "sentence_transformers" not in sys.modules


def test_missing_package_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.retrieval.st_embedder import SentenceTransformersEmbedder

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        SentenceTransformersEmbedder()


def test_prefixed_applies_prefix():
    assert prefixed("query: ", ["plafonds", "fraude"]) == ["query: plafonds", "query: fraude"]


def test_prefixed_empty_prefix_copies_unchanged():
    texts = ["plafonds"]
    result = prefixed("", texts)
    assert result == texts
    assert result is not texts  # never alias: callers must not reach the input via the result


def test_fake_embedder_queries_and_passages_are_identical():
    emb = FakeEmbedder(["app mobile"])
    [q] = emb.embed_queries(["projet app mobile"])
    [p] = emb.embed_passages(["projet app mobile"])
    assert q == p


def test_st_embedder_routes_prefixes_per_method(monkeypatch):
    import sys
    import types

    from core.retrieval.config import E5_BASE

    captured: list[list[str]] = []

    class _RecordingModel:
        def __init__(self, model_name, **kwargs):
            pass

        def encode(self, texts, normalize_embeddings):
            captured.append(list(texts))
            return [[1.0, 0.0] for _ in texts]

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _RecordingModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from core.retrieval.st_embedder import SentenceTransformersEmbedder

    embedder = SentenceTransformersEmbedder(E5_BASE)
    embedder.embed_queries(["plafonds"])
    embedder.embed_passages(["plafonds"])
    assert captured == [["query: plafonds"], ["passage: plafonds"]]


def test_st_embedder_passes_profile_st_kwargs(monkeypatch):
    import sys
    import types
    from dataclasses import replace

    from core.retrieval.config import MINILM

    captured_kwargs: dict = {}

    class _RecordingModel:
        def __init__(self, model_name, **kwargs):
            captured_kwargs.update(kwargs)

        def encode(self, texts, normalize_embeddings):
            return [[1.0, 0.0] for _ in texts]

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _RecordingModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from core.retrieval.st_embedder import SentenceTransformersEmbedder

    profile = replace(
        MINILM,
        model_kwargs={"attn_implementation": "eager"},
        tokenizer_kwargs={"padding_side": "left"},
    )
    SentenceTransformersEmbedder(profile)
    assert captured_kwargs == {
        "model_kwargs": {"attn_implementation": "eager"},
        "processor_kwargs": {"padding_side": "left"},  # ST 5.x name for tokenizer kwargs
    }


def test_st_embedder_omits_empty_st_kwargs(monkeypatch):
    import sys
    import types

    from core.retrieval.config import MINILM

    captured_kwargs: dict = {}

    class _RecordingModel:
        def __init__(self, model_name, **kwargs):
            captured_kwargs.update(kwargs)

        def encode(self, texts, normalize_embeddings):
            return [[1.0, 0.0] for _ in texts]

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _RecordingModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from core.retrieval.st_embedder import SentenceTransformersEmbedder

    SentenceTransformersEmbedder(MINILM)
    assert captured_kwargs == {}  # legacy models keep the exact historical constructor call
