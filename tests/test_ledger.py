"""Propose/validate ledger: pending cards the user accepts, edits, or rejects."""

import pytest

from core.runtime.ledger import Ledger, Proposal


def _claim(node_ids=("sys-a",), section="dependances"):
    return Proposal.claim(
        kind="depends_on", node_ids=list(node_ids), target_section=section,
        reason="dépend du moteur",
    )


def test_proposals_get_sequential_ids_and_pending_status():
    ledger = Ledger()
    pid = ledger.add(_claim())
    assert pid == "p1"
    assert ledger.get(pid).status == "pending"
    assert ledger.add(_claim()) == "p2"


def test_accept_with_optional_edit():
    ledger = Ledger()
    pid = ledger.add(Proposal.field(section_id="objectifs", text="Réduire le délai"))
    accepted = ledger.accept(pid, edited_text="Réduire le délai à 2 jours")
    assert accepted.status == "accepted"
    assert accepted.text == "Réduire le délai à 2 jours"


def test_reject_keeps_the_proposal_visible():
    ledger = Ledger()
    pid = ledger.add(_claim())
    ledger.reject(pid)
    assert ledger.get(pid).status == "rejected"
    assert [p.id for p in ledger.pending()] == []


def test_double_decision_fails_loud():
    ledger = Ledger()
    pid = ledger.add(_claim())
    ledger.accept(pid)
    with pytest.raises(ValueError, match="already decided"):
        ledger.reject(pid)


def test_round_trip():
    ledger = Ledger()
    ledger.add(_claim())
    clone = Ledger.from_dict(ledger.to_dict())
    assert clone.get("p1").kind == "claim"
    assert clone.get("p1").payload["target_section"] == "dependances"


def test_statement_proposal_carries_flags_and_issues():
    from core.runtime.ledger import Ledger, Proposal
    ledger = Ledger()
    pid = ledger.add(Proposal.statement(
        text="Le gel court jusqu'au 15 janvier 2026.",
        flags=["30"], issues=["Date inversée."]))
    p = ledger.get(pid)
    assert p.kind == "statement"
    assert p.payload["flags"] == ["30"]
    assert p.payload["issues"] == ["Date inversée."]
