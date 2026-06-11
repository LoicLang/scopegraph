import datetime
from pathlib import Path

import pytest

from core.graph.models import Decision, System
from core.graph.service import GraphService
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex, graph_fingerprint, node_document


def test_node_document_includes_name_aliases_description() -> None:
    system = System(
        id="sys-x",
        name="Moteur d'autorisation carte",
        aliases=["MONAUT"],
        description="Autorise les transactions carte en temps réel.",
        owner_team="Monétique",
        domains=["monetique"],
    )
    doc = node_document(system)
    assert "Moteur d'autorisation carte" in doc
    assert "MONAUT" in doc
    assert "Autorise les transactions" in doc


def test_node_document_uses_title_and_statement_for_decisions() -> None:
    decision = Decision(
        id="dec-x",
        title="Scoring unique",
        statement="Un seul moteur de scoring est autorisé.",
        rationale="Cohérence des décisions risque.",
        date=datetime.date(2024, 1, 1),
        decided_by="Comité d'architecture",
        domains=["lcb-ft"],
    )
    doc = node_document(decision)
    assert "Scoring unique" in doc
    assert "Un seul moteur de scoring" in doc


def test_graph_fingerprint_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "nodes").mkdir()
    (tmp_path / "nodes" / "a.yaml").write_text("id: a\n")
    (tmp_path / "edges.yaml").write_text("edges: []\n")
    first = graph_fingerprint(tmp_path)
    assert first == graph_fingerprint(tmp_path)  # stable
    (tmp_path / "nodes" / "a.yaml").write_text("id: a\nname: changed\n")
    assert graph_fingerprint(tmp_path) != first


def _mini_service() -> GraphService:
    nodes = [
        System(
            id="sys-gestion-beneficiaires",
            name="Gestion des bénéficiaires",
            description="Référentiel des bénéficiaires de virement.",
            owner_team="Référentiels",
            domains=["referentiel-client"],
        ),
        System(
            id="sys-moteur-credit",
            name="Moteur de crédit",
            description="Octroi et gestion des crédits.",
            owner_team="Crédit",
            domains=["credit"],
        ),
        System(
            id="sys-core-banking",
            name="Core banking",
            description="Tenue de compte centrale.",
            owner_team="SI",
            domains=["socle-si"],
        ),
    ]
    return GraphService({n.id: n for n in nodes}, [])


def test_query_ranks_matching_document_first() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder(["bénéficiaire"]))
    index.build(service)
    results = index.query("ajout d'un bénéficiaire depuis le portail", n=3)
    assert results[0][0] == "sys-gestion-beneficiaires"
    assert results[0][1] > 0.9
    assert len(results) == 3


def test_query_n_is_bounded_by_corpus_size() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder())
    index.build(service)
    assert len(index.query("n'importe quoi", n=50)) == 3


def test_query_before_build_raises() -> None:
    index = VectorIndex(FakeEmbedder())
    with pytest.raises(RuntimeError, match="before build"):
        index.query("quoi que ce soit", n=3)


def test_empty_graph_builds_and_returns_no_results() -> None:
    index = VectorIndex(FakeEmbedder())
    assert index.build(GraphService({}, [])) is True
    assert index.query("n'importe quoi", n=5) == []


def test_persistent_index_skips_rebuild_when_fingerprint_matches(tmp_path: Path) -> None:
    service = _mini_service()
    embedder = FakeEmbedder(["bénéficiaire"])

    first = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert first.build(service, fingerprint="fp-1") is True

    second = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert second.build(service, fingerprint="fp-1") is False  # reused, not rebuilt
    assert second.query("bénéficiaire", n=1)[0][0] == "sys-gestion-beneficiaires"


def test_persistent_index_rebuilds_when_fingerprint_changes(tmp_path: Path) -> None:
    service = _mini_service()
    embedder = FakeEmbedder(["bénéficiaire"])
    VectorIndex(embedder, persist_dir=tmp_path / "chroma").build(service, fingerprint="fp-1")

    stale = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert stale.build(service, fingerprint="fp-2") is True  # content changed → rebuilt


def test_ephemeral_index_always_rebuilds() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder())
    assert index.build(service, fingerprint="fp-1") is True
    assert index.build(service, fingerprint="fp-1") is False  # same client instance reuses
