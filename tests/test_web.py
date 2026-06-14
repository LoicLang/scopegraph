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


def test_maybe_cache_wraps_only_when_env_set(tmp_path, monkeypatch) -> None:
    from core.llm.caching import CachingProvider
    from core.llm.provider import MockProvider
    from web.app import _maybe_cache

    inner = MockProvider([])
    monkeypatch.delenv("SCOPEGRAPH_CACHE_DIR", raising=False)
    assert _maybe_cache(inner) is inner
    assert _maybe_cache(None) is None
    monkeypatch.setenv("SCOPEGRAPH_CACHE_DIR", str(tmp_path))
    assert isinstance(_maybe_cache(inner), CachingProvider)


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
    # queue: enrich(no additions) · extract(opener mined, empty) · pick_question(valid gap choice)
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
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
    # queue: enrich · extract(opener mined, empty) · triage(keep all) · claims(one valid claim)
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [
            {"kind": "constraint_applies", "node_ids": ["con-mini"],
             "target_section": "dependances", "reason": "la règle s'applique"}],
         "domains": [], "challenge_statement": "Défi."},
        {"verdicts": [{"index": 0, "grounded": True, "reason_fr": ""}]},  # #3: claim grounded
        {"challenge_statement": "Défi."},
        {"issues": []},  # fidelity judge
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    pid = out["cards"][0]["id"]
    out = client.post(f"/api/session/{session_id}/proposal/{pid}",
                      json={"decision": "accept"}).json()
    assert out["edb"]["dependances"]


def test_claim_cards_carry_node_provenance(tmp_path: Path) -> None:
    # Fidelity: each claim card ships the authoritative text of its cited nodes, so the
    # user verifies the LLM's paraphrase against the seed (the runtime is the source of truth).
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [
            {"kind": "constraint_applies", "node_ids": ["con-mini"],
             "target_section": "contraintes", "reason": "la règle s'applique au cash-back"}],
         "domains": [], "challenge_statement": "Défi."},
        {"verdicts": [{"index": 0, "grounded": True, "reason_fr": ""}]},  # #3: claim grounded
        {"challenge_statement": "Défi."},
        {"issues": []},  # fidelity judge
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    claim = next(c for c in out["cards"] if c["kind"] == "claim")
    assert claim["provenance"][0]["node_id"] == "con-mini"
    assert claim["provenance"][0]["text"] == "Contrainte locale."  # verbatim from the node


def test_statement_flags_in_payload(tmp_path: Path) -> None:
    # P2: unsourced numbers in the challenge statement surface in the payload for the UI.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "30% des dossiers sont concernés."},
        {"challenge_statement": "30% des dossiers sont concernés."},
        {"issues": []},  # fidelity judge
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    assert "30" in out["statement_flags"]


def test_enrichment_removal_endpoint_reruns_retrieval(tmp_path: Path) -> None:
    # queue: enrich(1 chip) · triage · claims · re-run pick (NO re-enrich — lever 3:
    # removing a chip adds no user words, so the round reruns without a new enrichment)
    provider = MockProvider([
        {"additions": [{"text": "fidélité", "kind": "synonym"}]},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi."},
        {"challenge_statement": "Défi."},
        {"issues": []},  # fidelity judge
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
    # queue: enrich · extract(opener mined, empty) · triage(reject con-mini) · claims(empty)
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": [{"node_id": "con-mini", "verdict": "reject", "reason": "hors sujet"}]},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi."},
        {"challenge_statement": "Défi."},
        {"issues": []},  # fidelity judge
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


# -- Task 2: payload uses kept_node_ids(); new post-challenge nodes get "nouveau" ----


def test_payload_map_uses_kept_node_ids_and_honors_exclusions(tmp_path: Path) -> None:
    # After triage rejects con-mini, the map must not contain it — proving kept_node_ids()
    # (which respects rejected_nodes) drives the only= set in _session_payload.
    # queue: enrich · extract(opener mined, empty) · triage(reject con-mini) · claims(empty)
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too
        {"verdicts": [{"node_id": "con-mini", "verdict": "reject", "reason": "hors sujet"}]},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi."},
        {"challenge_statement": "Défi."},
        {"issues": []},  # fidelity judge
    ])
    client = mini_client(tmp_path, provider)
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "refonte du canal"}).json()
    # (a) payload renders
    assert "map" in out and "nodes" in out["map"]
    # (b) kept_node_ids() drives only= — rejected node must be absent
    map_ids = {node["id"] for node in out["map"]["nodes"]}
    assert "con-mini" not in map_ids
    assert "sys-mini" in map_ids


def test_annotations_marks_new_nodes_as_nouveau_after_challenge(tmp_path: Path) -> None:
    # (c) Three invariants, all tested with specific node ids (sys-mini / con-mini):
    #   1. kept - previously_mapped - restored → provenance="nouveau"
    #   2. previously_mapped node → NOT marked "nouveau"
    #   3. restored node → keeps "restauré par l'utilisateur", NOT relabeled "nouveau"
    from web.app import _annotations
    from core.runtime.session import ScopingSession
    from core.retrieval.index import VectorIndex
    from core.graph.service import GraphService

    graph_dir = make_mini_graph(tmp_path)
    service = GraphService.from_dir(graph_dir)
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)

    session = ScopingSession(service, index)
    # Do one real turn so last_result is set
    session.handle_message("refonte du canal")
    result = session.last_result
    assert result is not None

    kept = session.kept_node_ids()
    assert kept  # sanity: there are nodes on the map
    assert "sys-mini" in kept and "con-mini" in kept

    session.challenge_done = True

    # --- Invariant 1 & 2: one previously-mapped node, one genuinely new node ---
    session.previously_mapped = {"sys-mini"}
    session.restored = set()
    ann = _annotations(session, result, kept)
    # con-mini: in kept, not in previously_mapped, not in restored → "nouveau"
    assert ann["con-mini"].get("provenance") == "nouveau", (
        f"con-mini should be 'nouveau' but got {ann.get('con-mini')}"
    )
    # sys-mini: in previously_mapped → must NOT be marked "nouveau"
    assert ann.get("sys-mini", {}).get("provenance") != "nouveau", (
        "sys-mini is previously_mapped and should not be 'nouveau'"
    )

    # --- Invariant 3: restored node must keep its provenance, not be relabeled ---
    session.previously_mapped = set()
    session.restored = {"con-mini"}
    # Seed the restored annotation so _annotations can merge it
    ann2 = _annotations(session, result, kept)
    # con-mini is restored: the restored loop writes "restauré par l'utilisateur"
    # and the new-node loop must NOT overwrite it
    assert ann2["con-mini"].get("provenance") == "restauré par l'utilisateur", (
        f"restored node should keep its provenance but got {ann2.get('con-mini')}"
    )
    # sys-mini: in kept, not previously_mapped, not restored → "nouveau"
    assert ann2["sys-mini"].get("provenance") == "nouveau", (
        f"sys-mini should be 'nouveau' but got {ann2.get('sys-mini')}"
    )


# -- Task 12: statement card payload carries flags/issues ----------------------


def test_card_dict_serializes_statement_flags_and_issues() -> None:
    """_card_dict must forward payload.flags and payload.issues for a statement card
    so the UI can surface the amber fidelity strip on the quarantined statement."""
    from web.app import _card_dict
    from core.runtime.ledger import Proposal
    from tests.test_session import make_service

    p = Proposal.statement(
        text="Le gel court jusqu'au 15 janvier 2026.",
        flags=["30"],
        issues=["Date inversée : « jusqu'au » au lieu de « à compter du »."],
    )
    p.id = "p1"
    out = _card_dict(make_service(), p)
    assert out["kind"] == "statement"
    assert out["payload"]["flags"] == ["30"]
    assert out["payload"]["issues"] == [
        "Date inversée : « jusqu'au » au lieu de « à compter du »."
    ]
