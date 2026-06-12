from core.graph.models import Edge, EdgeType
from core.retrieval.retriever import RetrievalResult, ScoredNode
from core.runtime.brief import ProjectBrief
from core.runtime.triggers import (
    DomainTieTrigger,
    PivotTrigger,
    WeakBriefTrigger,
    detect_trigger,
)

EDGE = Edge(source_id="sys-a", target_id="sys-b", type=EdgeType.DEPENDS_ON)


def make_result(anchors=(), expanded=(), domain_scores=None, derived=()) -> RetrievalResult:
    return RetrievalResult(
        anchors=list(anchors),
        expanded=list(expanded),
        domain_scores=dict(domain_scores or {}),
        derived_domains=list(derived),
    )


def strong_anchor() -> ScoredNode:
    return ScoredNode("sys-a", 0.9, domains=("credit",), semantic_sim=0.9)


def test_weak_brief_fires_when_best_anchor_low() -> None:
    result = make_result(anchors=[ScoredNode("sys-a", 0.3, semantic_sim=0.3)])
    trigger = detect_trigger(result, ProjectBrief(description="x"), asked=set())
    assert isinstance(trigger, WeakBriefTrigger)


def test_weak_brief_fires_when_no_anchor_and_respects_asked_log() -> None:
    result = make_result()
    assert isinstance(detect_trigger(result, ProjectBrief(description="x"), set()), WeakBriefTrigger)
    assert detect_trigger(result, ProjectBrief(description="x"), asked={"weak"}) is None


def test_domain_tie_fires_within_relative_delta() -> None:
    result = make_result(
        anchors=[strong_anchor()],
        domain_scores={"credit": 1.0, "monetique": 0.9},
        derived=["credit", "monetique"],
    )
    trigger = detect_trigger(result, ProjectBrief(description="x"), set())
    assert trigger == DomainTieTrigger(domain_a="credit", domain_b="monetique")
    assert detect_trigger(result, ProjectBrief(description="x"), {trigger.key}) is None


def test_no_tie_when_gap_is_wide() -> None:
    result = make_result(
        anchors=[strong_anchor()], domain_scores={"credit": 1.0, "monetique": 0.5},
        derived=["credit"],
    )
    assert detect_trigger(result, ProjectBrief(description="x"), set()) is None


def pivot_node() -> ScoredNode:
    return ScoredNode(
        "sys-terminal", 0.49, domains=("tpe-acceptation",), semantic_sim=0.0,
        anchor_id="sys-a", path=(EDGE, EDGE), expansion_only=True,
    )


def test_pivot_fires_for_expansion_only_foreign_domain() -> None:
    result = make_result(
        anchors=[strong_anchor()], expanded=[pivot_node()],
        domain_scores={"credit": 1.0}, derived=["credit"],
    )
    trigger = detect_trigger(result, ProjectBrief(description="x"), set())
    assert trigger == PivotTrigger(domain="tpe-acceptation", node_id="sys-terminal")


def test_pivot_skips_known_excluded_and_asked_domains() -> None:
    result = make_result(
        anchors=[strong_anchor()], expanded=[pivot_node()],
        domain_scores={"credit": 1.0}, derived=["credit"],
    )
    known = ProjectBrief(description="x", domains=["tpe-acceptation"])
    assert detect_trigger(result, known, set()) is None
    excluded = ProjectBrief(description="x", excluded_domains=["tpe-acceptation"])
    assert detect_trigger(result, excluded, set()) is None
    assert detect_trigger(result, ProjectBrief(description="x"), {"pivot:tpe-acceptation"}) is None


def test_precedence_weak_then_tie_then_pivot() -> None:
    result = make_result(
        anchors=[ScoredNode("sys-a", 0.3, domains=("credit",), semantic_sim=0.3)],
        expanded=[pivot_node()],
        domain_scores={"credit": 0.3, "monetique": 0.28},
        derived=["credit", "monetique"],
    )
    brief = ProjectBrief(description="x")
    assert isinstance(detect_trigger(result, brief, set()), WeakBriefTrigger)
    assert isinstance(detect_trigger(result, brief, {"weak"}), DomainTieTrigger)
    tie_key = DomainTieTrigger(domain_a="credit", domain_b="monetique").key
    assert isinstance(detect_trigger(result, brief, {"weak", tie_key}), PivotTrigger)


def test_pivot_skips_nodes_already_justified_by_a_known_domain() -> None:
    bridge = ScoredNode(
        "sys-pont", 0.49, domains=("credit", "tpe-acceptation"), semantic_sim=0.0,
        anchor_id="sys-a", path=(EDGE,), expansion_only=True,
    )
    result = make_result(
        anchors=[strong_anchor()], expanded=[bridge],
        domain_scores={"credit": 1.0}, derived=["credit"],
    )
    # the node carries credit (known) → no pivot question about tpe-acceptation
    assert detect_trigger(result, ProjectBrief(description="x"), set()) is None
