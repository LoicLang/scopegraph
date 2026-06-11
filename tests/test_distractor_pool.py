"""Data gates over the committed distractor pool (pure YAML — CI-safe, no model).

Pool-shape contract from the W3 lot 0 spec: 10 shards × 200 nodes, parents before
features, synthetic-only, edges closed over the pool. Skipped only if the pool has
not been generated yet (pre-Task-9 working tree).
"""

from pathlib import Path

import pytest

from core.graph.distractors import load_distractor_pool
from core.graph.loader import load_domains, load_graph
from core.graph.service import GraphService

ROOT = Path(__file__).resolve().parent.parent
POOL_DIR = ROOT / "graph-distractors"

pytestmark = pytest.mark.skipif(
    not POOL_DIR.is_dir(), reason="distractor pool not generated yet (W3 lot 0 task 7-9)"
)


@pytest.fixture(scope="module")
def pool():
    vocabulary = load_domains(ROOT / "graph")
    nodes, _ = load_graph(ROOT / "graph")
    return load_distractor_pool(POOL_DIR, vocabulary, frozenset(nodes))


def test_ten_shards_of_two_hundred(pool):
    shards, _ = pool
    assert len(shards) == 10
    assert {name: len(nodes) for name, nodes in shards.items()} == dict.fromkeys(shards, 200)


def test_pool_has_inter_domain_edges(pool):
    shards, edges = pool
    domain_of = {n.id: name for name, nodes in shards.items() for n in nodes}
    inter = [e for e in edges if domain_of[e.source_id] != domain_of[e.target_id]]
    assert len(inter) >= 60, "edge agent must produce a real inter-domain mesh"


def test_full_merge_loads(pool):
    service = GraphService.from_dirs(ROOT / "graph", POOL_DIR, 2000)
    assert len(service.all_nodes()) == 72 + 2000


@pytest.mark.parametrize("n", [1, 7, 500, 1000, 1999])
def test_any_prefix_n_is_loadable(n):
    service = GraphService.from_dirs(ROOT / "graph", POOL_DIR, n)
    assert len(service.all_nodes()) == 72 + n
