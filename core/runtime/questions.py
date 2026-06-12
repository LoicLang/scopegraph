"""French question templates — assembled from graph content, never generated (W2 spec §1).

W3 will add LLM rephrasing on top; these templates remain the permanent fallback.
"""

from core.dossier.template import section_spec
from core.graph.service import GraphService
from core.runtime.triggers import DomainTieTrigger, PivotTrigger, Trigger, WeakBriefTrigger

WEAK_QUESTION = (
    "Votre description est courte — pouvez-vous préciser le canal concerné "
    "et l'objet métier manipulé ?"
)


def render_question(trigger: Trigger, service: GraphService) -> str:
    match trigger:
        case WeakBriefTrigger():
            return WEAK_QUESTION
        case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
            return f"Le projet relève-t-il plutôt de « {domain_a} » ou de « {domain_b} » ?"
        case PivotTrigger(domain=domain, node_id=node_id):
            node = service.get_node(node_id)
            label = getattr(node, "name", "") or getattr(node, "title", "")
            return f"Le périmètre inclut-il « {domain} » ? ({label} serait alors concerné)"
    raise TypeError(f"unknown trigger type: {trigger!r}")  # pragma: no cover


def gap_question(section_id: str) -> str:
    """Deterministic fallback question for an EDB gap (the section's hint)."""
    return section_spec(section_id).prompt_hint_fr
