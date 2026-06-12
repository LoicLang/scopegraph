"""Hybrid scorer: semantic + domain boost + bounded graph expansion with provenance."""

from collections.abc import Sequence
from dataclasses import dataclass

from core.graph.models import Edge
from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.config import RetrievalProfile
from core.retrieval.index import VectorIndex

# Tiebreak priority for equal-scoring anchors: primary architectural subjects rank first.
# Systems and business_objects are the "things" a brief asks about; features, projects,
# decisions, constraints, and risks are derivative or governance artifacts.
_TYPE_PRIORITY: dict[str, int] = {
    "system": 0,
    "business_object": 1,
    "feature": 2,
    "project": 3,
    "decision": 4,
    "constraint": 5,
    "risk": 6,
}


@dataclass(frozen=True)
class ScoredNode:
    node_id: str
    score: float
    domains: tuple[str, ...] = ()
    semantic_sim: float | None = None
    anchor_id: str | None = None
    path: tuple[Edge, ...] = ()
    expansion_only: bool = False  # reached structurally, near-invisible textually (T3)


@dataclass
class RetrievalResult:
    anchors: list[ScoredNode]  # sorted by score, best first
    expanded: list[ScoredNode]  # sorted by score, best first
    domain_scores: dict[str, float]
    derived_domains: list[str]

    def node_ids(self) -> list[str]:
        return [scored.node_id for scored in [*self.anchors, *self.expanded]]


def retrieve(
    text: str,
    service: GraphService,
    index: VectorIndex,
    *,
    domains: Sequence[str] = (),
    excluded_domains: Sequence[str] = (),
    profile: RetrievalProfile = config.DEFAULT_PROFILE,
) -> RetrievalResult:
    """Hybrid retrieval: semantic anchors + domain boost + bounded expansion.

    `domains` are the brief's user-confirmed domains (boost + derivation override);
    `excluded_domains` only filter the expansion layer — anchors are never dropped
    (the user literally named them).
    """
    sims = dict(index.query(text, profile.top_n(len(service.all_nodes()))))
    wanted = set(domains)
    boosted = {
        node_id: sim + profile.alpha * len(set(service.get_node(node_id).domains) & wanted)
        for node_id, sim in sims.items()
    }
    anchor_ids = [
        node_id
        for node_id, score in sorted(
            boosted.items(),
            key=lambda kv: (
                -kv[1],
                _TYPE_PRIORITY.get(service.get_node(kv[0]).type, 99),
                kv[0],
            ),
        )
        if score >= profile.tau_anchor
    ][: config.TOP_K]
    anchors = [
        ScoredNode(
            node_id=node_id,
            score=boosted[node_id],
            domains=tuple(service.get_node(node_id).domains),
            semantic_sim=sims[node_id],
        )
        for node_id in anchor_ids
    ]

    domain_scores: dict[str, float] = {}
    for anchor in anchors:
        for domain in anchor.domains:
            domain_scores[domain] = domain_scores.get(domain, 0.0) + anchor.score
    top = max(domain_scores.values(), default=0.0)
    derived = sorted(
        (d for d, s in domain_scores.items() if s >= profile.domain_fraction * top),
        key=lambda d: (-domain_scores[d], d),
    )

    expanded = _expand(anchors, service, sims, set(excluded_domains), set(domains), profile)
    return RetrievalResult(anchors, expanded, domain_scores, derived)


def _expand(
    anchors: list[ScoredNode],
    service: GraphService,
    sims: dict[str, float],
    excluded: set[str],
    confirmed: set[str],
    profile: RetrievalProfile,
) -> list[ScoredNode]:
    anchor_ids = {anchor.node_id for anchor in anchors}
    best: dict[str, ScoredNode] = {}
    for anchor in anchors:  # strongest first → ties resolve to the strongest anchor
        for node_id, path in service.k_hop(anchor.node_id, config.MAX_HOPS).items():
            if node_id in anchor_ids:
                continue
            node = service.get_node(node_id)
            node_domains = set(node.domains)
            # exclusion drops a node only if no user-confirmed domain rescues it
            if node_domains & excluded and not (node_domains & confirmed):
                continue
            score = anchor.score * profile.decay ** len(path)
            if score < profile.tau_keep:
                continue
            if node_id not in best or score > best[node_id].score:
                best[node_id] = ScoredNode(
                    node_id=node_id,
                    score=score,
                    domains=tuple(node.domains),
                    semantic_sim=sims.get(node_id),
                    anchor_id=anchor.node_id,
                    path=tuple(path),
                    expansion_only=(sims.get(node_id) or 0.0) < profile.tau_noise,
                )
    return sorted(best.values(), key=lambda scored: (-scored.score, scored.node_id))
