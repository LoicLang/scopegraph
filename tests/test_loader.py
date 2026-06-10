import pytest

from core.graph.loader import GraphLoadError, load_graph

DOMAINS_YAML = "domains: [monetique, referentiel-client, banque-en-ligne]\n"

SYSTEM_YAML = """
type: system
id: sys-gestion-beneficiaires
name: Gestion des bénéficiaires
aliases: [BENEFGEST]
description: Référentiel et règles de gestion des bénéficiaires de virement.
owner_team: Équipe Référentiels
domains: [referentiel-client]
"""

FEATURE_YAML = """
type: feature
id: feat-benef-ajout
name: Ajout de bénéficiaire
description: Crée un bénéficiaire avec IBAN, BIC et libellé.
parameters: [IBAN, BIC, libellé]
domains: [referentiel-client]
"""

OBJECT_YAML = """
type: business_object
id: obj-beneficiaire
name: Bénéficiaire
description: Tiers destinataire de virements, rattaché à un client.
steward_team: Équipe Référentiels
domains: [referentiel-client]
"""

PART_OF_EDGE = """
  - source_id: feat-benef-ajout
    target_id: sys-gestion-beneficiaires
    type: PART_OF
"""


def write_graph(tmp_path, node_yamls, edges_yaml="edges: []\n", domains_yaml=DOMAINS_YAML):
    nodes_dir = tmp_path / "nodes"
    nodes_dir.mkdir()
    for i, content in enumerate(node_yamls):
        (nodes_dir / f"node{i}.yaml").write_text(content, encoding="utf-8")
    (tmp_path / "edges.yaml").write_text(edges_yaml, encoding="utf-8")
    (tmp_path / "domains.yaml").write_text(domains_yaml, encoding="utf-8")
    return tmp_path


def test_loads_nodes_and_edges(tmp_path):
    edges = "edges:\n" + PART_OF_EDGE
    nodes, edge_list = load_graph(
        write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges)
    )
    assert set(nodes) == {"sys-gestion-beneficiaires", "feat-benef-ajout"}
    assert len(edge_list) == 1


def test_missing_domains_file_fails(tmp_path):
    graph_dir = write_graph(tmp_path, [SYSTEM_YAML])
    (graph_dir / "domains.yaml").unlink()
    with pytest.raises(GraphLoadError, match="domains.yaml"):
        load_graph(graph_dir)


def test_unknown_domain_fails_with_filename(tmp_path):
    bad = SYSTEM_YAML.replace(
        "domains: [referentiel-client]", "domains: [blockchain]"
    )
    with pytest.raises(GraphLoadError, match="node0.yaml"):
        load_graph(write_graph(tmp_path, [bad]))


def test_duplicate_id_fails_with_filename(tmp_path):
    with pytest.raises(GraphLoadError, match="node1.yaml"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, SYSTEM_YAML]))


def test_edge_to_unknown_node_fails(tmp_path):
    edges = """
edges:
  - source_id: feat-benef-ajout
    target_id: sys-fantome
    type: PART_OF
"""
    with pytest.raises(GraphLoadError, match="sys-fantome"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges))
