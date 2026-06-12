"""The per-turn candidate pool: graph ambiguity first, then EDB gaps (W3 spec §4.4).

Pure assembly — the runtime decides WHAT may be asked; the LLM (or the template
fallback) only picks within this pool and phrases the question.
"""

from dataclasses import dataclass

from core.dossier.template import EdbState
from core.retrieval.retriever import RetrievalResult
from core.runtime.brief import ProjectBrief
from core.runtime.triggers import (
    DomainTieTrigger,
    Trigger,
    WeakBriefTrigger,
    collect_pivot_candidates,
    detect_trigger,
)


@dataclass(frozen=True)
class Candidate:
    kind: str  # "weak" | "tie" | "pivot" | "edb_gap"
    key: str  # asked-log key
    domain: str = ""  # pivot/tie context
    node_id: str = ""  # pivot context
    section_id: str = ""  # edb_gap context
    trigger: Trigger | None = None  # the W2 trigger object for fallback rendering


def build_pool(
    result: RetrievalResult, brief: ProjectBrief, asked: set[str], edb: EdbState
) -> list[Candidate]:
    pool: list[Candidate] = []
    primary = detect_trigger(result, brief, asked)
    if isinstance(primary, WeakBriefTrigger):
        pool.append(Candidate(kind="weak", key=primary.key, trigger=primary))
    elif isinstance(primary, DomainTieTrigger):
        pool.append(Candidate(kind="tie", key=primary.key,
                              domain=f"{primary.domain_a}|{primary.domain_b}",
                              trigger=primary))
    # A primary PivotTrigger is already covered by collect_pivot_candidates below.
    for pivot in collect_pivot_candidates(result, brief, asked):
        pool.append(Candidate(kind="pivot", key=pivot.key, domain=pivot.domain,
                              node_id=pivot.node_id, trigger=pivot))
    for section_id in edb.missing_sections():
        key = f"gap:{section_id}"
        if key not in asked:
            pool.append(Candidate(kind="edb_gap", key=key, section_id=section_id))
    return pool
