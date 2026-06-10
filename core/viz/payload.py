"""Build the display payload for the graph viewer and the future Context Map.

This is the durable seam (graph-viz design spec): the standalone viewer, the W2
web Context Map pane, and the W4 scoping highlight mode all consume this structure.
"""

from core.graph.models import Node
from core.graph.service import GraphService

_SUMMARY_LIMIT = 200


def build_payload(
    service: GraphService,
    *,
    focus: str | None = None,
    k: int = 2,
    domains: set[str] | None = None,
    types: set[str] | None = None,
    highlight: set[str] | None = None,
) -> dict:
    """Filterable view of the graph as a JSON-serializable dict.

    Filters compose by intersection; edges are kept iff both endpoints are kept.
    `highlight` is display-only: unknown ids raise, filtered-out ids are dropped.
    """
    wanted_highlight = set(highlight or ())
    for node_id in wanted_highlight:
        service.get_node(node_id)  # raises UnknownNodeError on unknown ids

    nodes = {node.id: node for node in service.all_nodes()}

    kept = set(nodes)
    if focus is not None:
        kept &= set(service.k_hop(focus, k=k)) | {focus}
    if domains is not None:
        kept = {nid for nid in kept if set(nodes[nid].domains) & domains}
    if types is not None:
        kept = {nid for nid in kept if nodes[nid].type in types}

    edges = [
        edge
        for edge in service.all_edges()
        if edge.source_id in kept and edge.target_id in kept
    ]
    return {
        "nodes": [_node_payload(nodes[nid]) for nid in sorted(kept)],
        "edges": [
            {
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.type.value,
                "note": edge.note,
            }
            for edge in edges
        ],
        "highlight": sorted(wanted_highlight & kept),
    }


def _node_payload(node: Node) -> dict:
    label = getattr(node, "name", "") or getattr(node, "title", "")
    summary = getattr(node, "description", "") or getattr(node, "statement", "")
    if len(summary) > _SUMMARY_LIMIT:
        summary = summary[: _SUMMARY_LIMIT - 1].rstrip() + "…"
    aliases = getattr(node, "aliases", [])
    return {
        "id": node.id,
        "label": label,
        "type": node.type,
        "domains": list(node.domains),
        "summary": summary,
        "search": " ".join([node.id, label, *aliases]).lower(),
    }
