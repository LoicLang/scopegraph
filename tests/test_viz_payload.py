# tests/test_viz_payload.py
from pathlib import Path

import pytest

from core.graph.service import GraphService, UnknownNodeError
from core.viz.payload import build_payload

GRAPH_DIR = Path(__file__).resolve().parent.parent / "graph"


@pytest.fixture(scope="module")
def service() -> GraphService:
    return GraphService.from_dir(GRAPH_DIR)


def test_full_graph_payload(service):
    payload = build_payload(service)
    assert len(payload["nodes"]) == 72
    assert len(payload["edges"]) == 100
    assert payload["highlight"] == []


def test_focus_subgraph_contains_founding_two_hop(service):
    payload = build_payload(service, focus="feat-mobile-ajout-benef", k=2)
    ids = {node["id"] for node in payload["nodes"]}
    assert "feat-mobile-ajout-benef" in ids
    assert "con-carence-beneficiaire-48h" in ids
    assert len(ids) < 72
    for edge in payload["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_domain_filter(service):
    payload = build_payload(service, domains={"tpe-acceptation"})
    assert payload["nodes"]
    for node in payload["nodes"]:
        assert "tpe-acceptation" in node["domains"]


def test_type_filter(service):
    payload = build_payload(service, types={"risk"})
    assert len(payload["nodes"]) == 6
    assert payload["edges"] == []  # no risk-to-risk edge exists in the seed


def test_highlight_passthrough_and_filtered_out(service):
    payload = build_payload(service, highlight={"obj-beneficiaire"})
    assert payload["highlight"] == ["obj-beneficiaire"]
    filtered = build_payload(service, types={"risk"}, highlight={"obj-beneficiaire"})
    assert filtered["highlight"] == []


def test_unknown_highlight_raises(service):
    with pytest.raises(UnknownNodeError):
        build_payload(service, highlight={"sys-fantome"})


def test_unknown_focus_raises(service):
    with pytest.raises(UnknownNodeError):
        build_payload(service, focus="sys-fantome")


def test_summaries_truncated_and_search_includes_aliases(service):
    payload = build_payload(service)
    by_id = {node["id"]: node for node in payload["nodes"]}
    assert all(len(node["summary"]) <= 200 for node in payload["nodes"])
    assert "monaut" in by_id["sys-moteur-autorisation"]["search"]
    assert "moteur d'autorisation" in by_id["sys-moteur-autorisation"]["search"]


def test_only_keeps_subset_and_their_edges(service):
    payload = build_payload(service, only={"sys-gestion-beneficiaires", "feat-benef-ajout"})
    ids = {node["id"] for node in payload["nodes"]}
    assert ids == {"sys-gestion-beneficiaires", "feat-benef-ajout"}
    for edge in payload["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_annotations_merge_into_node_payload(service):
    payload = build_payload(
        service,
        only={"sys-gestion-beneficiaires"},
        annotations={"sys-gestion-beneficiaires": {"role": "anchor", "score": 0.91}},
    )
    [node] = payload["nodes"]
    assert node["role"] == "anchor"
    assert node["score"] == 0.91
    assert node["label"]  # base payload fields still present
