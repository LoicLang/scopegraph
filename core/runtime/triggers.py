"""Deterministic ambiguity triggers (W2 spec §4). The runtime decides — never the LLM."""

from dataclasses import dataclass

from core.retrieval import config
from core.retrieval.retriever import RetrievalResult
from core.runtime.brief import ProjectBrief


@dataclass(frozen=True)
class WeakBriefTrigger:
    @property
    def key(self) -> str:
        return "weak"


@dataclass(frozen=True)
class DomainTieTrigger:
    domain_a: str
    domain_b: str

    @property
    def key(self) -> str:
        return "tie:" + ":".join(sorted((self.domain_a, self.domain_b)))


@dataclass(frozen=True)
class PivotTrigger:
    domain: str
    node_id: str

    @property
    def key(self) -> str:
        return f"pivot:{self.domain}"  # one question per domain, not per node


Trigger = WeakBriefTrigger | DomainTieTrigger | PivotTrigger


def detect_trigger(
    result: RetrievalResult, brief: ProjectBrief, asked: set[str]
) -> Trigger | None:
    """First firing trigger in T1 → T2 → T3 order, skipping already-asked keys."""
    best = result.anchors[0].score if result.anchors else 0.0
    if best < config.TAU_WEAK:
        trigger = WeakBriefTrigger()
        if trigger.key not in asked:
            return trigger

    ranked = sorted(result.domain_scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) >= 2:
        (domain_a, score_a), (domain_b, score_b) = ranked[0], ranked[1]
        if score_a - score_b < config.DELTA * score_a:
            trigger = DomainTieTrigger(domain_a=domain_a, domain_b=domain_b)
            if trigger.key not in asked:
                return trigger

    known = set(brief.domains) | set(result.derived_domains) | set(brief.excluded_domains)
    # Pivot choice is deliberately naive: first unknown domain by expansion score. It often
    # picks an incidental neighbor over the decisive one (known-limits L3) — W3's LLM will
    # judge relevance; the runtime keeps deciding WHETHER to ask.
    for scored in result.expanded:  # already sorted best-first
        if not scored.expansion_only:
            continue
        # node-level check: if ANY domain is known, the node is already justified — skip it
        if set(scored.domains) & known:
            continue
        for domain in scored.domains:
            trigger = PivotTrigger(domain=domain, node_id=scored.node_id)
            if trigger.key not in asked:
                return trigger
    return None
