import pytest

from core.graph.models import Constraint, Edge, EdgeType, Feature, System
from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import retrieve


def make_service() -> GraphService:
    nodes = [
        System(
            id="sys-canal",
            name="Canal mobile",
            description="Canal client mobile.",
            owner_team="T",
            domains=["banque-en-ligne"],
        ),
        System(
            id="sys-moteur",
            name="Moteur central",
            description="Traitement central des opérations.",
            owner_team="T",
            domains=["monetique"],
        ),
        System(
            id="sys-terminal",
            name="Terminal magasin",
            description="Acceptation en magasin.",
            owner_team="T",
            domains=["tpe-acceptation"],
        ),
        Constraint(
            id="con-regle",
            title="Règle PCI",
            statement="Cloisonnement réseau requis.",
            source="PCI DSS",
            severity="high",
            domains=["monetique"],
        ),
    ]
    edges = [
        Edge(source_id="sys-canal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-terminal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="con-regle", target_id="sys-moteur", type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def make_index(fragments: list[str]) -> tuple[GraphService, VectorIndex]:
    service = make_service()
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return service, index


def anchor_score(result, node_id: str) -> float:
    return next(s.score for s in result.anchors if s.node_id == node_id)


def test_anchors_require_threshold_and_carry_similarity() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    assert [s.node_id for s in result.anchors] == ["sys-canal"]
    assert result.anchors[0].semantic_sim == pytest.approx(1.0)
    assert result.anchors[0].domains == ("banque-en-ligne",)


def test_no_anchor_when_nothing_matches() -> None:
    service, index = make_index(["canal"])
    result = retrieve("sujet totalement étranger", service, index)
    assert result.anchors == []
    assert result.derived_domains == []


def test_domain_boost_adds_alpha_per_shared_domain() -> None:
    service, index = make_index(["canal", "central"])
    plain = retrieve("le canal et le traitement central", service, index)
    boosted = retrieve(
        "le canal et le traitement central", service, index, domains=["monetique"]
    )
    expected = anchor_score(plain, "sys-moteur") + config.ALPHA
    assert anchor_score(boosted, "sys-moteur") == pytest.approx(expected)
    assert boosted.anchors[0].node_id == "sys-moteur"  # boost reorders the tie


def test_domain_scores_and_derivation() -> None:
    service, index = make_index(["canal", "central"])
    result = retrieve("le canal et le traitement central", service, index)
    assert set(result.domain_scores) == {"banque-en-ligne", "monetique"}
    # equal anchor scores → both domains derived (≥ DOMAIN_FRACTION · top)
    assert set(result.derived_domains) == {"banque-en-ligne", "monetique"}


def test_expansion_carries_provenance_and_decay() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    by_id = {s.node_id: s for s in result.expanded}

    moteur = by_id["sys-moteur"]
    assert moteur.score == pytest.approx(config.DECAY)  # anchor score 1.0 · DECAY^1
    assert moteur.anchor_id == "sys-canal"
    assert [edge.type for edge in moteur.path] == [EdgeType.DEPENDS_ON]

    terminal = by_id["sys-terminal"]
    assert terminal.score == pytest.approx(config.DECAY**2)
    assert len(terminal.path) == 2
    assert terminal.expansion_only  # zero textual similarity, pure structure

    assert "con-regle" in by_id  # constraints ride the same expansion


def test_expansion_skips_anchors_and_sorts_by_score() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    expanded_ids = [s.node_id for s in result.expanded]
    assert "sys-canal" not in expanded_ids
    scores = [s.score for s in result.expanded]
    assert scores == sorted(scores, reverse=True)


def test_excluded_domains_drop_expanded_nodes() -> None:
    service, index = make_index(["canal"])
    result = retrieve(
        "améliorer notre canal mobile", service, index, excluded_domains=["tpe-acceptation"]
    )
    expanded_ids = {s.node_id for s in result.expanded}
    assert "sys-terminal" not in expanded_ids
    assert "sys-moteur" in expanded_ids  # other domains untouched


def test_confirmed_domain_rescues_node_from_exclusion() -> None:
    service, index = make_index(["canal"])
    result = retrieve(
        "améliorer notre canal mobile", service, index,
        domains=["monetique"], excluded_domains=["monetique"],
    )
    # degenerate overlap: confirmation wins over exclusion
    assert "sys-moteur" in {s.node_id for s in result.expanded}


def test_exclusion_drops_unrescued_nodes_only() -> None:
    service, index = make_index(["canal"])
    result = retrieve(
        "améliorer notre canal mobile", service, index,
        domains=[], excluded_domains=["tpe-acceptation"],
    )
    ids = {s.node_id for s in result.expanded}
    assert "sys-terminal" not in ids
    assert "sys-moteur" in ids


def test_anchor_tie_break_prefers_system_over_feature() -> None:
    """Exact score ties resolve by node type: the System (the subject) outranks
    Features that match the same text — executable spec of _TYPE_PRIORITY."""
    nodes = [
        Feature(
            id="feat-espace-client",
            name="Espace client",
            description="Fonctionnalité de l'espace client.",
            domains=["banque-en-ligne"],
        ),
        System(
            id="sys-espace-client",
            name="Espace client",
            description="Portail espace client.",
            owner_team="T",
            domains=["banque-en-ligne"],
        ),
    ]
    service = GraphService({n.id: n for n in nodes}, [])
    index = VectorIndex(FakeEmbedder(["espace client"]))
    index.build(service)
    result = retrieve("refondre l'espace client", service, index)
    assert [s.node_id for s in result.anchors] == ["sys-espace-client", "feat-espace-client"]
