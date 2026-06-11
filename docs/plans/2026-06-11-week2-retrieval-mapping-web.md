---
summary: W2 implementation plan — embeddings+Chroma, hybrid scorer, MAPPING loop, first web screens (18 TDD tasks)
read_when:
  - executing the W2 chantier
  - resuming W2 work mid-way (checkboxes track progress)
---

# Week 2 — Retrieval, MAPPING loop, first web screens — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the W2 design spec (`docs/specs/2026-06-10-week2-retrieval-mapping-web-design.md`): a free-text project brief is embedded, scored against the 72-node graph (semantic + domain boost + 1–2 hop expansion with provenance), the deterministic MAPPING loop asks template questions until the map is stable, and a FastAPI+Alpine page shows the chat and the live Context Map.

**Architecture:** New packages `core/retrieval/` (Embedder Protocol, Chroma index, hybrid scorer) and `core/runtime/` (ProjectBrief, triggers, questions, ScopingSession); `core/viz/payload.py` gains `only`/`annotations` params (the planned seam extension); `web/app.py` serves the single page. Everything hermetic in CI via `FakeEmbedder` + ephemeral Chroma; the real model runs only in `scripts/retrieval-smoke`.

**Tech Stack:** Python 3.12, Pydantic v2, ChromaDB, sentence-transformers (optional extra, lazy import), FastAPI + Alpine.js + Cytoscape (CDN), pytest.

**Branch:** `w2-retrieval-web` (create from `main` at Task 1).

**Conventions that bind every task:** ruff line length 100 · type hints everywhere · English code/docstrings, French user-facing strings · hermetic tests (no network, no API key, no model download — Chroma telemetry disabled) · conventional commit prefixes.

---

## Task 1: Branch, dependencies, package skeletons, config

**Files:**
- Modify: `pyproject.toml`
- Create: `core/retrieval/__init__.py` (empty), `core/runtime/__init__.py` (empty), `web/__init__.py` (empty)
- Create: `core/retrieval/config.py`
- Modify: `.gitignore` (add `.chroma/`)

- [ ] **Step 1: Create the branch**

```bash
git checkout -b w2-retrieval-web main
```

- [ ] **Step 2: Add dependencies**

In `pyproject.toml`, change the `dependencies` and `optional-dependencies` sections to:

```toml
dependencies = [
    "pydantic>=2",
    "pyyaml",
    "fastapi",
    "uvicorn",
    "chromadb",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",
    "pre-commit",
    "httpx",
]
embeddings = [
    "sentence-transformers",
]
```

(`httpx` is required by FastAPI's `TestClient`; `embeddings` is NEVER installed in CI.)

- [ ] **Step 3: Install**

Run: `pip install -e ".[dev]"`
Expected: installs chromadb and httpx without error. Verify: `python -c "import chromadb, httpx; print('ok')"` prints `ok`.

- [ ] **Step 4: Create skeletons and config**

Create empty `core/retrieval/__init__.py`, `core/runtime/__init__.py`, `web/__init__.py`.

Create `core/retrieval/config.py`:

```python
"""Retrieval & MAPPING knobs (W2 design spec §3).

Calibrated with scripts/retrieval-smoke against the eval cases — never by intuition.
"""

EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

TOP_N = 20  # semantic candidates pulled from the vector index
TOP_K = 8  # max anchors
ALPHA = 0.15  # score boost per shared domain between brief and node
TAU_ANCHOR = 0.35  # min boosted score to count as an anchor
TAU_KEEP = 0.20  # min score for an expanded node to be kept
TAU_WEAK = 0.45  # best anchor below this → T1 (vague brief)
TAU_NOISE = 0.25  # semantic sim below this → node counts as expansion-only (T3)
DELTA = 0.15  # relative margin: top-2 domain scores closer than this → T2
DOMAIN_FRACTION = 0.5  # derived domains = candidate score ≥ fraction · top score
MAX_HOPS = 2  # expansion radius from anchors
DECAY = 0.7  # expanded score = anchor score · DECAY^hops
MAX_QUESTIONS = 5  # hard cap of questions per session
```

Append `.chroma/` on its own line to `.gitignore`.

- [ ] **Step 5: Verify and commit**

Run: `ruff check . && pytest -q`
Expected: all existing tests still pass.

```bash
git add pyproject.toml core/retrieval core/runtime web/__init__.py .gitignore
git commit -m "chore: W2 scaffolding — chromadb dep, retrieval/runtime packages, config knobs"
```

---

## Task 2: Embedder Protocol + FakeEmbedder

**Files:**
- Create: `core/retrieval/embedder.py`
- Test: `tests/test_embedder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_embedder.py`:

```python
import math

import pytest

from core.retrieval.embedder import DIM, FakeEmbedder


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_vectors_are_unit_norm() -> None:
    emb = FakeEmbedder(["app mobile"])
    for vector in emb.embed(["projet dans l'app mobile", "texte sans fragment"]):
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)
        assert len(vector) == DIM


def test_shared_fragment_gives_high_similarity() -> None:
    emb = FakeEmbedder(["app mobile"])
    [a, b, c] = emb.embed(
        ["projet dans l'App Mobile", "Application — app mobile bancaire", "moteur de crédit"]
    )
    assert cosine(a, b) == pytest.approx(1.0)
    assert cosine(a, c) == pytest.approx(0.0)  # fragment axes and hash axes are disjoint


def test_two_fragments_give_partial_overlap() -> None:
    emb = FakeEmbedder(["app mobile", "crédit"])
    [both, one] = emb.embed(["app mobile et crédit", "le crédit conso"])
    assert cosine(both, one) == pytest.approx(1 / math.sqrt(2))


def test_unknown_texts_are_deterministic_and_distinct() -> None:
    emb = FakeEmbedder()
    [v1] = emb.embed(["texte inconnu"])
    [v2] = emb.embed(["texte inconnu"])
    [v3] = emb.embed(["autre texte"])
    assert v1 == v2
    assert v1 != v3


def test_too_many_fragments_rejected() -> None:
    with pytest.raises(ValueError, match="at most"):
        FakeEmbedder([f"frag-{i}" for i in range(DIM)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embedder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.retrieval.embedder'`

- [ ] **Step 3: Implement**

Create `core/retrieval/embedder.py`:

```python
"""Embedder Protocol and the test-rigged FakeEmbedder (hermetic tests, no model)."""

import hashlib
import math
from typing import Protocol

DIM = 32
_HASH_OFFSET = DIM // 2  # hash vectors live in the upper half, fragments in the lower


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic embedder rigged by fragments.

    Texts sharing a registered fragment (case-insensitive substring) get overlapping
    one-hot components → high cosine similarity. Texts matching no fragment get a
    stable signed hash vector on disjoint axes → ~zero similarity with everything.
    """

    def __init__(self, fragments: list[str] | None = None) -> None:
        self._fragments = {f.lower(): i for i, f in enumerate(fragments or [])}
        if len(self._fragments) > _HASH_OFFSET:
            raise ValueError(f"FakeEmbedder supports at most {_HASH_OFFSET} fragments")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        lowered = text.lower()
        vector = [0.0] * DIM
        matched = False
        for fragment, axis in self._fragments.items():
            if fragment in lowered:
                vector[axis] = 1.0
                matched = True
        if not matched:
            digest = hashlib.sha256(lowered.encode()).digest()
            for i in range(_HASH_OFFSET, DIM):
                vector[i] = (digest[i - _HASH_OFFSET] - 127.5) / 127.5
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embedder.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/embedder.py tests/test_embedder.py
git commit -m "feat: Embedder Protocol + rig-able FakeEmbedder for hermetic retrieval tests"
```

---

## Task 3: Node documents + graph fingerprint

**Files:**
- Create: `core/retrieval/index.py` (documents + fingerprint only; VectorIndex comes in Task 4)
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.retrieval.index'`

- [ ] **Step 3: Implement**

Create `core/retrieval/index.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/index.py tests/test_index.py
git commit -m "feat: node documents (A1: label+aliases+body) and graph content fingerprint"
```

---

## Task 4: VectorIndex — build and query (ephemeral)

**Files:**
- Modify: `core/retrieval/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_index.py`:

```python
from core.graph.models import Edge, EdgeType, Feature  # noqa: F401  (Edge/EdgeType used in Task 5+)
from core.graph.service import GraphService
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex


def _mini_service() -> GraphService:
    nodes = [
        System(
            id="sys-gestion-beneficiaires",
            name="Gestion des bénéficiaires",
            description="Référentiel des bénéficiaires de virement.",
            owner_team="Référentiels",
            domains=["referentiel-client"],
        ),
        System(
            id="sys-moteur-credit",
            name="Moteur de crédit",
            description="Octroi et gestion des crédits.",
            owner_team="Crédit",
            domains=["credit"],
        ),
        System(
            id="sys-core-banking",
            name="Core banking",
            description="Tenue de compte centrale.",
            owner_team="SI",
            domains=["socle-si"],
        ),
    ]
    return GraphService({n.id: n for n in nodes}, [])


def test_query_ranks_matching_document_first() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder(["bénéficiaire"]))
    index.build(service)
    results = index.query("ajout d'un bénéficiaire depuis le portail", n=3)
    assert results[0][0] == "sys-gestion-beneficiaires"
    assert results[0][1] > 0.9
    assert len(results) == 3


def test_query_n_is_bounded_by_corpus_size() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder())
    index.build(service)
    assert len(index.query("n'importe quoi", n=50)) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index.py -q`
Expected: FAIL — `ImportError: cannot import name 'VectorIndex'`

- [ ] **Step 3: Implement**

Append to `core/retrieval/index.py` (and add the new imports at the top):

```python
import chromadb
from chromadb.config import Settings

from core.graph.service import GraphService
from core.retrieval.embedder import Embedder

_COLLECTION = "scopegraph-nodes"
_SETTINGS = Settings(anonymized_telemetry=False)  # hermetic: no network, ever


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/index.py tests/test_index.py
git commit -m "feat: VectorIndex — Chroma cosine index over node documents, explicit embeddings only"
```

---

## Task 5: VectorIndex — persistence and staleness

**Files:**
- Test: `tests/test_index.py` (implementation from Task 4 should already satisfy this — these tests prove it)

- [ ] **Step 1: Write the tests**

Append to `tests/test_index.py`:

```python
def test_persistent_index_skips_rebuild_when_fingerprint_matches(tmp_path: Path) -> None:
    service = _mini_service()
    embedder = FakeEmbedder(["bénéficiaire"])

    first = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert first.build(service, fingerprint="fp-1") is True

    second = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert second.build(service, fingerprint="fp-1") is False  # reused, not rebuilt
    assert second.query("bénéficiaire", n=1)[0][0] == "sys-gestion-beneficiaires"


def test_persistent_index_rebuilds_when_fingerprint_changes(tmp_path: Path) -> None:
    service = _mini_service()
    embedder = FakeEmbedder(["bénéficiaire"])
    VectorIndex(embedder, persist_dir=tmp_path / "chroma").build(service, fingerprint="fp-1")

    stale = VectorIndex(embedder, persist_dir=tmp_path / "chroma")
    assert stale.build(service, fingerprint="fp-2") is True  # content changed → rebuilt


def test_ephemeral_index_always_rebuilds() -> None:
    service = _mini_service()
    index = VectorIndex(FakeEmbedder())
    assert index.build(service, fingerprint="fp-1") is True
    assert index.build(service, fingerprint="fp-1") is False  # same client instance reuses
```

Note the third test: within one ephemeral client instance a matching fingerprint also
reuses — that is fine and intended (the W2 web app builds once at startup).

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_index.py -q`
Expected: 8 passed (Task 4's implementation already covers persistence). If any fail,
fix `build()` — do not weaken the tests.

- [ ] **Step 3: Commit**

```bash
git add tests/test_index.py
git commit -m "test: VectorIndex staleness — reuse on matching fingerprint, rebuild on change"
```

---

## Task 6: SentenceTransformersEmbedder (lazy, optional)

**Files:**
- Create: `core/retrieval/st_embedder.py`
- Test: `tests/test_embedder.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embedder.py`:

```python
import sys


def test_importing_st_module_does_not_import_sentence_transformers() -> None:
    import core.retrieval.st_embedder  # noqa: F401

    assert "sentence_transformers" not in sys.modules


def test_missing_package_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.retrieval.st_embedder import SentenceTransformersEmbedder

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        SentenceTransformersEmbedder()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embedder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.retrieval.st_embedder'`

- [ ] **Step 3: Implement**

Create `core/retrieval/st_embedder.py`:

```python
"""The real embedder. Only module allowed to import sentence_transformers — lazily."""

from core.retrieval.config import EMBED_MODEL


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str = EMBED_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # clear startup error (W2 spec: error handling)
            raise RuntimeError(
                "sentence-transformers is not installed — run: pip install -e '.[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        rows = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embedder.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/st_embedder.py tests/test_embedder.py
git commit -m "feat: SentenceTransformersEmbedder — lazy import, clear error when extra missing"
```

---

## Task 7: Hybrid scorer — semantic + domain boost + anchors + domain derivation

**Files:**
- Create: `core/retrieval/retriever.py`
- Test: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retriever.py`:

```python
import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import retrieve


def make_service() -> GraphService:
    nodes = [
        System(
            id="sys-canal",
            name="Canal mobile",
            description="Canal client mobile.",
            owner_team="T",
            domains=["banque-en-ligne"],
        ),
        System(
            id="sys-moteur",
            name="Moteur central",
            description="Traitement central des opérations.",
            owner_team="T",
            domains=["monetique"],
        ),
        System(
            id="sys-terminal",
            name="Terminal magasin",
            description="Acceptation en magasin.",
            owner_team="T",
            domains=["tpe-acceptation"],
        ),
        Constraint(
            id="con-regle",
            title="Règle PCI",
            statement="Cloisonnement réseau requis.",
            source="PCI DSS",
            severity="high",
            domains=["monetique"],
        ),
    ]
    edges = [
        Edge(source_id="sys-canal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-terminal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="con-regle", target_id="sys-moteur", type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def make_index(fragments: list[str]) -> tuple[GraphService, VectorIndex]:
    service = make_service()
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return service, index


def anchor_score(result, node_id: str) -> float:
    return next(s.score for s in result.anchors if s.node_id == node_id)


def test_anchors_require_threshold_and_carry_similarity() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    assert [s.node_id for s in result.anchors] == ["sys-canal"]
    assert result.anchors[0].semantic_sim == pytest.approx(1.0)
    assert result.anchors[0].domains == ("banque-en-ligne",)


def test_no_anchor_when_nothing_matches() -> None:
    service, index = make_index(["canal"])
    result = retrieve("sujet totalement étranger", service, index)
    assert result.anchors == []
    assert result.derived_domains == []


def test_domain_boost_adds_alpha_per_shared_domain() -> None:
    service, index = make_index(["canal", "central"])
    plain = retrieve("le canal et le traitement central", service, index)
    boosted = retrieve(
        "le canal et le traitement central", service, index, domains=["monetique"]
    )
    expected = anchor_score(plain, "sys-moteur") + config.ALPHA
    assert anchor_score(boosted, "sys-moteur") == pytest.approx(expected)
    assert boosted.anchors[0].node_id == "sys-moteur"  # boost reorders the tie


def test_domain_scores_and_derivation() -> None:
    service, index = make_index(["canal", "central"])
    result = retrieve("le canal et le traitement central", service, index)
    assert set(result.domain_scores) == {"banque-en-ligne", "monetique"}
    # equal anchor scores → both domains derived (≥ DOMAIN_FRACTION · top)
    assert set(result.derived_domains) == {"banque-en-ligne", "monetique"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retriever.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.retrieval.retriever'`

- [ ] **Step 3: Implement**

Create `core/retrieval/retriever.py` (expansion arrives in Task 8 — `retrieve` returns
empty `expanded` for now):

```python
"""Hybrid scorer: semantic + domain boost + bounded graph expansion with provenance."""

from collections.abc import Sequence
from dataclasses import dataclass

from core.graph.models import Edge
from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.index import VectorIndex


@dataclass(frozen=True)
class ScoredNode:
    node_id: str
    score: float
    domains: tuple[str, ...] = ()
    semantic_sim: float | None = None
    anchor_id: str | None = None
    path: tuple[Edge, ...] = ()

    @property
    def expansion_only(self) -> bool:
        """Reached structurally, near-invisible textually (T3 material)."""
        return bool(self.path) and (self.semantic_sim or 0.0) < config.TAU_NOISE


@dataclass
class RetrievalResult:
    anchors: list[ScoredNode]  # sorted by score, best first
    expanded: list[ScoredNode]  # sorted by score, best first
    domain_scores: dict[str, float]
    derived_domains: list[str]

    def node_ids(self) -> list[str]:
        return [scored.node_id for scored in [*self.anchors, *self.expanded]]


def retrieve(
    text: str,
    service: GraphService,
    index: VectorIndex,
    *,
    domains: Sequence[str] = (),
    excluded_domains: Sequence[str] = (),
) -> RetrievalResult:
    sims = dict(index.query(text, config.TOP_N))
    wanted = set(domains)
    boosted = {
        node_id: sim + config.ALPHA * len(set(service.get_node(node_id).domains) & wanted)
        for node_id, sim in sims.items()
    }
    anchor_ids = [
        node_id
        for node_id, score in sorted(boosted.items(), key=lambda kv: (-kv[1], kv[0]))
        if score >= config.TAU_ANCHOR
    ][: config.TOP_K]
    anchors = [
        ScoredNode(
            node_id=node_id,
            score=boosted[node_id],
            domains=tuple(service.get_node(node_id).domains),
            semantic_sim=sims[node_id],
        )
        for node_id in anchor_ids
    ]

    domain_scores: dict[str, float] = {}
    for anchor in anchors:
        for domain in anchor.domains:
            domain_scores[domain] = domain_scores.get(domain, 0.0) + anchor.score
    top = max(domain_scores.values(), default=0.0)
    derived = sorted(
        (d for d, s in domain_scores.items() if s >= config.DOMAIN_FRACTION * top),
        key=lambda d: (-domain_scores[d], d),
    )

    expanded = _expand(anchors, service, sims, set(excluded_domains))
    return RetrievalResult(anchors, expanded, domain_scores, derived)


def _expand(
    anchors: list[ScoredNode],
    service: GraphService,
    sims: dict[str, float],
    excluded: set[str],
) -> list[ScoredNode]:
    return []  # Task 8
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retriever.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/retriever.py tests/test_retriever.py
git commit -m "feat: hybrid scorer stage 1-3 — semantic, domain boost, anchors, domain derivation"
```

---

## Task 8: Hybrid scorer — expansion with provenance, decay, exclusions

**Files:**
- Modify: `core/retrieval/retriever.py` (`_expand`)
- Test: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retriever.py`:

```python
def test_expansion_carries_provenance_and_decay() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    by_id = {s.node_id: s for s in result.expanded}

    moteur = by_id["sys-moteur"]
    assert moteur.score == pytest.approx(config.DECAY)  # anchor score 1.0 · DECAY^1
    assert moteur.anchor_id == "sys-canal"
    assert [edge.type for edge in moteur.path] == [EdgeType.DEPENDS_ON]

    terminal = by_id["sys-terminal"]
    assert terminal.score == pytest.approx(config.DECAY**2)
    assert len(terminal.path) == 2
    assert terminal.expansion_only  # zero textual similarity, pure structure

    assert "con-regle" in by_id  # constraints ride the same expansion


def test_expansion_skips_anchors_and_sorts_by_score() -> None:
    service, index = make_index(["canal"])
    result = retrieve("améliorer notre canal mobile", service, index)
    expanded_ids = [s.node_id for s in result.expanded]
    assert "sys-canal" not in expanded_ids
    scores = [s.score for s in result.expanded]
    assert scores == sorted(scores, reverse=True)


def test_excluded_domains_drop_expanded_nodes() -> None:
    service, index = make_index(["canal"])
    result = retrieve(
        "améliorer notre canal mobile", service, index, excluded_domains=["tpe-acceptation"]
    )
    expanded_ids = {s.node_id for s in result.expanded}
    assert "sys-terminal" not in expanded_ids
    assert "sys-moteur" in expanded_ids  # other domains untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retriever.py -q`
Expected: 3 new tests FAIL (`_expand` returns `[]`), 4 previous pass.

- [ ] **Step 3: Implement**

Replace `_expand` in `core/retrieval/retriever.py`:

```python
def _expand(
    anchors: list[ScoredNode],
    service: GraphService,
    sims: dict[str, float],
    excluded: set[str],
) -> list[ScoredNode]:
    anchor_ids = {anchor.node_id for anchor in anchors}
    best: dict[str, ScoredNode] = {}
    for anchor in anchors:  # strongest first → ties resolve to the strongest anchor
        for node_id, path in service.k_hop(anchor.node_id, config.MAX_HOPS).items():
            if node_id in anchor_ids:
                continue
            node = service.get_node(node_id)
            if set(node.domains) & excluded:
                continue
            score = anchor.score * config.DECAY ** len(path)
            if score < config.TAU_KEEP:
                continue
            if node_id not in best or score > best[node_id].score:
                best[node_id] = ScoredNode(
                    node_id=node_id,
                    score=score,
                    domains=tuple(node.domains),
                    semantic_sim=sims.get(node_id),
                    anchor_id=anchor.node_id,
                    path=tuple(path),
                )
    return sorted(best.values(), key=lambda scored: (-scored.score, scored.node_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retriever.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/retriever.py tests/test_retriever.py
git commit -m "feat: scorer expansion — k_hop from anchors, decay, edge-path provenance, exclusions"
```

---

## Task 9: Eval cases 1 & 2 as mechanical tests on the real seed

These tests load the actual `graph/` seed (local YAML — hermetic) and rig the embedder so
the brief anchors where real semantics would anchor. Case 1 proves the load-bearing wall:
a node with ZERO textual similarity (TPE) is surfaced through a 2-hop edge path. If a test
fails, fix the scorer or the §3 constants — never the assertion.

**Files:**
- Test: `tests/test_retrieval_eval_cases.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_retrieval_eval_cases.py`:

```python
from pathlib import Path

from core.graph.models import EdgeType
from core.graph.service import GraphService
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import retrieve

SEED = Path(__file__).resolve().parent.parent / "graph"


def seed_retrieve(fragments: list[str], brief: str):
    service = GraphService.from_dir(SEED)
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return retrieve(brief, service, index), service


def test_eval_case_1_bnpl_reaches_tpe_in_two_hops() -> None:
    """BNPL mobile (eval case 1): sys-logiciel-tpe has no textual link to the brief —
    only the chain sys-app-mobile → DEPENDS_ON → sys-moteur-autorisation ← DEPENDS_ON ←
    sys-logiciel-tpe can surface it."""
    result, _ = seed_retrieve(
        ["application mobile", "crédit"],
        "Ajouter une option de paiement en 3 fois dans l'application mobile (crédit conso).",
    )
    assert result.anchors[0].node_id == "sys-app-mobile"  # matches both fragments

    by_id = {s.node_id: s for s in result.expanded}
    assert "sys-logiciel-tpe" in by_id, "the 2-hop monétique chain must surface the TPE"
    tpe = by_id["sys-logiciel-tpe"]
    assert tpe.anchor_id == "sys-app-mobile"
    assert len(tpe.path) == 2
    assert all(edge.type is EdgeType.DEPENDS_ON for edge in tpe.path)
    touched = {edge.source_id for edge in tpe.path} | {edge.target_id for edge in tpe.path}
    assert "sys-moteur-autorisation" in touched
    assert tpe.expansion_only  # zero similarity: pure structure — the naive-LLM trap


def test_eval_case_2_beneficiary_context_surfaces() -> None:
    """Bénéficiaires entreprise (eval case 2): the shared rules and the cancelled
    project must be in the retrieved context (anchored or expanded)."""
    result, _ = seed_retrieve(
        ["bénéficiaire"],
        "Permettre aux clients entreprise de créer des bénéficiaires depuis leur portail.",
    )
    ids = set(result.node_ids())
    for expected in (
        "con-carence-beneficiaire-48h",
        "con-sca-ajout-beneficiaire",
        "con-verif-sanctions-creation",
        "dec-ecriture-via-api-benef",
        "proj-refonte-parcours-beneficiaire",
    ):
        assert expected in ids, f"{expected} missing from retrieved context"
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_retrieval_eval_cases.py -q`
Expected: 2 passed. If case 1 fails on `TAU_KEEP` (TPE score = 1.0·0.7² = 0.49 ≥ 0.20, so
it should pass), or case 2 misses a node (check it is within `MAX_HOPS` of an anchor —
the constraints are 1 hop from `obj-beneficiaire`), debug the scorer with
`pytest ... -q -x --tb=long`. Adjust constants only with a comment explaining why.

- [ ] **Step 3: Commit**

```bash
git add tests/test_retrieval_eval_cases.py
git commit -m "test: eval cases 1-2 mechanical — TPE 2-hop chain and beneficiary inheritance"
```

---

## Task 10: ProjectBrief

**Files:**
- Create: `core/runtime/brief.py`
- Test: `tests/test_brief.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brief.py`:

```python
from core.runtime.brief import QA, ProjectBrief


def test_text_concatenates_description_and_qa() -> None:
    brief = ProjectBrief(description="Paiement en 3 fois dans l'app mobile.")
    brief.qa.append(QA(question="Le périmètre inclut-il « monetique » ?", answer="oui"))
    text = brief.text()
    assert "Paiement en 3 fois" in text
    assert "monetique" in text  # the question's vocabulary enriches the query
    assert "oui" in text


def test_defaults_are_empty() -> None:
    brief = ProjectBrief(description="x")
    assert brief.qa == []
    assert brief.domains == []
    assert brief.excluded_domains == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brief.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.runtime.brief'`

- [ ] **Step 3: Implement**

Create `core/runtime/brief.py`:

```python
"""ProjectBrief: the accumulated, structured semantic query (never raw chat history).

Both question and answer text enter text(): the question carries the graph vocabulary
(domain, node name), so a confirmed pivot becomes a direct semantic anchor next round
— the loop converts hops into anchors (W2 spec §4).
"""

from pydantic import BaseModel, Field


class QA(BaseModel):
    question: str
    answer: str


class ProjectBrief(BaseModel):
    description: str
    qa: list[QA] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # user-confirmed only
    excluded_domains: list[str] = Field(default_factory=list)

    def text(self) -> str:
        parts = [self.description, *(f"{item.question} {item.answer}" for item in self.qa)]
        return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brief.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add core/runtime/brief.py tests/test_brief.py
git commit -m "feat: ProjectBrief — the accumulating semantic query with user-confirmed domains"
```

---

## Task 11: Deterministic triggers

**Files:**
- Create: `core/runtime/triggers.py`
- Test: `tests/test_triggers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triggers.py`:

```python
from core.graph.models import Edge, EdgeType
from core.retrieval.retriever import RetrievalResult, ScoredNode
from core.runtime.brief import ProjectBrief
from core.runtime.triggers import (
    DomainTieTrigger,
    PivotTrigger,
    WeakBriefTrigger,
    detect_trigger,
)

EDGE = Edge(source_id="sys-a", target_id="sys-b", type=EdgeType.DEPENDS_ON)


def make_result(anchors=(), expanded=(), domain_scores=None, derived=()) -> RetrievalResult:
    return RetrievalResult(
        anchors=list(anchors),
        expanded=list(expanded),
        domain_scores=dict(domain_scores or {}),
        derived_domains=list(derived),
    )


def strong_anchor() -> ScoredNode:
    return ScoredNode("sys-a", 0.9, domains=("credit",), semantic_sim=0.9)


def test_weak_brief_fires_when_best_anchor_low() -> None:
    result = make_result(anchors=[ScoredNode("sys-a", 0.3, semantic_sim=0.3)])
    trigger = detect_trigger(result, ProjectBrief(description="x"), asked=set())
    assert isinstance(trigger, WeakBriefTrigger)


def test_weak_brief_fires_when_no_anchor_and_respects_asked_log() -> None:
    result = make_result()
    assert isinstance(detect_trigger(result, ProjectBrief(description="x"), set()), WeakBriefTrigger)
    assert detect_trigger(result, ProjectBrief(description="x"), asked={"weak"}) is None


def test_domain_tie_fires_within_relative_delta() -> None:
    result = make_result(
        anchors=[strong_anchor()],
        domain_scores={"credit": 1.0, "monetique": 0.9},
        derived=["credit", "monetique"],
    )
    trigger = detect_trigger(result, ProjectBrief(description="x"), set())
    assert trigger == DomainTieTrigger(domain_a="credit", domain_b="monetique")
    assert detect_trigger(result, ProjectBrief(description="x"), {trigger.key}) is None


def test_no_tie_when_gap_is_wide() -> None:
    result = make_result(
        anchors=[strong_anchor()], domain_scores={"credit": 1.0, "monetique": 0.5},
        derived=["credit"],
    )
    assert detect_trigger(result, ProjectBrief(description="x"), set()) is None


def pivot_node() -> ScoredNode:
    return ScoredNode(
        "sys-terminal", 0.49, domains=("tpe-acceptation",), semantic_sim=0.0,
        anchor_id="sys-a", path=(EDGE, EDGE),
    )


def test_pivot_fires_for_expansion_only_foreign_domain() -> None:
    result = make_result(
        anchors=[strong_anchor()], expanded=[pivot_node()],
        domain_scores={"credit": 1.0}, derived=["credit"],
    )
    trigger = detect_trigger(result, ProjectBrief(description="x"), set())
    assert trigger == PivotTrigger(domain="tpe-acceptation", node_id="sys-terminal")


def test_pivot_skips_known_excluded_and_asked_domains() -> None:
    result = make_result(
        anchors=[strong_anchor()], expanded=[pivot_node()],
        domain_scores={"credit": 1.0}, derived=["credit"],
    )
    known = ProjectBrief(description="x", domains=["tpe-acceptation"])
    assert detect_trigger(result, known, set()) is None
    excluded = ProjectBrief(description="x", excluded_domains=["tpe-acceptation"])
    assert detect_trigger(result, excluded, set()) is None
    assert detect_trigger(result, ProjectBrief(description="x"), {"pivot:tpe-acceptation"}) is None


def test_precedence_weak_then_tie_then_pivot() -> None:
    result = make_result(
        anchors=[ScoredNode("sys-a", 0.3, domains=("credit",), semantic_sim=0.3)],
        expanded=[pivot_node()],
        domain_scores={"credit": 0.3, "monetique": 0.28},
        derived=["credit", "monetique"],
    )
    brief = ProjectBrief(description="x")
    assert isinstance(detect_trigger(result, brief, set()), WeakBriefTrigger)
    assert isinstance(detect_trigger(result, brief, {"weak"}), DomainTieTrigger)
    tie_key = DomainTieTrigger(domain_a="credit", domain_b="monetique").key
    assert isinstance(detect_trigger(result, brief, {"weak", tie_key}), PivotTrigger)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_triggers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.runtime.triggers'`

- [ ] **Step 3: Implement**

Create `core/runtime/triggers.py`:

```python
"""Deterministic ambiguity triggers (W2 spec §4). The runtime decides — never the LLM."""

from dataclasses import dataclass

from core.retrieval import config
from core.retrieval.retriever import RetrievalResult
from core.runtime.brief import ProjectBrief


@dataclass(frozen=True)
class WeakBriefTrigger:
    @property
    def key(self) -> str:
        return "weak"


@dataclass(frozen=True)
class DomainTieTrigger:
    domain_a: str
    domain_b: str

    @property
    def key(self) -> str:
        return "tie:" + ":".join(sorted((self.domain_a, self.domain_b)))


@dataclass(frozen=True)
class PivotTrigger:
    domain: str
    node_id: str

    @property
    def key(self) -> str:
        return f"pivot:{self.domain}"  # one question per domain, not per node


Trigger = WeakBriefTrigger | DomainTieTrigger | PivotTrigger


def detect_trigger(
    result: RetrievalResult, brief: ProjectBrief, asked: set[str]
) -> Trigger | None:
    """First firing trigger in T1 → T2 → T3 order, skipping already-asked keys."""
    best = result.anchors[0].score if result.anchors else 0.0
    if best < config.TAU_WEAK:
        trigger = WeakBriefTrigger()
        if trigger.key not in asked:
            return trigger

    ranked = sorted(result.domain_scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) >= 2:
        (domain_a, score_a), (domain_b, score_b) = ranked[0], ranked[1]
        if score_a - score_b < config.DELTA * score_a:
            trigger = DomainTieTrigger(domain_a=domain_a, domain_b=domain_b)
            if trigger.key not in asked:
                return trigger

    known = set(brief.domains) | set(result.derived_domains) | set(brief.excluded_domains)
    for scored in result.expanded:  # already sorted best-first
        if not scored.expansion_only:
            continue
        for domain in scored.domains:
            if domain in known:
                continue
            trigger = PivotTrigger(domain=domain, node_id=scored.node_id)
            if trigger.key not in asked:
                return trigger
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_triggers.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/runtime/triggers.py tests/test_triggers.py
git commit -m "feat: deterministic ambiguity triggers T1/T2/T3 with asked-log and precedence"
```

---

## Task 12: French question templates

**Files:**
- Create: `core/runtime/questions.py`
- Test: `tests/test_questions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_questions.py`:

```python
from core.graph.models import System
from core.graph.service import GraphService
from core.runtime.questions import WEAK_QUESTION, render_question
from core.runtime.triggers import DomainTieTrigger, PivotTrigger, WeakBriefTrigger


def make_service() -> GraphService:
    node = System(
        id="sys-logiciel-tpe",
        name="Logiciel d'acceptation TPE",
        description="Acceptation en magasin.",
        owner_team="Monétique",
        domains=["tpe-acceptation"],
    )
    return GraphService({node.id: node}, [])


def test_weak_template() -> None:
    assert render_question(WeakBriefTrigger(), make_service()) == WEAK_QUESTION
    assert "préciser" in WEAK_QUESTION


def test_tie_template() -> None:
    question = render_question(
        DomainTieTrigger(domain_a="credit", domain_b="monetique"), make_service()
    )
    assert question == "Le projet relève-t-il plutôt de « credit » ou de « monetique » ?"


def test_pivot_template_uses_node_label() -> None:
    question = render_question(
        PivotTrigger(domain="tpe-acceptation", node_id="sys-logiciel-tpe"), make_service()
    )
    assert question == (
        "Le périmètre inclut-il « tpe-acceptation » ? "
        "(Logiciel d'acceptation TPE serait alors concerné)"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_questions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.runtime.questions'`

- [ ] **Step 3: Implement**

Create `core/runtime/questions.py`:

```python
"""French question templates — assembled from graph content, never generated (W2 spec §1).

W3 will add LLM rephrasing on top; these templates remain the permanent fallback.
"""

from core.graph.service import GraphService
from core.runtime.triggers import DomainTieTrigger, PivotTrigger, Trigger, WeakBriefTrigger

WEAK_QUESTION = (
    "Votre description est courte — pouvez-vous préciser le canal concerné "
    "et l'objet métier manipulé ?"
)


def render_question(trigger: Trigger, service: GraphService) -> str:
    match trigger:
        case WeakBriefTrigger():
            return WEAK_QUESTION
        case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
            return f"Le projet relève-t-il plutôt de « {domain_a} » ou de « {domain_b} » ?"
        case PivotTrigger(domain=domain, node_id=node_id):
            node = service.get_node(node_id)
            label = getattr(node, "name", "") or getattr(node, "title", "")
            return f"Le périmètre inclut-il « {domain} » ? ({label} serait alors concerné)"
    raise TypeError(f"unknown trigger type: {trigger!r}")  # pragma: no cover
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_questions.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add core/runtime/questions.py tests/test_questions.py
git commit -m "feat: French question templates for the three MAPPING triggers"
```

---

## Task 13: ScopingSession — the MAPPING loop

**Files:**
- Create: `core/runtime/session.py`
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session.py` (reuses the Task 7 synthetic graph shape):

```python
import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.runtime.questions import WEAK_QUESTION
from core.runtime.session import ScopingSession, SessionState


def make_service() -> GraphService:
    nodes = [
        System(
            id="sys-canal", name="Canal mobile", description="Canal client mobile.",
            owner_team="T", domains=["banque-en-ligne"],
        ),
        System(
            id="sys-moteur", name="Moteur central",
            description="Traitement central des opérations.",
            owner_team="T", domains=["monetique"],
        ),
        System(
            id="sys-terminal", name="Terminal magasin", description="Acceptation en magasin.",
            owner_team="T", domains=["tpe-acceptation"],
        ),
        Constraint(
            id="con-regle", title="Règle PCI", statement="Cloisonnement réseau requis.",
            source="PCI DSS", severity="high", domains=["monetique"],
        ),
    ]
    edges = [
        Edge(source_id="sys-canal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-terminal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="con-regle", target_id="sys-moteur", type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def make_session(fragments: list[str]) -> ScopingSession:
    service = make_service()
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return ScopingSession(service, index)


def test_describe_moves_to_mapping_and_asks_pivot_questions() -> None:
    session = make_session(["canal"])
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.state is SessionState.MAPPING
    # strongest expansion-only foreign-domain node is sys-moteur (1 hop, monetique)
    assert turn.question is not None
    assert "monetique" in turn.question


def test_answer_non_excludes_domain_and_loop_converges() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")
    turn = session.handle_message("non")  # monetique out of scope
    kept = set(turn.result.node_ids())
    assert "sys-moteur" not in kept
    assert "con-regle" not in kept
    # next pivot: tpe-acceptation (sys-terminal)
    assert turn.question is not None and "tpe-acceptation" in turn.question
    final = session.handle_message("non")
    assert final.question is None  # no trigger left → map stable
    assert "sys-terminal" not in set(final.result.node_ids())


def test_answer_oui_confirms_domain_and_keeps_nodes() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")
    turn = session.handle_message("oui")
    assert "monetique" in session.brief.domains
    assert "sys-moteur" in set(turn.result.node_ids())


def test_weak_brief_asks_generic_question_first() -> None:
    session = make_session(["canal"])
    turn = session.handle_message("améliorer des choses")  # matches nothing
    assert turn.question == WEAK_QUESTION
    follow_up = session.handle_message("c'est pour le canal mobile")
    assert follow_up.question != WEAK_QUESTION  # T1 never re-fires
    assert {s.node_id for s in follow_up.result.anchors} == {"sys-canal"}


def test_question_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_QUESTIONS", 1)
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")  # question 1 (monetique)
    turn = session.handle_message("non")
    assert turn.question is None  # tpe pivot exists but the cap stops the interview


def test_empty_message_rejected_and_future_states_guarded() -> None:
    session = make_session(["canal"])
    with pytest.raises(ValueError):
        session.handle_message("   ")
    session.handle_message("améliorer notre canal mobile")
    session.state = SessionState.CHALLENGING
    with pytest.raises(NotImplementedError):
        session.handle_message("peu importe")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.runtime.session'`

- [ ] **Step 3: Implement**

Create `core/runtime/session.py`:

```python
"""ScopingSession: the deterministic state machine. W2 implements DESCRIBING → MAPPING;
CHALLENGING and beyond arrive with W3/W4 (MVP spec §3)."""

from dataclasses import dataclass
from enum import StrEnum

from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import RetrievalResult, retrieve
from core.runtime.brief import QA, ProjectBrief
from core.runtime.questions import render_question
from core.runtime.triggers import (
    DomainTieTrigger,
    PivotTrigger,
    Trigger,
    WeakBriefTrigger,
    detect_trigger,
)


class SessionState(StrEnum):
    DESCRIBING = "DESCRIBING"
    MAPPING = "MAPPING"
    CHALLENGING = "CHALLENGING"
    SCOPING = "SCOPING"
    DRAFTING = "DRAFTING"
    VALIDATED = "VALIDATED"


@dataclass
class Turn:
    state: SessionState
    question: str | None
    result: RetrievalResult
    brief: ProjectBrief


class ScopingSession:
    def __init__(self, service: GraphService, index: VectorIndex) -> None:
        self._service = service
        self._index = index
        self.state = SessionState.DESCRIBING
        self.brief: ProjectBrief | None = None
        self.asked: set[str] = set()
        self.questions_asked = 0
        self.pending: Trigger | None = None

    def handle_message(self, text: str) -> Turn:
        text = text.strip()
        if not text:
            raise ValueError("empty message")
        if self.state is SessionState.DESCRIBING:
            self.brief = ProjectBrief(description=text)
            self.state = SessionState.MAPPING
        elif self.state is SessionState.MAPPING:
            if self.pending is not None:
                self._apply_answer(self.pending, text)
                self.pending = None
            else:  # detail volunteered after stability: enrich and re-run
                self.brief.qa.append(QA(question="(précision)", answer=text))
        else:
            raise NotImplementedError(f"state {self.state} arrives with W3/W4")
        return self._map_round()

    def _apply_answer(self, trigger: Trigger, answer: str) -> None:
        assert self.brief is not None
        self.brief.qa.append(
            QA(question=render_question(trigger, self._service), answer=answer)
        )
        match trigger:
            case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
                lowered = answer.lower()
                for domain in (domain_a, domain_b):
                    if domain.lower() in lowered and domain not in self.brief.domains:
                        self.brief.domains.append(domain)
            case PivotTrigger(domain=domain):
                verdict = _parse_yes_no(answer)
                if verdict is True and domain not in self.brief.domains:
                    self.brief.domains.append(domain)
                elif verdict is False and domain not in self.brief.excluded_domains:
                    self.brief.excluded_domains.append(domain)
                # unparseable → the QA text alone enriches the brief; never re-asked
            case WeakBriefTrigger():
                pass  # the answer text itself enriches the brief

    def _map_round(self) -> Turn:
        assert self.brief is not None
        result = retrieve(
            self.brief.text(),
            self._service,
            self._index,
            domains=self.brief.domains,
            excluded_domains=self.brief.excluded_domains,
        )
        question: str | None = None
        if self.questions_asked < config.MAX_QUESTIONS:
            trigger = detect_trigger(result, self.brief, self.asked)
            if trigger is not None:
                self.asked.add(trigger.key)
                self.questions_asked += 1
                self.pending = trigger
                question = render_question(trigger, self._service)
        return Turn(state=self.state, question=question, result=result, brief=self.brief)


def _parse_yes_no(answer: str) -> bool | None:
    tokens = {token.strip(".,!?;:()«»\"'").lower() for token in answer.split()}
    if tokens & {"oui", "yes"}:
        return True
    if tokens & {"non", "no"}:
        return False
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -q`
Expected: 6 passed. The first test's expected pivot (`monetique` before `tpe-acceptation`)
holds because expanded nodes are sorted by score and `sys-moteur` is 1 hop vs 2.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/session.py tests/test_session.py
git commit -m "feat: ScopingSession — deterministic MAPPING loop with cap and convergence"
```

---

## Task 14: Viz payload seam extension — `only` and `annotations`

**Files:**
- Modify: `core/viz/payload.py`
- Test: `tests/test_viz_payload.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_viz_payload.py` (the file already has a module-scoped `service`
fixture over the real seed — these tests reuse it):

```python
def test_only_keeps_subset_and_their_edges(service):
    payload = build_payload(service, only={"sys-gestion-beneficiaires", "feat-benef-ajout"})
    ids = {node["id"] for node in payload["nodes"]}
    assert ids == {"sys-gestion-beneficiaires", "feat-benef-ajout"}
    for edge in payload["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_annotations_merge_into_node_payload(service):
    payload = build_payload(
        service,
        only={"sys-gestion-beneficiaires"},
        annotations={"sys-gestion-beneficiaires": {"role": "anchor", "score": 0.91}},
    )
    [node] = payload["nodes"]
    assert node["role"] == "anchor"
    assert node["score"] == 0.91
    assert node["label"]  # base payload fields still present
```

(Do not create a second fixture — `service` is the existing module-scoped one.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_viz_payload.py -q`
Expected: FAIL — `TypeError: build_payload() got an unexpected keyword argument 'only'`

- [ ] **Step 3: Implement**

In `core/viz/payload.py`, extend the signature and body of `build_payload`:

```python
def build_payload(
    service: GraphService,
    *,
    focus: str | None = None,
    k: int = 2,
    domains: set[str] | None = None,
    types: set[str] | None = None,
    highlight: set[str] | None = None,
    only: set[str] | None = None,
    annotations: dict[str, dict] | None = None,
) -> dict:
```

After the existing `types` filter block, add:

```python
    if only is not None:
        kept &= only
```

And change the node list construction to merge annotations:

```python
        "nodes": [
            {**_node_payload(nodes[nid]), **(annotations or {}).get(nid, {})}
            for nid in sorted(kept)
        ],
```

Update the docstring's filter sentence to mention `only` (composes by intersection like
the others) and `annotations` (display-only extras merged into node payloads).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_viz_payload.py -q`
Expected: all pass (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add core/viz/payload.py tests/test_viz_payload.py
git commit -m "feat: viz payload — only-subset filter and per-node annotations for the Context Map"
```

---

## Task 15: FastAPI app — session endpoints

**Files:**
- Create: `web/app.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.app'`

- [ ] **Step 3: Implement**

Create `web/app.py`:

```python
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
from core.retrieval.index import VectorIndex, graph_fingerprint
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
    index.build(service, graph_fingerprint(graph_dir))

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add web/app.py tests/test_web.py
git commit -m "feat: FastAPI session endpoints — map payload rides the message response (C1)"
```

---

## Task 16: The page — chat pane + live Context Map

**Files:**
- Create: `web/static/index.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_home_serves_the_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "scopegraph" in response.text
```

Run: `pytest tests/test_web.py::test_home_serves_the_page -q`
Expected: FAIL — 500/`RuntimeError` (file does not exist).

- [ ] **Step 2: Create the page**

Create `web/static/index.html`:

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>scopegraph</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3/dist/cytoscape.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #f6f7f9; color: #1c2733; }
  main { display: grid; grid-template-columns: minmax(320px, 2fr) 3fr; height: 100vh; }
  #chat { display: flex; flex-direction: column; border-right: 1px solid #d8dee5; background: #fff; }
  #chat h1 { font-size: 1.1rem; margin: 0; padding: 14px 18px; border-bottom: 1px solid #d8dee5; }
  #messages { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; }
  .bot, .user { max-width: 85%; padding: 8px 12px; border-radius: 10px; line-height: 1.35; }
  .bot { background: #eef2f6; align-self: flex-start; }
  .user { background: #1d6fd1; color: #fff; align-self: flex-end; }
  form { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid #d8dee5; }
  input { flex: 1; padding: 9px 12px; border: 1px solid #c4ccd4; border-radius: 8px; font-size: 0.95rem; }
  button { padding: 9px 16px; border: 0; border-radius: 8px; background: #1d6fd1; color: #fff; cursor: pointer; }
  #mappane { position: relative; }
  #cy { position: absolute; inset: 0; }
  #detail { position: absolute; left: 12px; bottom: 12px; right: 12px; background: #ffffffe6;
            border: 1px solid #d8dee5; border-radius: 8px; padding: 8px 12px; font-size: 0.85rem;
            min-height: 1.2em; }
  #empty { position: absolute; inset: 0; display: grid; place-items: center; color: #8a97a5; }
</style>
</head>
<body x-data="app()" x-init="start()">
<main>
  <section id="chat">
    <h1>scopegraph — cadrage contextualisé</h1>
    <div id="messages">
      <template x-for="m in messages"><div :class="m.role" x-text="m.text"></div></template>
    </div>
    <form @submit.prevent="send()">
      <input x-model="draft" placeholder="Décrivez votre projet…" autocomplete="off">
      <button>Envoyer</button>
    </form>
  </section>
  <section id="mappane">
    <div id="cy"></div>
    <div id="empty" x-show="!hasMap">La Context Map apparaîtra ici après votre description.</div>
    <div id="detail" x-show="hasMap" x-text="detail"></div>
  </section>
</main>
<script>
const TYPE_COLORS = { system: "#1d6fd1", feature: "#5aa2e8", business_object: "#7c5cd1",
                      project: "#2e9e6b", decision: "#e0a431", constraint: "#d15c4f",
                      risk: "#b33a3a" };
let cy = null;

function renderMap(payload, ui) {
  ui.hasMap = payload.nodes.length > 0;
  const elements = [
    ...payload.nodes.map(n => ({ data: { ...n } })),
    ...payload.edges.map(e => ({ data: { source: e.source, target: e.target, kind: e.type } })),
  ];
  if (cy) cy.destroy();
  cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    style: [
      { selector: "node", style: {
          label: "data(label)", "font-size": 9, "text-wrap": "wrap", "text-max-width": 90,
          "text-valign": "bottom", "text-margin-y": 4, width: 26, height: 26,
          "background-color": n => TYPE_COLORS[n.data("type")] || "#888", opacity: 0.55 } },
      { selector: 'node[role = "anchor"]', style: {
          opacity: 1, width: 38, height: 38, "border-width": 3, "border-color": "#13315c" } },
      { selector: 'node[role = "expanded"]', style: { opacity: 0.9, "border-width": 1,
          "border-style": "dashed", "border-color": "#5d6b7a" } },
      { selector: "edge", style: { width: 1.5, "line-color": "#aab6c2",
          "curve-style": "bezier", "target-arrow-shape": "triangle",
          "target-arrow-color": "#aab6c2", "arrow-scale": 0.8, label: "data(kind)",
          "font-size": 6, color: "#7a8794" } },
    ],
    layout: { name: "cose", animate: false, padding: 30 },
  });
  cy.on("tap", "node", evt => {
    const d = evt.target.data();
    const role = d.role === "anchor" ? `ancre (score ${d.score})`
      : d.role === "expanded" ? `étendu via ${d.via} (${d.hops} saut${d.hops > 1 ? "s" : ""}, score ${d.score})`
      : "nœud";
    ui.detail = `${d.label} — ${d.type} — ${role}`;
  });
}

function app() {
  return {
    messages: [], draft: "", sessionId: null, detail: "", hasMap: false,
    async start() {
      const response = await fetch("/api/session", { method: "POST" });
      this.sessionId = (await response.json()).session_id;
      this.push("bot", "Décrivez votre projet en une phrase — je cartographie le contexte existant.");
    },
    push(role, text) {
      this.messages.push({ role, text });
      this.$nextTick(() => { const el = document.getElementById("messages"); el.scrollTop = el.scrollHeight; });
    },
    async send() {
      const text = this.draft.trim();
      if (!text || !this.sessionId) return;
      this.push("user", text);
      this.draft = "";
      const response = await fetch(`/api/session/${this.sessionId}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) { this.push("bot", "Erreur — reformulez ou réessayez."); return; }
      const data = await response.json();
      renderMap(data.map, this);
      this.push("bot", data.question
        ?? "Carte stable — aucun point de périmètre à clarifier. (La suite — challenge et dossier — arrive en W3/W4.)");
    },
  };
}
</script>
</body>
</html>
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_web.py -q`
Expected: 5 passed

- [ ] **Step 4: Manual smoke (only if the embeddings extra is installed locally)**

```bash
pip install -e ".[embeddings]"   # one-time, downloads the model on first run
uvicorn --factory web.app:create_app --reload
```

Open http://127.0.0.1:8000 — type « Ajouter le paiement en 3 fois dans l'app mobile » :
the map should render anchors (big, solid border) and expanded nodes (dashed), and the
bot should ask a French scope question. This is a visual check, not a gate — the
TestClient tests are the gate.

- [ ] **Step 5: Commit**

```bash
git add web/static/index.html tests/test_web.py
git commit -m "feat: W2 page — chat pane + live Context Map with anchor/expanded styling"
```

---

## Task 17: Calibration bench — scripts/retrieval-smoke

**Files:**
- Create: `scripts/retrieval-smoke` (executable, NOT covered by CI tests — it needs the real model)

- [ ] **Step 1: Create the script**

Create `scripts/retrieval-smoke`:

```python
#!/usr/bin/env python3
"""Calibration bench: run the REAL embedder over the 6 eval briefs (never in CI).

Usage:  pip install -e ".[embeddings]"  &&  ./scripts/retrieval-smoke
Prints anchors, expanded nodes with provenance, and domain derivation per brief —
the §3 constants in core/retrieval/config.py are tuned by reading this output.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.graph.service import GraphService  # noqa: E402
from core.retrieval.index import VectorIndex, graph_fingerprint  # noqa: E402
from core.retrieval.retriever import retrieve  # noqa: E402
from core.retrieval.st_embedder import SentenceTransformersEmbedder  # noqa: E402

BRIEFS = {
    "cas-1-bnpl": "Ajouter une option de paiement en 3 fois dans l'app mobile.",
    "cas-2-beneficiaires": (
        "Permettre aux clients entreprise de créer des bénéficiaires depuis leur portail."
    ),
    "cas-3-cashback": (
        "Proposer un programme de cash-back aux clients lors de leurs paiements "
        "chez les commerçants partenaires."
    ),
    "cas-4-plafonds-ip": "Relever les plafonds de virement instantané pour les clients premium.",
    "cas-5-ia-reclamations": (
        "Mettre en place un assistant IA qui rédige les réponses aux réclamations clients."
    ),
    "cas-6-onboarding": "Refondre le parcours d'entrée en relation 100 % digital.",
}


def main() -> None:
    service = GraphService.from_dir(ROOT / "graph")
    index = VectorIndex(SentenceTransformersEmbedder())
    index.build(service, graph_fingerprint(ROOT / "graph"))
    for case, brief in BRIEFS.items():
        result = retrieve(brief, service, index)
        print(f"\n=== {case}: {brief}")
        print("  -- anchors")
        for scored in result.anchors:
            print(f"    {scored.score:.3f}  {scored.node_id}  (sim {scored.semantic_sim:.3f})")
        print("  -- expanded (top 12)")
        for scored in result.expanded[:12]:
            hops = len(scored.path)
            print(f"    {scored.score:.3f}  {scored.node_id}  via {scored.anchor_id} ({hops} hop)")
        print(f"  -- domains {result.domain_scores} -> derived {result.derived_domains}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable, lint**

```bash
chmod +x scripts/retrieval-smoke
ruff check scripts/retrieval-smoke
```

Expected: no ruff errors. If `sentence-transformers` is installed locally, run
`./scripts/retrieval-smoke` once and eyeball: case 1 should anchor on mobile/credit nodes
and expand to `sys-logiciel-tpe`. Record surprising rankings in the PR description — do
NOT silently retune constants here; constant changes are their own commit with rationale.

- [ ] **Step 3: Commit**

```bash
git add scripts/retrieval-smoke
git commit -m "feat: retrieval-smoke — real-model calibration bench over the 6 eval briefs"
```

---

## Task 18: Final verification, BUILD-ORDER, branch finish

- [ ] **Step 1: Full verification**

Run: `ruff check . && pytest -q`
Expected: 0 ruff errors; ALL tests pass (W1's 37+ plus the ~40 new ones). Read the
output before claiming done (verification-before-completion).

- [ ] **Step 2: Update BUILD-ORDER**

Edit `docs/BUILD-ORDER.md`: move W2 into "Current state" (lots delivered: retrieval
package, hybrid scorer with eval cases 1–2 green, MAPPING loop with template questions,
web chat+map; spec + plan references), and make "Next chantier" point to W3 (LLM
providers Mistral/DeepSeek/Mock, grounding gate, propose/validate, challenge — MVP spec
§8) with a note that CHALLENGING+ states already raise NotImplementedError and the LLM
rephrasing layers on top of the W2 templates.

```bash
git add docs/BUILD-ORDER.md
git commit -m "docs: BUILD-ORDER — W2 retrieval + MAPPING + first screens shipped"
```

- [ ] **Step 3: Finish the branch**

Use superpowers:finishing-a-development-branch — present merge/PR options for
`w2-retrieval-web` (W1 merged via the same flow).

---

## Self-review notes (done at plan-writing time)

- **Spec coverage**: §1 decisions → Tasks 3 (A1), 11/12 (B1 + templates), 15 (C1), 17
  (no-reranker escalation bench) · §2 → Tasks 2–6 · §3 → Tasks 7–9 · §4 → Tasks 10–13 ·
  §5 → Tasks 14–16 · §6 → tests throughout + smoke (17) · §7 honored (no LLM anywhere) ·
  §8 → Tasks 1, 18.
- **Known intentional deviations**: none.
- **Sequencing caveat for executors**: Task 13's first-question assertion depends on
  expansion ordering (1-hop beats 2-hop by DECAY); if a constant changes during Task 9
  calibration, re-run Task 13's tests before assuming a session bug.
