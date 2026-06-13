"""CHALLENGING mechanics: gate A (triage), the deterministic governance pull
(the L4-residual answer), gate B (claims) — all pure, no LLM in this module.

The runtime decides; rejections are returned, never swallowed (hard rule 2)."""

import re
from dataclasses import dataclass

from core.dossier.template import CLAIM_SECTIONS
from core.graph.service import GraphService, UnknownNodeError

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?")

PULL_CAP = 10  # structural: max governance nodes pulled back per challenge
_PULL_EDGE_TYPES = {"CONSTRAINS", "SUPERSEDES"}
_PULL_NODE_TYPES = {"decision", "risk", "constraint"}
_CLAIM_KINDS = {"depends_on", "constraint_applies", "risk", "overlap"}


def gate_triage(
    verdicts: list[dict], submitted_ids: set[str]
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Returns (keeps {id: reason}, rejects {id: reason}, dropped unknown ids).

    Missing nodes default to KEEP — recall-first, the LLM must argue to remove."""
    keeps: dict[str, str] = {}
    rejects: dict[str, str] = {}
    dropped: list[str] = []
    seen: set[str] = set()
    for verdict in verdicts:
        node_id = str(verdict.get("node_id", ""))
        if node_id not in submitted_ids:
            dropped.append(node_id)
            continue
        seen.add(node_id)
        reason = str(verdict.get("reason", ""))
        if verdict.get("verdict") == "reject":
            rejects[node_id] = reason
        else:
            keeps[node_id] = reason
    for node_id in submitted_ids - seen:
        keeps[node_id] = ""
    return keeps, rejects, dropped


@dataclass(frozen=True)
class PulledNode:
    node_id: str
    via_id: str  # the kept node that brought it back
    edge_type: str


def pull_governance(
    service: GraphService, kept_ids: set[str], rejected_ids: set[str], cap: int = PULL_CAP
) -> list[PulledNode]:
    """1 hop from keeps along governance edges / to governance node types.

    Deterministic order: kept ids sorted, then neighbor edges sorted — stable runs."""
    pulled: list[PulledNode] = []
    seen = set(kept_ids) | set(rejected_ids)
    for kept_id in sorted(kept_ids):
        adjacent = sorted(
            service.neighbors(kept_id),
            key=lambda pair: (pair[0].type, pair[0].source_id, pair[0].target_id),
        )
        for edge, node in adjacent:
            if node.id in seen:
                continue
            if edge.type in _PULL_EDGE_TYPES or node.type in _PULL_NODE_TYPES:
                pulled.append(PulledNode(node_id=node.id, via_id=kept_id,
                                         edge_type=str(edge.type)))
                seen.add(node.id)
                if len(pulled) >= cap:
                    return pulled
    return pulled


def _node_line(node) -> str:
    title = getattr(node, "name", "") or getattr(node, "title", "")
    description = getattr(node, "description", "") or getattr(node, "statement", "")
    return f"{node.id} · {node.type} · {title} — {description} (domaines : {', '.join(node.domains)})"


def _edge_lines(service: GraphService, ids: set[str]) -> list[str]:
    return [
        f"{edge.source_id} —{edge.type}→ {edge.target_id}"
        for edge in service.all_edges()
        if edge.source_id in ids and edge.target_id in ids
    ]


def render_subgraph(result, service: GraphService) -> str:
    """Plain-text French rendering of the raw retrieved map (triage input).

    Dumb and complete — the LLM needs the descriptions to judge. Shared with
    the challenge bench (scripts/challenge-eval)."""
    ids = set(result.node_ids())
    lines = [_node_line(service.get_node(s.node_id)) for s in [*result.anchors, *result.expanded]]
    return "\n".join(lines + _edge_lines(service, ids))


def render_stabilized(
    keeps: dict[str, str], pulled: list[PulledNode], service: GraphService
) -> str:
    """Plain-text rendering of the stabilized map: keeps + pulled-back governance."""
    ids = set(keeps) | {p.node_id for p in pulled}
    lines = [_node_line(service.get_node(node_id)) for node_id in sorted(keeps)]
    lines += [
        f"{_node_line(service.get_node(p.node_id))} [ramené via {p.via_id} ← {p.edge_type}]"
        for p in pulled
    ]
    return "\n".join(lines + _edge_lines(service, ids))


def node_provenance(service: GraphService, node_ids: list[str]) -> list[dict]:
    """Authoritative facts for the cited nodes (claim fidelity, W3 spec §5).

    The runtime is the source of truth: each claim ships its cited nodes' real text
    so the user verifies the LLM's paraphrase against the seed, not the other way
    round. Unknown ids are dropped (gate B already rejects out-of-map claims)."""
    facts: list[dict] = []
    for node_id in node_ids:
        try:
            node = service.get_node(node_id)
        except UnknownNodeError:
            continue
        title = getattr(node, "name", "") or getattr(node, "title", "")
        text = getattr(node, "description", "") or getattr(node, "statement", "")
        facts.append({"node_id": node_id, "label": title, "type": node.type, "text": text})
    return facts


def statement_fact_flags(statement: str, source_texts: list[str]) -> list[str]:
    """Numbers/percentages in the free-prose challenge statement absent from every
    cited source AND from the user's own words — likely fabricated (e.g. « 30 % »
    when the node says « une part significative »). Deterministic guard: the claims
    carry provenance, the statement is prose, so the runtime flags unsourced figures
    for the user to check (W3 known-limits L4 — statement fidelity)."""
    haystack = " ".join(source_texts)
    return [num for num in dict.fromkeys(_NUMBER_RE.findall(statement)) if num not in haystack]


def gate_domains(domains: list[str], service: GraphService) -> list[str]:
    known = service.known_domains()
    return [d for d in domains if d in known]


def gate_claims(
    payload: dict, map_ids: set[str], service: GraphService
) -> tuple[list[dict], list[dict]]:
    """Returns (valid claims, rejected claims each carrying reason_rejected)."""
    valid: list[dict] = []
    rejected: list[dict] = []
    for claim in payload.get("claims", []):
        node_ids = [str(n) for n in claim.get("node_ids", [])]
        section = claim.get("target_section", "")
        kind = claim.get("kind", "")
        problem = ""
        if kind not in _CLAIM_KINDS:
            problem = f"type de claim inconnu : {kind}"
        elif not node_ids or any(n not in map_ids for n in node_ids):
            problem = "cite un nœud hors de la carte stabilisée"
        elif section not in CLAIM_SECTIONS:
            problem = f"section non autorisée : {section}"
        elif not str(claim.get("reason", "")).strip():
            problem = "raison manquante"  # ungrounded for the card/EDB text
        if problem:
            rejected.append({**claim, "reason_rejected": problem})
        else:
            valid.append(claim)
    return valid, rejected
