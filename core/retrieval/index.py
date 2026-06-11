"""Node documents and the ChromaDB vector index with content-hash staleness."""

import hashlib
from pathlib import Path

from core.graph.models import Node


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
