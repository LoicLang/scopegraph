"""FastAPI app: chat pane + live Context Map + EDB pane (W2/W3 screens).

Run locally (real embedder + LLM, requires the embeddings/llm extras):
    SCOPEGRAPH_LLM_PROVIDER=mistral uvicorn --factory web.app:create_app --reload
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.graph.service import GraphService
from core.llm.factory import make_provider
from core.llm.provider import LLMProvider
from core.runtime.challenge import node_provenance
from core.retrieval.embedder import Embedder
from core.retrieval.index import VectorIndex, embedder_id, graph_fingerprint
from core.retrieval.retriever import RetrievalResult
from core.runtime.session import ScopingSession
from core.viz.payload import build_payload

_ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = _ROOT / "graph"
STATIC_DIR = _ROOT / "web" / "static"
CHROMA_DIR = _ROOT / ".chroma"


class MessageIn(BaseModel):
    text: str = Field(min_length=1)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")
    edited_text: str | None = None


def _annotations(session: ScopingSession, result: RetrievalResult) -> dict[str, dict]:
    annotations: dict[str, dict] = {}
    for scored in result.anchors:
        annotations[scored.node_id] = {"role": "anchor", "score": round(scored.score, 3)}
    for scored in result.expanded:
        annotations[scored.node_id] = {
            "role": "expanded",
            "score": round(scored.score, 3),
            "via": scored.anchor_id,
            "hops": len(scored.path),
        }
    for pulled in session.pulled:
        annotations[pulled.node_id] = {
            "role": "pulled", "via": pulled.via_id, "edge": pulled.edge_type,
        }
    for node_id in session.restored:
        annotations[node_id] = {
            **annotations.get(node_id, {}), "provenance": "restauré par l'utilisateur",
        }
    return annotations


def _card_dict(service: GraphService, proposal) -> dict:
    """Serialize a ledger proposal, hydrating claims with their cited nodes' real text."""
    ids = proposal.payload.get("node_ids") or proposal.payload.get("node_refs") or []
    return {
        "id": proposal.id, "kind": proposal.kind, "text": proposal.text,
        "payload": proposal.payload, "status": proposal.status,
        "provenance": node_provenance(service, ids),
    }


def _session_payload(
    service: GraphService,
    session: ScopingSession,
    *,
    message: str | None = None,
    cards_filter: list | None = None,
) -> dict:
    result = session.last_result
    assert result is not None, "payload requires at least one completed round"
    kept = (set(result.node_ids()) | {p.node_id for p in session.pulled}) - set(
        session.rejected_nodes
    )
    payload = build_payload(
        service,
        only=kept,
        annotations=_annotations(session, result),
        highlight={s.node_id for s in result.anchors} - set(session.rejected_nodes),
    )
    return {
        "state": session.state,
        "question": session.pending_question,
        "message": message,
        "map": payload,
        "brief": session.brief.model_dump() if session.brief else None,
        "edb": session.edb.to_dict(),
        "missing_sections": session.edb.missing_sections(),
        "cards": [
            _card_dict(service, p)
            for p in (cards_filter if cards_filter is not None else session.ledger.pending())
        ],
        "rejected_nodes": session.rejected_nodes,
        "gate_rejections": session.gate_rejections,
        "statement_flags": session.statement_flags,
        "pulled": [
            {"id": p.node_id, "via": p.via_id, "edge_type": p.edge_type}
            for p in session.pulled
        ],
        "proposed_domains": session.proposed_domains,
    }


def create_app(
    graph_dir: Path = GRAPH_DIR,
    embedder: Embedder | None = None,
    persist_dir: Path | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    service = GraphService.from_dir(graph_dir)
    if embedder is None:  # real embedder only outside tests
        from core.retrieval.st_embedder import SentenceTransformersEmbedder

        embedder = SentenceTransformersEmbedder()
        persist_dir = persist_dir or CHROMA_DIR
    index = VectorIndex(embedder, persist_dir=persist_dir)
    index.build(service, f"{graph_fingerprint(graph_dir)}:{embedder_id(embedder)}")
    if provider is None:  # uvicorn picks up SCOPEGRAPH_LLM_PROVIDER (default: none)
        provider = make_provider()

    app = FastAPI(title="scopegraph")
    sessions: dict[str, ScopingSession] = {}

    def _get_session(session_id: str) -> ScopingSession:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session inconnue")
        return session

    @app.post("/api/session")
    def create_session() -> dict:
        session_id = uuid.uuid4().hex
        sessions[session_id] = ScopingSession(service, index, provider=provider)
        return {"session_id": session_id, "state": sessions[session_id].state}

    @app.post("/api/session/{session_id}/message")
    def post_message(session_id: str, message: MessageIn) -> dict:
        session = _get_session(session_id)
        try:
            turn = session.handle_message(message.text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _session_payload(service, session, message=turn.message)

    @app.post("/api/session/{session_id}/proposal/{pid}")
    def decide_proposal(session_id: str, pid: str, decision: DecisionIn) -> dict:
        session = _get_session(session_id)
        try:
            if decision.decision == "accept":
                session.accept_proposal(pid, decision.edited_text)
            else:
                session.reject_proposal(pid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="proposition inconnue") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _session_payload(service, session)

    @app.delete("/api/session/{session_id}/enrichment/{index}")
    def remove_enrichment(session_id: str, index: int) -> dict:
        session = _get_session(session_id)
        try:
            turn = session.remove_enrichment(index)
        except IndexError as exc:
            raise HTTPException(status_code=404, detail="enrichissement inconnu") from exc
        return _session_payload(service, session, message=turn.message)

    @app.post("/api/session/{session_id}/restore/{node_id}")
    def restore_node(session_id: str, node_id: str) -> dict:
        session = _get_session(session_id)
        session.restore_node(node_id)
        return _session_payload(service, session)

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
