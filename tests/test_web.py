from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.llm.provider import MockProvider
from core.retrieval.embedder import FakeEmbedder
from web.app import create_app

GRAPH_DIR = Path(__file__).resolve().parent.parent / "graph"


@pytest.fixture()
def client() -> TestClient:
    app = create_app(
        graph_dir=GRAPH_DIR, embedder=FakeEmbedder(["application mobile", "crédit"])
    )
    return TestClient(app)


def create_session(client: TestClient) -> str:
    response = client.post("/api/session")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "DESCRIBING"
    return body["session_id"]


def test_create_session(client: TestClient) -> None:
    create_session(client)


def test_describe_returns_map_and_state(client: TestClient) -> None:
    session_id = create_session(client)
    response = client.post(
        f"/api/session/{session_id}/message",
        json={"text": "Paiement en 3 fois dans l'application mobile (crédit conso)."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "MAPPING"
    ids = {node["id"] for node in body["map"]["nodes"]}
    assert "sys-app-mobile" in ids
    roles = {node["id"]: node.get("role") for node in body["map"]["nodes"]}
    assert roles["sys-app-mobile"] == "anchor"
    assert body["brief"]["description"].startswith("Paiement en 3 fois")


def test_unknown_session_is_404(client: TestClient) -> None:
    response = client.post("/api/session/nope/message", json={"text": "bonjour"})
    assert response.status_code == 404


def test_blank_text_is_422(client: TestClient) -> None:
    session_id = create_session(client)
    assert (
        client.post(f"/api/session/{session_id}/message", json={"text": ""}).status_code == 422
    )
    assert (
        client.post(f"/api/session/{session_id}/message", json={"text": "   "}).status_code
        == 422
    )


def test_home_serves_the_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "scopegraph" in response.text


# -- W3: provider-driven payloads, proposals, chips, restore -------------------


def make_mini_graph(tmp_path: Path) -> Path:
    """One system + one constraint, same domain → no graph trigger, challenge on turn 1."""
    graph = tmp_path / "graph"
    (graph / "nodes").mkdir(parents=True)
    (graph / "domains.yaml").write_text("domains:\n  - banque-en-ligne\n")
    (graph / "nodes" / "sys-mini.yaml").write_text(
        "type: system\nid: sys-mini\nname: Canal mini\n"
        "description: Canal client minimal.\nowner_team: T\ndomains: [banque-en-ligne]\n"
    )
    (graph / "nodes" / "con-mini.yaml").write_text(
        "type: constraint\nid: con-mini\ntitle: Règle mini\nstatement: Contrainte locale.\n"
        "source: PCI\nseverity: high\ndomains: [banque-en-ligne]\n"
    )
    (graph / "edges.yaml").write_text(
        "edges:\n  - {source_id: con-mini, target_id: sys-mini, type: CONSTRAINS}\n"
    )
    return graph


def mini_client(tmp_path: Path, provider: MockProvider) -> TestClient:
    app = create_app(graph_dir=make_mini_graph(tmp_path),
                     embedder=FakeEmbedder(["canal"]), provider=provider)
    return TestClient(app)


def test_message_response_carries_edb_cards_and_rejections() -> None:
    # queue: enrich(no additions) · pick_question(valid gap choice)
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "gap:objectifs", "question": "Quel succès ?"},
    ])
    client = TestClient(create_app(graph_dir=GRAPH_DIR,
                                   embedder=FakeEmbedder(["application mobile"]),
                                   provider=provider))
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "projet dans l'application mobile"}).json()
    assert "edb" in out and out["edb"]["besoin"] == []
    assert "cards" in out and "enrichments" in out["brief"]
    assert "rejected_nodes" in out and "gate_rejections" in out
    assert "missing_sections" in out


def test_proposal_accept_endpoint_applies_to_edb(tmp_path: Path) -> None:
    # queue: enrich · triage(keep all) · claims(one valid claim)
    provider = MockProvider([
        {"additions": []},
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [
            {"kind": "constraint_applies", "node_ids": ["con-mini"],
             "target_section": "dependances", "reason": "la règle s'applique"}],
         "domains": [], "challenge_statement": "Défi."},
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    pid = out["cards"][0]["id"]
    out = client.post(f"/api/session/{session_id}/proposal/{pid}",
                      json={"decision": "accept"}).json()
    assert out["edb"]["dependances"]


def test_enrichment_removal_endpoint_reruns_retrieval(tmp_path: Path) -> None:
    # queue: enrich(1 chip) · triage · claims · re-run pick (NO re-enrich — lever 3:
    # removing a chip adds no user words, so the round reruns without a new enrichment)
    provider = MockProvider([
        {"additions": [{"text": "fidélité", "kind": "synonym"}]},
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi."},
        {"candidate_key": "gap:contexte", "question": "Quel contexte ?"},
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    assert out["brief"]["enrichments"] == ["fidélité"]
    out = client.delete(f"/api/session/{session_id}/enrichment/0").json()
    assert out["brief"]["enrichments"] == []


def test_node_restore_endpoint_moves_rejected_back_to_map(tmp_path: Path) -> None:
    # queue: enrich · triage(reject con-mini) · claims(empty)
    provider = MockProvider([
        {"additions": []},
        {"verdicts": [{"node_id": "con-mini", "verdict": "reject", "reason": "hors sujet"}]},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi."},
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    assert out["rejected_nodes"] == {"con-mini": "hors sujet"}
    map_ids = {node["id"] for node in out["map"]["nodes"]}
    assert "con-mini" not in map_ids
    out = client.post(f"/api/session/{session_id}/restore/con-mini").json()
    assert "con-mini" not in out["rejected_nodes"]
    map_ids = {node["id"] for node in out["map"]["nodes"]}
    assert "con-mini" in map_ids
