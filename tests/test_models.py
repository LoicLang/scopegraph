import pytest
from pydantic import TypeAdapter, ValidationError

from core.graph.models import TOPOLOGY, Edge, EdgeType
from core.graph.models import BusinessObject, Feature, Node, System


def test_edge_type_has_the_seven_adr_0001_members():
    assert {e.value for e in EdgeType} == {
        "DEPENDS_ON", "PART_OF", "OPERATES_ON", "PRODUCED",
        "CONSTRAINS", "SUPERSEDES", "RELATES_TO",
    }


def test_topology_covers_every_type_except_relates_to():
    assert set(TOPOLOGY) == set(EdgeType) - {EdgeType.RELATES_TO}
    assert ("feature", "system") in TOPOLOGY[EdgeType.PART_OF]
    assert ("system", "business_object") in TOPOLOGY[EdgeType.OPERATES_ON]


def test_edge_valid():
    edge = Edge(
        source_id="feat-mobile-ajout-benef",
        target_id="feat-benef-api",
        type=EdgeType.DEPENDS_ON,
        evidence="description of feat-mobile-ajout-benef",
    )
    assert edge.verified is False
    assert edge.created_from == "seed"


def test_relates_to_requires_note():
    with pytest.raises(ValidationError, match="RELATES_TO"):
        Edge(source_id="a-b", target_id="c-d", type=EdgeType.RELATES_TO)


def test_edge_created_from_format_enforced():
    with pytest.raises(ValidationError):
        Edge(source_id="a-b", target_id="c-d", type=EdgeType.DEPENDS_ON, created_from="manual")


def test_system_valid_and_frozen():
    sys_node = System(
        id="sys-moteur-autorisation",
        name="Moteur d'autorisation carte",
        aliases=["MONAUT"],
        description="Autorise les transactions carte en temps réel.",
        owner_team="Équipe Monétique",
        domains=["monetique"],
    )
    assert sys_node.type == "system"
    with pytest.raises(ValidationError):
        sys_node.name = "autre"  # frozen


def test_feature_valid():
    feat = Feature(
        id="feat-benef-ajout",
        name="Ajout de bénéficiaire",
        description="Crée un bénéficiaire avec IBAN, BIC et libellé.",
        parameters=["IBAN", "BIC", "libellé"],
        domains=["referentiel-client"],
    )
    assert feat.type == "feature"


def test_business_object_valid():
    obj = BusinessObject(
        id="obj-beneficiaire",
        name="Bénéficiaire",
        description="Tiers destinataire de virements, rattaché à un client.",
        steward_team="Équipe Référentiels",
        domains=["referentiel-client"],
    )
    assert obj.type == "business_object"


def test_node_union_discriminates_on_type():
    adapter = TypeAdapter(Node)
    node = adapter.validate_python({
        "type": "feature",
        "id": "feat-ip-emission",
        "name": "Émission de virement instantané",
        "description": "Émet un virement SEPA Inst en moins de 10 secondes.",
        "domains": ["paiement-instantane"],
    })
    assert isinstance(node, Feature)
    assert node.parameters == []


def test_node_requires_at_least_one_domain():
    with pytest.raises(ValidationError):
        System(id="sys-x", name="X", description="d", owner_team="t", domains=[])
