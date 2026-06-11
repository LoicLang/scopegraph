"""Load the YAML graph (domains.yaml + nodes/*.yaml + edges.yaml) into schema-v1 objects.

Fail-fast: any invalid file aborts the load with the offending path in the error.
All graph rules of ADR 0001 are enforced here: domain vocabulary, edge endpoint
existence, edge topology, PART_OF cardinality, cancelled-project restrictions.
"""

from collections import Counter
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from core.graph.models import TOPOLOGY, Edge, EdgeType, Node

_NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)

# Id prefix per node type (ADR 0001 shared fields).
_ID_PREFIXES: dict[str, str] = {
    "system": "sys-",
    "feature": "feat-",
    "business_object": "obj-",
    "project": "proj-",
    "decision": "dec-",
    "constraint": "con-",
    "risk": "risk-",
}


class GraphLoadError(Exception):
    """The graph on disk violates schema v1 (ADR 0001)."""


def validate_node(data: dict, path: Path, vocabulary: frozenset[str]) -> Node:
    """Validate one raw node mapping: schema v1, id prefix, domain vocabulary."""
    try:
        node = _NODE_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise GraphLoadError(f"{path}: invalid node: {exc}") from exc
    expected_prefix = _ID_PREFIXES[node.type]
    if not node.id.startswith(expected_prefix):
        raise GraphLoadError(
            f"{path}: id '{node.id}' must carry the '{expected_prefix}' prefix "
            f"for type '{node.type}' (ADR 0001)"
        )
    unknown = set(node.domains) - vocabulary
    if unknown:
        raise GraphLoadError(
            f"{path}: unknown domains {sorted(unknown)} "
            "(vocabulary: graph/domains.yaml, governed by ADR)"
        )
    return node


def load_domains(graph_dir: Path) -> frozenset[str]:
    path = graph_dir / "domains.yaml"
    if not path.exists():
        raise GraphLoadError(f"{path}: missing domain vocabulary file")
    domains = (_read_yaml(path) or {}).get("domains") or []
    if not domains:
        raise GraphLoadError(f"{path}: empty domain vocabulary")
    return frozenset(domains)


def load_graph(graph_dir: Path) -> tuple[dict[str, Node], list[Edge]]:
    vocabulary = load_domains(graph_dir)

    nodes: dict[str, Node] = {}
    for path in sorted((graph_dir / "nodes").glob("*.yaml")):
        node = validate_node(_read_yaml(path), path, vocabulary)
        if node.id in nodes:
            raise GraphLoadError(f"{path}: duplicate node id '{node.id}'")
        nodes[node.id] = node

    edges: list[Edge] = []
    edges_path = graph_dir / "edges.yaml"
    raw_edges = (_read_yaml(edges_path) or {}).get("edges") or []
    for index, raw in enumerate(raw_edges):
        try:
            edge = Edge.model_validate(raw)
        except ValidationError as exc:
            raise GraphLoadError(f"{edges_path}: edge #{index}: {exc}") from exc
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in nodes:
                raise GraphLoadError(
                    f"{edges_path}: edge #{index} references unknown node '{endpoint}'"
                )
        _check_topology(edge, nodes, edges_path, index)
        edges.append(edge)

    _check_graph_rules(nodes, edges)
    return nodes, edges


def _check_topology(
    edge: Edge, nodes: dict[str, Node], path: Path, index: int
) -> None:
    if edge.type is EdgeType.RELATES_TO:
        return
    pair = (nodes[edge.source_id].type, nodes[edge.target_id].type)
    if pair not in TOPOLOGY[edge.type]:
        raise GraphLoadError(
            f"{path}: edge #{index}: {edge.type.value} not allowed "
            f"from '{pair[0]}' to '{pair[1]}' (ADR 0001 topology)"
        )


def _check_graph_rules(nodes: dict[str, Node], edges: list[Edge]) -> None:
    parent_counts = Counter(
        edge.source_id for edge in edges if edge.type is EdgeType.PART_OF
    )
    for node in nodes.values():
        if node.type == "feature" and parent_counts.get(node.id, 0) != 1:
            raise GraphLoadError(
                f"feature '{node.id}' must have exactly one PART_OF edge "
                f"(found {parent_counts.get(node.id, 0)})"
            )

    cancelled = {
        node.id
        for node in nodes.values()
        if node.type == "project" and node.status == "cancelled"
    }
    for edge in edges:
        if edge.type is EdgeType.RELATES_TO:
            continue
        if edge.source_id in cancelled or edge.target_id in cancelled:
            raise GraphLoadError(
                f"cancelled project may only carry RELATES_TO edges: "
                f"{edge.source_id} -{edge.type.value}-> {edge.target_id}"
            )


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GraphLoadError(f"{path}: invalid YAML: {exc}") from exc
