"""Distractor pool loading + prefix sampling (hermetic: tmp-path YAML only)."""

from pathlib import Path

import pytest

from core.graph.distractors import load_distractor_pool, sample_pool
from core.graph.loader import GraphLoadError

DOMAINS_YAML = "domains:\n  - alpha\n  - beta\n"

SEED_NODE = """\
type: system
id: sys-core
name: Coeur seed
description: Système du seed.
owner_team: Equipe Seed
domains: [alpha]
"""

ALPHA_SHARD = """\
nodes:
  - type: system
    id: sys-da-un
    name: DA Un
    description: Premier système distracteur.
    owner_team: Equipe A
    domains: [alpha]
    created_from: synthetic
  - type: feature
    id: feat-da-un-a
    name: Fonction A
    description: Fonction du système DA Un.
    domains: [alpha]
    created_from: synthetic
  - type: feature
    id: feat-da-un-b
    name: Fonction B
    description: Autre fonction du système DA Un.
    domains: [alpha]
    created_from: synthetic
edges:
  - {source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF, created_from: synthetic}
  - {source_id: feat-da-un-b, target_id: sys-da-un, type: PART_OF, created_from: synthetic}
"""

BETA_SHARD = """\
nodes:
  - type: system
    id: sys-db-un
    name: DB Un
    description: Système distracteur du domaine beta.
    owner_team: Equipe B
    domains: [beta]
    created_from: synthetic
  - type: risk
    id: risk-db-un
    title: Risque distracteur
    statement: Un risque plausible du domaine beta.
    likelihood: low
    impact: medium
    domains: [beta]
    created_from: synthetic
"""


def write_seed(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "graph"
    (graph_dir / "nodes").mkdir(parents=True)
    (graph_dir / "domains.yaml").write_text(DOMAINS_YAML, encoding="utf-8")
    (graph_dir / "nodes" / "sys-core.yaml").write_text(SEED_NODE, encoding="utf-8")
    (graph_dir / "edges.yaml").write_text("edges: []\n", encoding="utf-8")
    return graph_dir


def write_pool(
    tmp_path: Path,
    alpha: str = ALPHA_SHARD,
    beta: str = BETA_SHARD,
    inter: str | None = None,
) -> Path:
    pool_dir = tmp_path / "graph-distractors"
    pool_dir.mkdir()
    (pool_dir / "alpha.yaml").write_text(alpha, encoding="utf-8")
    (pool_dir / "beta.yaml").write_text(beta, encoding="utf-8")
    if inter is not None:
        (pool_dir / "edges.yaml").write_text(inter, encoding="utf-8")
    return pool_dir


VOCAB = frozenset({"alpha", "beta"})


def test_pool_loads_shards_in_file_order(tmp_path):
    pool_dir = write_pool(tmp_path)
    shards, edges = load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))
    assert [n.id for n in shards["alpha"]] == ["sys-da-un", "feat-da-un-a", "feat-da-un-b"]
    assert [n.id for n in shards["beta"]] == ["sys-db-un", "risk-db-un"]
    assert len(edges) == 2  # the two PART_OF


def test_inter_domain_edges_yaml_is_loaded(tmp_path):
    inter = (
        "edges:\n"
        "  - {source_id: sys-da-un, target_id: sys-db-un, type: DEPENDS_ON,"
        " created_from: synthetic}\n"
    )
    pool_dir = write_pool(tmp_path, inter=inter)
    _, edges = load_distractor_pool(pool_dir, VOCAB, frozenset())
    assert len(edges) == 3


def test_non_synthetic_node_rejected(tmp_path):
    bad = ALPHA_SHARD.replace("created_from: synthetic", "created_from: seed", 1)
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="created_from: synthetic"):
        load_distractor_pool(pool_dir, VOCAB, frozenset())


def test_non_synthetic_edge_rejected(tmp_path):
    bad = ALPHA_SHARD.replace(
        "{source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF,"
        " created_from: synthetic}",
        "{source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF}",
    )
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="created_from: synthetic"):
        load_distractor_pool(pool_dir, VOCAB, frozenset())


def test_edge_referencing_seed_id_rejected(tmp_path):
    inter = (
        "edges:\n"
        "  - {source_id: sys-da-un, target_id: sys-core, type: DEPENDS_ON,"
        " created_from: synthetic}\n"
    )
    pool_dir = write_pool(tmp_path, inter=inter)
    with pytest.raises(GraphLoadError, match="outside the pool"):
        load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))


def test_pool_id_colliding_with_seed_rejected(tmp_path):
    bad = ALPHA_SHARD.replace("id: sys-da-un", "id: sys-core")
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="already used"):
        load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))


def test_missing_pool_dir_rejected(tmp_path):
    with pytest.raises(GraphLoadError, match="not found"):
        load_distractor_pool(tmp_path / "nope", VOCAB, frozenset())


def test_sample_pool_prefix_and_remainder(tmp_path):
    pool_dir = write_pool(tmp_path)
    shards, _ = load_distractor_pool(pool_dir, VOCAB, frozenset())
    # n=3 over 2 shards: divmod -> base 1, remainder to alphabetically-first (alpha)
    assert [n.id for n in sample_pool(shards, 3)] == ["sys-da-un", "feat-da-un-a", "sys-db-un"]
    assert sample_pool(shards, 0) == []
