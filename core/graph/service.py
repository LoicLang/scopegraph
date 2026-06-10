"""In-memory graph service: the deterministic read API over the loaded graph."""

from collections.abc import Iterable
from pathlib import Path

from core.graph.loader import load_graph
from core.graph.models import Edge, EdgeType, Node


class UnknownNodeError(KeyError):
    """Raised when a node id does not exist in the graph."""


class GraphService:
    def __init__(self, nodes: dict[str, Node], edges: list[Edge]) -> None:
        self._nodes = nodes
        self._edges = edges
        self._adjacency: dict[str, list[Edge]] = {node_id: [] for node_id in nodes}
        for edge in edges:
            self._adjacency[edge.source_id].append(edge)
            self._adjacency[edge.target_id].append(edge)

    @classmethod
    def from_dir(cls, graph_dir: Path) -> "GraphService":
        return cls(*load_graph(graph_dir))

    def get_node(self, node_id: str) -> Node:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise UnknownNodeError(f"unknown node id '{node_id}'") from None

    def all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def all_edges(self) -> list[Edge]:
        return list(self._edges)

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> list[tuple[Edge, Node]]:
        """Adjacent (edge, node) pairs, both directions, in stable edge order."""
        self.get_node(node_id)  # raises on unknown id
        wanted = set(edge_types) if edge_types is not None else None
        result: list[tuple[Edge, Node]] = []
        for edge in self._adjacency[node_id]:
            if wanted is not None and edge.type not in wanted:
                continue
            other_id = edge.target_id if edge.source_id == node_id else edge.source_id
            result.append((edge, self._nodes[other_id]))
        return result

    def k_hop(self, start: str, k: int) -> dict[str, list[Edge]]:
        """BFS up to k hops (edges treated as undirected).

        Returns reached node id -> shortest path as the list of edges from start.
        The start node itself is excluded.
        """
        self.get_node(start)
        paths: dict[str, list[Edge]] = {start: []}
        frontier = [start]
        for _ in range(k):
            next_frontier: list[str] = []
            for node_id in frontier:
                for edge, node in self.neighbors(node_id):
                    if node.id in paths:
                        continue
                    paths[node.id] = [*paths[node_id], edge]
                    next_frontier.append(node.id)
            frontier = next_frontier
        del paths[start]
        return paths
