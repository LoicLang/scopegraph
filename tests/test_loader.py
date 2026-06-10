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


def test_topology_violation_fails(tmp_path):
    edges = """
edges:
  - source_id: sys-gestion-beneficiaires
    target_id: feat-benef-ajout
    type: PART_OF
"""
    with pytest.raises(GraphLoadError, match="topology"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges))


def test_feature_without_parent_fails(tmp_path):
    with pytest.raises(GraphLoadError, match="exactly one PART_OF"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML]))


def test_feature_with_two_parents_fails(tmp_path):
    edges = "edges:\n" + PART_OF_EDGE + PART_OF_EDGE
    with pytest.raises(GraphLoadError, match="exactly one PART_OF"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges))


CANCELLED_PROJECT_YAML = """
type: project
id: proj-refonte-parcours-beneficiaire
name: Refonte du parcours bénéficiaire
description: Tentative de refonte abandonnée en 2023.
status: cancelled
owner_team: Équipe Canaux
outcomes: Migration du stock jugée infaisable sans fenêtre de gel.
domains: [banque-en-ligne]
"""


def test_cancelled_project_with_structural_edge_fails(tmp_path):
    edges = """
edges:
  - source_id: proj-refonte-parcours-beneficiaire
    target_id: sys-gestion-beneficiaires
    type: PRODUCED
"""
    with pytest.raises(GraphLoadError, match="cancelled"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, CANCELLED_PROJECT_YAML], edges))


def test_cancelled_project_relates_to_is_allowed(tmp_path):
    edges = """
edges:
  - source_id: proj-refonte-parcours-beneficiaire
    target_id: obj-beneficiaire
    type: RELATES_TO
    note: tentative de refonte abandonnée en 2023 — migration du stock infaisable
"""
    nodes, edge_list = load_graph(
        write_graph(tmp_path, [SYSTEM_YAML, OBJECT_YAML, CANCELLED_PROJECT_YAML], edges)
    )
    assert len(edge_list) == 1


def test_id_prefix_must_match_node_type(tmp_path):
    bad = FEATURE_YAML.replace("id: feat-benef-ajout", "id: sys-benef-ajout")
    with pytest.raises(GraphLoadError, match="prefix"):
        load_graph(write_graph(tmp_path, [bad]))
