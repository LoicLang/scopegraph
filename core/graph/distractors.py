"""Distractor pool: parsing, validation, deterministic prefix sampling (W3 lot 0).

The pool lives in graph-distractors/ — one YAML shard per domain (a coherent fictional
mini-ecosystem: `nodes:` ordered parents-before-features, plus intra-domain `edges:`)
and edges.yaml for inter-domain edges among distractors. Bench/test-only: the app and
the demo never load this. Spec: docs/specs/2026-06-11-distractor-stress-bench-design.md.
"""

from pathlib import Path

from pydantic import ValidationError

from core.graph.loader import GraphLoadError, _check_topology, _read_yaml, validate_node
from core.graph.models import Edge, Node

EDGES_FILE = "edges.yaml"


def load_distractor_pool(
    pool_dir: Path, vocabulary: frozenset[str], reserved_ids: frozenset[str]
) -> tuple[dict[str, list[Node]], list[Edge]]:
    """Parse and validate the full pool.

    Returns (shard name -> nodes in file order, all pool edges). Fail-fast on:
    non-synthetic provenance, id collisions (pool-internal or vs reserved seed ids),
    edges referencing anything outside the pool (which bans distractor↔seed edges),
    topology violations (ADR 0001).
    """
    if not pool_dir.is_dir():
        raise GraphLoadError(f"{pool_dir}: distractor pool directory not found")
    shard_paths = sorted(p for p in pool_dir.glob("*.yaml") if p.name != EDGES_FILE)
    if not shard_paths:
        raise GraphLoadError(f"{pool_dir}: no distractor shards found")

    shards: dict[str, list[Node]] = {}
    pool_nodes: dict[str, Node] = {}
    raw_edges: list[tuple[Path, int, dict]] = []
    for path in shard_paths:
        data = _read_yaml(path) or {}
        shard: list[Node] = []
        for raw in data.get("nodes") or []:
            node = validate_node(raw, path, vocabulary)
            if node.id in pool_nodes or node.id in reserved_ids:
                raise GraphLoadError(f"{path}: id '{node.id}' already used (pool or seed)")
            if node.created_from != "synthetic":
                raise GraphLoadError(
                    f"{path}: node '{node.id}' must carry created_from: synthetic"
                )
            pool_nodes[node.id] = node
            shard.append(node)
        shards[path.stem] = shard
        raw_edges.extend((path, i, raw) for i, raw in enumerate(data.get("edges") or []))

    inter_path = pool_dir / EDGES_FILE
    if inter_path.exists():
        inter_raw = (_read_yaml(inter_path) or {}).get("edges") or []
        raw_edges.extend((inter_path, i, raw) for i, raw in enumerate(inter_raw))

    edges: list[Edge] = []
    for path, i, raw in raw_edges:
        try:
            edge = Edge.model_validate(raw)
        except ValidationError as exc:
            raise GraphLoadError(f"{path}: edge #{i}: {exc}") from exc
        if edge.created_from != "synthetic":
            raise GraphLoadError(f"{path}: edge #{i} must carry created_from: synthetic")
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in pool_nodes:
                raise GraphLoadError(
                    f"{path}: edge #{i} references '{endpoint}' outside the pool"
                )
        _check_topology(edge, pool_nodes, path, i)
        edges.append(edge)
    return shards, edges


def sample_pool(shards: dict[str, list[Node]], n: int) -> list[Node]:
    """Deterministic prefix sample: the first ~n/len(shards) nodes of each shard.

    Shards are ordered parents-before-features, so any prefix keeps every sampled
    feature's parent system (PART_OF cardinality holds at any n — verified again by
    _check_graph_rules on the merged graph). The remainder n % len(shards) goes to
    the alphabetically-first shards. No RNG anywhere.
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    names = sorted(shards)
    base, extra = divmod(n, len(names))
    sampled: list[Node] = []
    for rank, name in enumerate(names):
        quota = base + (1 if rank < extra else 0)
        sampled.extend(shards[name][:quota])
    return sampled
