from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
