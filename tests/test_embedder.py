import math
import sys

import pytest

from core.retrieval.embedder import DIM, FakeEmbedder


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_vectors_are_unit_norm() -> None:
    emb = FakeEmbedder(["app mobile"])
    for vector in emb.embed(["projet dans l'app mobile", "texte sans fragment"]):
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)
        assert len(vector) == DIM


def test_shared_fragment_gives_high_similarity() -> None:
    emb = FakeEmbedder(["app mobile"])
    [a, b, c] = emb.embed(
        ["projet dans l'App Mobile", "Application — app mobile bancaire", "moteur de crédit"]
    )
    assert cosine(a, b) == pytest.approx(1.0)
    assert cosine(a, c) == pytest.approx(0.0)  # fragment axes and hash axes are disjoint


def test_two_fragments_give_partial_overlap() -> None:
    emb = FakeEmbedder(["app mobile", "crédit"])
    [both, one] = emb.embed(["app mobile et crédit", "le crédit conso"])
    assert cosine(both, one) == pytest.approx(1 / math.sqrt(2))


def test_unknown_texts_are_deterministic_and_distinct() -> None:
    emb = FakeEmbedder()
    [v1] = emb.embed(["texte inconnu"])
    [v2] = emb.embed(["texte inconnu"])
    [v3] = emb.embed(["autre texte"])
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
