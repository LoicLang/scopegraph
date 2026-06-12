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
    expected = anchor_score(plain, "sys-moteur") + config.DEFAULT_PROFILE.alpha
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
    assert moteur.score == pytest.approx(config.DEFAULT_PROFILE.decay)  # anchor score 1.0 · DECAY^1
    assert moteur.anchor_id == "sys-canal"
    assert [edge.type for edge in moteur.path] == [EdgeType.DEPENDS_ON]

    terminal = by_id["sys-terminal"]
    assert terminal.score == pytest.approx(config.DEFAULT_PROFILE.decay**2)
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


def test_profile_top_n_caps_the_candidate_pool():
    from dataclasses import replace

    from core.retrieval.config import MINILM

    service, index = make_index(["canal", "central"])
    starved = replace(MINILM, top_n_fixed=1, tau_anchor=0.0)
    result = retrieve("canal et traitement central", service, index, profile=starved)
    assert len(result.anchors) == 1  # only one candidate ever reached the scorer


def test_coverage_policy_sizes_the_pool_from_the_graph():
    from dataclasses import replace

    from core.retrieval.config import MINILM

    service, index = make_index(["canal", "central"])
    covering = replace(MINILM, top_n_policy="coverage", top_n_floor=1, top_n_fraction=0.3,
                       tau_anchor=0.0)
    result = retrieve("canal et traitement central", service, index, profile=covering)
    assert len(result.anchors) == 2  # ceil(0.3 * 4 nodes) = 2 candidates reach the scorer


def test_expansion_only_threshold_comes_from_the_profile():
    """Y sits at intermediate sim ≈ 0.707 (shares one of the query's two fragments):
    visible under MiniLM's tau_noise=0.25, invisible under a strict profile."""
    from dataclasses import replace

    from core.retrieval.config import MINILM

    # Build a dedicated two-node graph so the math is isolated from make_service().
    # X contains both fragments → cosine 1.0 with the query → anchor under tau_anchor=0.9.
    # Y contains only frag-a → cosine 1/√2 ≈ 0.707 with the query → expanded, not anchor.
    FRAG_A = "zeta-one"
    FRAG_B = "zeta-two"
    QUERY = f"testing {FRAG_A} and {FRAG_B} integration"
    X_ID = "sys-alpha"
    Y_ID = "sys-beta"

    nodes = [
        System(
            id=X_ID,
            name="Alpha system",
            description=f"Handles {FRAG_A} and {FRAG_B}.",
            owner_team="T",
            domains=["test-domain"],
        ),
        System(
            id=Y_ID,
            name="Beta system",
            description=f"Handles {FRAG_A} only.",
            owner_team="T",
            domains=["test-domain"],
        ),
    ]
    edges = [
        Edge(source_id=Y_ID, target_id=X_ID, type=EdgeType.DEPENDS_ON),
    ]
    svc = GraphService({n.id: n for n in nodes}, edges)
    idx = VectorIndex(FakeEmbedder([FRAG_A, FRAG_B]))
    idx.build(svc)

    # tau_anchor=0.9: X (sim=1.0) is an anchor; Y (sim≈0.707) is NOT → Y appears in expanded.
    # top_n_fixed=20 (default) so Y reaches the scorer and gets a real semantic_sim (not None).
    lax = replace(MINILM, tau_anchor=0.9)
    strict = replace(MINILM, tau_anchor=0.9, tau_noise=2.0)

    lax_result = retrieve(QUERY, svc, idx, profile=lax)
    strict_result = retrieve(QUERY, svc, idx, profile=strict)

    lax_y = next(s for s in lax_result.expanded if s.node_id == Y_ID)
    strict_y = next(s for s in strict_result.expanded if s.node_id == Y_ID)

    assert lax_y.semantic_sim is not None and lax.tau_noise < lax_y.semantic_sim < 1.0  # setup is honest
    assert not lax_y.expansion_only  # 0.707 ≥ tau_noise 0.25 → textually visible
    assert strict_y.expansion_only  # 0.707 < tau_noise 2.0 → invisible under the strict profile
