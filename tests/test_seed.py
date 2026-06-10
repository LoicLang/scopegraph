"""Integration: the real seed graph loads and contains the 7 deliberate traps
(design spec 2026-06-10 §4)."""

from pathlib import Path

import pytest

from core.graph.models import EdgeType
from core.graph.service import GraphService

GRAPH_DIR = Path(__file__).resolve().parent.parent / "graph"


@pytest.fixture(scope="module")
def service() -> GraphService:
    return GraphService.from_dir(GRAPH_DIR)


def test_seed_size_and_layer_counts(service):
    nodes = service.all_nodes()
    assert 70 <= len(nodes) <= 80
    by_type = {}
    for node in nodes:
        by_type[node.type] = by_type.get(node.type, 0) + 1
    assert by_type == {
        "system": 9, "feature": 24, "business_object": 6,
        "project": 7, "decision": 8, "constraint": 12, "risk": 6,
    }
    covered = {domain for node in nodes for domain in node.domains}
    assert len(covered) == 10


def test_trap_1_alias_monaut(service):
    node = service.get_node("sys-moteur-autorisation")
    assert "MONAUT" in node.aliases


def test_trap_2_superseded_decision(service):
    superseding = [
        edge for edge in service.all_edges() if edge.type == EdgeType.SUPERSEDES
    ]
    assert any(
        edge.source_id == "dec-scoring-unique"
        and edge.target_id == "dec-scoring-par-canal-2021"
        for edge in superseding
    )
    assert service.get_node("dec-scoring-par-canal-2021").still_active is False


def test_trap_3_contradiction_is_marked(service):
    hits = service.neighbors(
        "dec-gel-evolutions-monetique", edge_types={EdgeType.RELATES_TO}
    )
    assert any(node.id == "dec-reutilisation-sca" for _, node in hits)


def test_trap_4_cross_domain_two_hop_chain(service):
    # From the TPE software, PCI DSS is reachable only through MONAUT.
    reached = service.k_hop("sys-logiciel-tpe", k=2)
    assert "con-pci-dss" in reached
    path = reached["con-pci-dss"]
    assert [edge.type for edge in path] == [EdgeType.DEPENDS_ON, EdgeType.CONSTRAINS]


def test_trap_5_constraint_inheritance_via_shared_object(service):
    # The founding example: the mobile add-beneficiary feature inherits the
    # 48h cooling-off rule through obj-beneficiaire, with full provenance.
    reached = service.k_hop("feat-mobile-ajout-benef", k=2)
    for constraint_id in (
        "con-carence-beneficiaire-48h",
        "con-sca-ajout-beneficiaire",
        "con-verif-sanctions-creation",
    ):
        assert constraint_id in reached
        path = reached[constraint_id]
        assert [edge.type for edge in path] == [
            EdgeType.OPERATES_ON, EdgeType.CONSTRAINS,
        ]
    # ... and discovers the sibling feature in BENEFGEST the same way.
    assert "feat-benef-ajout" in reached


def test_trap_6_non_uniform_depth(service):
    zoomed = set()
    for edge in service.all_edges():
        if edge.type == EdgeType.PART_OF:
            zoomed.add(edge.target_id)
    assert zoomed == {
        "sys-gestion-beneficiaires", "sys-app-mobile", "sys-passerelle-ip",
        "sys-moteur-autorisation", "sys-referentiel-client",
    }
    # A coarse system still participates in the object web at system grain.
    hits = service.neighbors("sys-scoring-fraude", edge_types={EdgeType.OPERATES_ON})
    assert any(node.id == "obj-alerte-fraude" for _, node in hits)


def test_trap_7_cancelled_project_is_memorial_only(service):
    node = service.get_node("proj-refonte-parcours-beneficiaire")
    assert node.status == "cancelled"
    hits = service.neighbors("proj-refonte-parcours-beneficiaire")
    assert len(hits) == 1
    edge, target = hits[0]
    assert edge.type == EdgeType.RELATES_TO
    assert target.id == "obj-beneficiaire"
    assert edge.note  # the abandon reason travels with the link
