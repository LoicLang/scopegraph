import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
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
