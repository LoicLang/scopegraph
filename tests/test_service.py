import pytest

from core.graph.models import (
    BusinessObject, Constraint, Edge, EdgeType, Feature, System,
)
from core.graph.service import GraphService, UnknownNodeError


@pytest.fixture()
def service() -> GraphService:
    nodes = [
        System(
            id="sys-gestion-beneficiaires",
            name="Gestion des bénéficiaires",
            description="Référentiel des bénéficiaires.",
            owner_team="Référentiels",
            domains=["referentiel-client"],
        ),
        Feature(
            id="feat-benef-ajout",
            name="Ajout de bénéficiaire",
            description="Crée un bénéficiaire.",
            domains=["referentiel-client"],
        ),
        Feature(
            id="feat-mobile-ajout-benef",
            name="Ajout de bénéficiaire (mobile)",
            description="Crée un bénéficiaire depuis l'app mobile.",
            domains=["banque-en-ligne"],
        ),
        BusinessObject(
            id="obj-beneficiaire",
            name="Bénéficiaire",
            description="Tiers destinataire de virements.",
            domains=["referentiel-client"],
        ),
        Constraint(
            id="con-carence-beneficiaire-48h",
            title="Délai de carence bénéficiaire",
            statement="Tout nouveau bénéficiaire est inutilisable pendant 48 heures.",
            source="politique interne fraude",
            severity="high",
            domains=["referentiel-client"],
        ),
        System(
            id="sys-isole",
            name="Système isolé",
            description="Aucun lien.",
            owner_team="Autre",
            domains=["referentiel-client"],
        ),
    ]
    edges = [
        Edge(source_id="feat-benef-ajout", target_id="sys-gestion-beneficiaires",
             type=EdgeType.PART_OF),
        Edge(source_id="feat-benef-ajout", target_id="obj-beneficiaire",
             type=EdgeType.OPERATES_ON),
        Edge(source_id="feat-mobile-ajout-benef", target_id="obj-beneficiaire",
             type=EdgeType.OPERATES_ON),
        Edge(source_id="con-carence-beneficiaire-48h", target_id="obj-beneficiaire",
             type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def test_get_node(service):
    assert service.get_node("con-carence-beneficiaire-48h").severity == "high"


def test_get_unknown_node_raises(service):
    with pytest.raises(UnknownNodeError, match="sys-fantome"):
        service.get_node("sys-fantome")


def test_neighbors_are_bidirectional(service):
    hits = service.neighbors("obj-beneficiaire")
    ids = {node.id for _, node in hits}
    assert ids == {
        "feat-benef-ajout", "feat-mobile-ajout-benef", "con-carence-beneficiaire-48h",
    }


def test_neighbors_filter_by_edge_type(service):
    hits = service.neighbors("obj-beneficiaire", edge_types={EdgeType.CONSTRAINS})
    assert [node.id for _, node in hits] == ["con-carence-beneficiaire-48h"]


def test_neighbors_of_isolated_node_empty(service):
    assert service.neighbors("sys-isole") == []
