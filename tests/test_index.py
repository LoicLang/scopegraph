import datetime
from pathlib import Path

from core.graph.models import Decision, System
from core.retrieval.index import graph_fingerprint, node_document


def test_node_document_includes_name_aliases_description() -> None:
    system = System(
        id="sys-x",
        name="Moteur d'autorisation carte",
        aliases=["MONAUT"],
        description="Autorise les transactions carte en temps réel.",
        owner_team="Monétique",
        domains=["monetique"],
    )
    doc = node_document(system)
    assert "Moteur d'autorisation carte" in doc
    assert "MONAUT" in doc
    assert "Autorise les transactions" in doc


def test_node_document_uses_title_and_statement_for_decisions() -> None:
    decision = Decision(
        id="dec-x",
        title="Scoring unique",
        statement="Un seul moteur de scoring est autorisé.",
        rationale="Cohérence des décisions risque.",
        date=datetime.date(2024, 1, 1),
        decided_by="Comité d'architecture",
        domains=["lcb-ft"],
    )
    doc = node_document(decision)
    assert "Scoring unique" in doc
    assert "Un seul moteur de scoring" in doc


def test_graph_fingerprint_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "nodes").mkdir()
    (tmp_path / "nodes" / "a.yaml").write_text("id: a\n")
    (tmp_path / "edges.yaml").write_text("edges: []\n")
    first = graph_fingerprint(tmp_path)
    assert first == graph_fingerprint(tmp_path)  # stable
    (tmp_path / "nodes" / "a.yaml").write_text("id: a\nname: changed\n")
    assert graph_fingerprint(tmp_path) != first
