"""Conversational scoping step (opt-in): one LLM call drives the whole interview.

Two phases, one prompt:
- « entrée » — no map yet: decide when the project subject is stated (`ready_to_map`),
  so the FIRST recall fires on a real brief, not on « bonjour ».
- « cadrage » — a FROZEN candidate universe is shown: the LLM proactively prunes the
  obvious, owns the next question, and signals `scope_stable` when the scope settles.

The LLM proposes; the runtime applies actions ONLY through the gates (known domain,
on-map node, reason present) and only ever REMOVES from the frozen universe (monotone
narrowing — no oscillation). provider=None or a JSON-contract miss → None (the caller
falls back to the deterministic interview)."""

import unicodedata
from dataclasses import dataclass, field

from core.graph.service import GraphService
from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import LLMProvider
from core.runtime.brief import ProjectBrief


def _norm_domain(text: str) -> str:
    """Accent-, case- and separator-insensitive key so « Crédit »/« virements
    instantanés » match the canonical slugs « credit »/« virements-instantanes »."""
    folded = unicodedata.normalize("NFKD", text.strip().casefold())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return stripped.replace(" ", "-").replace("_", "-")


@dataclass
class ConverseResult:
    message: str  # the human reply shown to the user
    actions: list[dict] = field(default_factory=list)  # gated scoping actions
    advance: bool = True  # False → help and re-ask, don't progress
    ready_to_map: bool = False  # entry phase: subject stated → fire the first recall
    scope_stable: bool = False  # scope phase: settled → trigger the challenge
    question: str = ""  # scope phase: the next question (the LLM owns it)


def converse_and_scope(
    provider: LLMProvider | None,
    *,
    phase: str,  # "entrée" | "cadrage"
    brief_text: str,
    map_text: str,
    known_domains,
    pending_question: str | None,
    user_message: str,
    asked_questions: tuple[str, ...] = (),
) -> ConverseResult | None:
    """One conversational turn. None → caller uses the deterministic fallback."""
    if provider is None:
        return None
    already = "\n".join(f"- {q}" for q in asked_questions) or "(aucune)"
    user = (
        f"Phase : {phase}\n\n"
        f"Domaines connus : {', '.join(known_domains)}\n\n"
        f"Carte (node_id · libellé · domaines) :\n{map_text or '(pas encore de carte)'}\n\n"
        f"Questions DÉJÀ posées (ne les repose pas à l'identique) :\n{already}\n\n"
        f"Question en attente : {pending_question or '(aucune)'}\n\n"
        f"Message de l'utilisateur : {user_message}\n\n"
        f"Brief jusqu'ici :\n{brief_text}"
    )
    try:
        out = complete_with_retry(
            provider, load_prompt("converse_scope"), user, required_keys=("message",)
        )
    except JsonContractError:
        return None
    return ConverseResult(
        message=str(out.get("message", "")).strip(),
        actions=[a for a in out.get("actions", []) if isinstance(a, dict)],
        advance=bool(out.get("advance", True)),
        ready_to_map=bool(out.get("pret_a_mapper", False)),
        scope_stable=bool(out.get("perimetre_stable", False)),
        question=str(out.get("question", "")).strip(),
    )


def apply_scope_actions(
    actions: list[dict],
    *,
    brief: ProjectBrief,
    universe: set[str],
    service: GraphService,
    rejected_nodes: dict[str, str],
) -> list[dict]:
    """Apply gated actions in place; return the ungrounded ones (visible rejection).

    Monotone: every prune REMOVES nodes from the frozen universe (a domain exclusion
    rejects that domain's still-present nodes). Nothing is ever added back. Gates: a
    domain must be known, a node must be on the current map, every action needs a reason."""
    canonical = {_norm_domain(d): d for d in service.known_domains()}
    on_map = set(universe) - set(rejected_nodes)
    confirmed = set(brief.domains)
    rejections: list[dict] = []

    def reject(action: dict, why: str) -> None:
        rejections.append({"kind": "scope_action", "raison_rejet": why, **action})

    for action in actions:
        kind = action.get("action")
        reason = str(action.get("raison", "")).strip()
        if kind in ("exclure_domaine", "inclure_domaine"):
            domain = canonical.get(_norm_domain(str(action.get("domaine", ""))))
            if domain is None or not reason:
                reject(action, "domaine inconnu ou raison manquante")
                continue
            if kind == "inclure_domaine":
                if domain not in brief.domains:
                    brief.domains.append(domain)
                    confirmed.add(domain)
                if domain in brief.excluded_domains:
                    brief.excluded_domains.remove(domain)
                continue
            if domain not in brief.excluded_domains:
                brief.excluded_domains.append(domain)
            if domain in brief.domains:
                brief.domains.remove(domain)
                confirmed.discard(domain)
            # monotone narrowing: drop this domain's still-present nodes from the map
            for node_id in on_map:
                node_domains = set(service.get_node(node_id).domains)
                if domain in node_domains and not (node_domains & confirmed):
                    rejected_nodes[node_id] = f"domaine « {domain} » écarté : {reason}"
        elif kind == "hors_perimetre":
            node_id = str(action.get("node_id", ""))
            if node_id not in on_map or not reason:
                reject(action, "nœud hors carte ou raison manquante")
                continue
            rejected_nodes[node_id] = reason
        else:
            reject(action, f"action inconnue : {kind}")
    return rejections
