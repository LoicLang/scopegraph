"""FastAPI app: chat pane + live Context Map (W2 first screens).

Run locally (real embedder, requires the embeddings extra):
    uvicorn --factory web.app:create_app --reload
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.graph.service import GraphService
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


def _annotations(result: RetrievalResult) -> dict[str, dict]:
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
    return annotations


def create_app(
    graph_dir: Path = GRAPH_DIR,
    embedder: Embedder | None = None,
    persist_dir: Path | None = None,
) -> FastAPI:
    service = GraphService.from_dir(graph_dir)
    if embedder is None:  # real embedder only outside tests
        from core.retrieval.st_embedder import SentenceTransformersEmbedder

        embedder = SentenceTransformersEmbedder()
        persist_dir = persist_dir or CHROMA_DIR
    index = VectorIndex(embedder, persist_dir=persist_dir)
    index.build(service, f"{graph_fingerprint(graph_dir)}:{embedder_id(embedder)}")

    app = FastAPI(title="scopegraph")
    sessions: dict[str, ScopingSession] = {}

    @app.post("/api/session")
    def create_session() -> dict:
        session_id = uuid.uuid4().hex
        sessions[session_id] = ScopingSession(service, index)
        return {"session_id": session_id, "state": sessions[session_id].state}

    @app.post("/api/session/{session_id}/message")
    def post_message(session_id: str, message: MessageIn) -> dict:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session inconnue")
        try:
            turn = session.handle_message(message.text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = build_payload(
            service,
            only=set(turn.result.node_ids()),
            annotations=_annotations(turn.result),
            highlight={scored.node_id for scored in turn.result.anchors},
        )
        return {
            "state": turn.state,
            "question": turn.question,
            "map": payload,
            "brief": turn.brief.model_dump(),
        }

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
