import pytest
from pydantic import ValidationError

from core.graph.models import TOPOLOGY, Edge, EdgeType


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
