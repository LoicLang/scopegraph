"""Governance pull (deterministic) + gates A and B (the grounding guarantees)."""

import datetime

import pytest

from core.graph.models import Constraint, Decision, Edge, EdgeType, Risk, System
from core.graph.service import GraphService
from core.runtime.challenge import (
    gate_claims,
    gate_domains,
    gate_triage,
    node_provenance,
    pull_governance,
    render_node_set,
    statement_fact_flags,
)


@pytest.fixture
def service() -> GraphService:
    nodes = [
        System(id="sys-a", name="Moteur A", description="Système central.",
               owner_team="T", domains=["monetique"]),
        System(id="sys-far", name="Lointain", description="Connecté à dec-y seulement.",
               owner_team="T", domains=["monetique"]),
        Constraint(id="con-x", title="Règle X", statement="Cloisonnement requis.",
                   source="PCI", severity="high", domains=["monetique"]),
        Decision(id="dec-y", title="Décision Y", statement="Gel des évolutions.",
                 rationale="Plan de charge.", date=datetime.date(2026, 1, 1),
                 decided_by="DSI", domains=["monetique"]),
        Risk(id="risk-z", title="Risque Z", statement="Charge inconnue.",
             likelihood="medium", impact="high", domains=["monetique"]),
    ]
    edges = [
        Edge(source_id="con-x", target_id="sys-a", type=EdgeType.CONSTRAINS),
        Edge(source_id="dec-y", target_id="sys-a", type=EdgeType.CONSTRAINS),
        Edge(source_id="risk-z", target_id="sys-a", type=EdgeType.RELATES_TO,
             note="risque porté par le moteur"),
        Edge(source_id="dec-y", target_id="sys-far", type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


# -- gate A -----------------------------------------------------------------

def test_gate_triage_defaults_missing_nodes_to_keep_and_drops_unknown_ids():
    submitted = {"sys-a", "con-x", "feat-b"}
    verdicts = [
        {"node_id": "sys-a", "verdict": "keep", "reason": "central"},
        {"node_id": "con-x", "verdict": "reject", "reason": "hors sujet"},
        {"node_id": "sys-GHOST", "verdict": "reject", "reason": "?"},
        # feat-b missing → keep (recall-first: the LLM must argue to remove)
    ]
    keeps, rejects, dropped = gate_triage(verdicts, submitted)
    assert keeps == {"sys-a": "central", "feat-b": ""}
    assert rejects == {"con-x": "hors sujet"}
    assert dropped == ["sys-GHOST"]


def test_gate_triage_malformed_verdict_is_dropped_not_fatal():
    keeps, rejects, dropped = gate_triage(
        [{"node_id": "sys-a"}, {"verdict": "keep"}], {"sys-a"}
    )
    assert "sys-a" in keeps  # missing verdict → default keep
    assert dropped == [""]  # the id-less entry


# -- pull --------------------------------------------------------------------

def test_pull_brings_back_governance_neighbors_of_keeps(service):
    pulled = pull_governance(service, kept_ids={"sys-a"}, rejected_ids=set(), cap=10)
    pulled_ids = {p.node_id for p in pulled}
    assert {"con-x", "dec-y", "risk-z"} <= pulled_ids
    assert all(p.via_id == "sys-a" for p in pulled)
    assert all(p.edge_type for p in pulled)


def test_pull_excludes_rejected_and_already_kept_and_respects_cap(service):
    pulled = pull_governance(service, kept_ids={"sys-a", "con-x"},
                             rejected_ids={"dec-y"}, cap=1)
    pulled_ids = {p.node_id for p in pulled}
    assert "con-x" not in pulled_ids  # already kept
    assert "dec-y" not in pulled_ids  # explicitly rejected by the LLM
    assert len(pulled) <= 1  # cap


def test_render_node_set_only_includes_submitted_nodes_and_internal_edges(service):
    rendered = render_node_set({"sys-a", "con-x"}, service)

    assert "sys-a" in rendered
    assert "con-x" in rendered
    assert "con-x —CONSTRAINS→ sys-a" in rendered
    assert "dec-y" not in rendered
    assert "risk-z" not in rendered


# -- gate B -------------------------------------------------------------------

def test_gate_claims_filters_ids_sections_and_domains(service):
    payload = {
        "pulled_justifications": [{"node_id": "con-x", "reason": "s'applique"}],
        "claims": [
            {"kind": "constraint_applies", "node_ids": ["con-x"],
             "target_section": "contraintes", "reason": "ok"},
            {"kind": "depends_on", "node_ids": ["sys-GHOST"],
             "target_section": "dependances", "reason": "ghost"},
            {"kind": "risk", "node_ids": ["risk-z"],
             "target_section": "budget", "reason": "bad section"},
        ],
        "domains": ["monetique", "not-a-domain"],
        "challenge_statement": "Le défi.",
    }
    valid, rejected = gate_claims(payload, map_ids={"sys-a", "con-x", "risk-z"},
                                  service=service)
    assert [c["target_section"] for c in valid] == ["contraintes"]
    assert len(rejected) == 2
    assert all(r["reason_rejected"] for r in rejected)


def test_gate_claims_rejects_a_reasonless_claim(service):
    # A claim with no justification is ungrounded for display/EDB — reject it visibly
    # rather than crash the session (a real Grok output omitted "reason").
    payload = {"claims": [
        {"kind": "risk", "node_ids": ["risk-z"], "target_section": "risques"},
    ]}
    valid, rejected = gate_claims(payload, map_ids={"risk-z"}, service=service)
    assert valid == []
    assert rejected[0]["reason_rejected"] == "raison manquante"


def test_gate_claims_filters_domains_against_vocabulary(service):
    assert gate_domains(["monetique", "fake-domain"], service) == ["monetique"]


def test_known_domains_is_the_in_use_vocabulary(service):
    assert service.known_domains() == frozenset({"monetique"})


# -- claim provenance (fidelity) ----------------------------------------------

def test_node_provenance_returns_authoritative_text_and_drops_unknown(service):
    prov = node_provenance(service, ["dec-y", "con-x", "sys-GHOST"])
    assert [p["node_id"] for p in prov] == ["dec-y", "con-x"]  # ghost id dropped
    dec = prov[0]
    assert dec["label"] == "Décision Y"
    assert dec["type"] == "decision"
    assert dec["text"] == "Gel des évolutions."  # verbatim from the node, not the LLM


def test_statement_fact_flags_catches_unsourced_numbers():
    sources = ["gel à compter du 15 janvier 2026", "une part significative des dossiers KYC"]
    flags = statement_fact_flags("Environ 30% des KYC sont périmés ; gel en 2026.", sources)
    assert "30" in flags        # fabricated figure, absent from every source
    assert "2026" not in flags  # present in a source — not flagged
    assert "15" not in flags    # present in a source — not flagged


def test_statement_fact_flags_clean_when_all_numbers_sourced():
    assert statement_fact_flags("Le gel court depuis 2026.", ["gel à compter de 2026"]) == []
