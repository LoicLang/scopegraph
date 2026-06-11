"""Node documents and the ChromaDB vector index with content-hash staleness."""

import hashlib
from pathlib import Path

import chromadb
from chromadb.config import Settings

from core.graph.models import Node
from core.graph.service import GraphService
from core.retrieval.embedder import Embedder

_COLLECTION = "scopegraph-nodes"
_SETTINGS = Settings(anonymized_telemetry=False)  # hermetic: no network, ever


def node_document(node: Node) -> str:
    """The text embedded per node: label + aliases + body (choice A1, W2 spec §1)."""
    label = getattr(node, "name", "") or getattr(node, "title", "")
    aliases = ", ".join(getattr(node, "aliases", []))
    body = getattr(node, "description", "") or getattr(node, "statement", "")
    return " — ".join(part for part in (label, aliases, body) if part)


def graph_fingerprint(graph_dir: Path) -> str:
    """Stable content hash of every YAML under graph_dir (staleness check)."""
    digest = hashlib.sha256()
    for path in sorted(graph_dir.rglob("*.yaml")):
        digest.update(path.relative_to(graph_dir).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class VectorIndex:
    """Cosine-space Chroma index over node documents.

    Embeddings are ALWAYS supplied explicitly (add and query) so Chroma's default
    embedding function — which downloads a model — is never instantiated.
    """

    def __init__(self, embedder: Embedder, persist_dir: Path | None = None) -> None:
        self._embedder = embedder
        self._client = (
            chromadb.PersistentClient(path=str(persist_dir), settings=_SETTINGS)
            if persist_dir is not None
            else chromadb.EphemeralClient(settings=_SETTINGS)
        )
        self._collection: chromadb.Collection | None = None

    def build(self, service: GraphService, fingerprint: str = "") -> bool:
        """(Re)index all nodes unless the stored fingerprint matches. True if indexed."""
        names = [getattr(c, "name", c) for c in self._client.list_collections()]
        if _COLLECTION in names:
            existing = self._client.get_collection(_COLLECTION)
            if fingerprint and (existing.metadata or {}).get("fingerprint") == fingerprint:
                self._collection = existing
                return False
            self._client.delete_collection(_COLLECTION)
        self._collection = self._client.create_collection(
            _COLLECTION,
            metadata={"hnsw:space": "cosine", "fingerprint": fingerprint or "unversioned"},
        )
        nodes = service.all_nodes()
        documents = [node_document(node) for node in nodes]
        self._collection.add(
            ids=[node.id for node in nodes],
            embeddings=self._embedder.embed(documents),
            documents=documents,
            metadatas=[{"type": node.type, "domains": " ".join(node.domains)} for node in nodes],
        )
        return True

    def query(self, text: str, n: int) -> list[tuple[str, float]]:
        """Top-n (node_id, cosine similarity), best first."""
        if self._collection is None:
            raise RuntimeError("VectorIndex.query called before build()")
        [vector] = self._embedder.embed([text])
        response = self._collection.query(
            query_embeddings=[vector], n_results=min(n, self._collection.count())
        )
        ids, distances = response["ids"][0], response["distances"][0]
        return [(node_id, 1.0 - distance) for node_id, distance in zip(ids, distances)]
