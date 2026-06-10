# Week 1 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the W1 foundations: both ADRs, graph schema v1 as Pydantic models, YAML loader, in-memory GraphService, the seeded French banking-IT graph (24 nodes with deliberate traps), README v1, and the 5 eval case drafts.

**Architecture:** Schema v1 lives in `core/graph/` as a frozen Pydantic discriminated union (the contract with ecosystem-foundry, ADR 0001). A fail-fast loader turns `graph/nodes/*.yaml` + `graph/edges.yaml` into an in-memory `GraphService` (lookup, neighbors, k-hop BFS with path provenance). Seed content is French; code/docs are English (spec §1).

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, pytest. No LLM, no embeddings, no web in W1.

**Context to read first:** `docs/project-kickoff.md` §4–§5, `docs/specs/2026-06-09-scopegraph-mvp-design.md`, `AGENTS.md` (hard rules — especially: hermetic tests, fictional entities only, language split).

---

## File structure

```
core/graph/__init__.py        # re-exports the public surface
core/graph/models.py          # schema v1: enums, DOMAINS, node types, Edge (frozen contract)
core/graph/loader.py          # YAML -> validated objects; GraphLoadError with file context
core/graph/service.py         # GraphService: get_node, all_nodes, neighbors, k_hop
tests/test_models.py
tests/test_loader.py
tests/test_service.py
tests/test_seed.py            # integration: the real seed graph + trap assertions
graph/nodes/<24 files>.yaml   # seed nodes (French content)
graph/edges.yaml              # seed edges
docs/adr/0000-pivot-from-mas.md
docs/adr/0001-graph-schema-v1.md
docs/eval/cases.md            # 5 eval case drafts (French)
README.md                     # v1 (replaces placeholder)
docs/BUILD-ORDER.md           # updated at the end
```

---

### Task 1: ADR 0000 — the pivot story

**Files:**
- Create: `docs/adr/0000-pivot-from-mas.md`
- Delete: `docs/adr/.gitkeep`

- [ ] **Step 1: Write the ADR.** Source material: kickoff §1 (read it; rephrase, don't paste). Structure (with front matter — ADRs are active docs, `docs-list` validates them):

```markdown
---
summary: ADR 0000 — why scopegraph exists; the pivot from MAS to ecosystem-aware scoping
read_when:
  - telling the project story (README, interviews)
  - questioning the product positioning
---

# ADR 0000 — Pivot from MAS to scopegraph

Date: 2026-06-09 · Status: accepted

## Context
[~150 words: MAS turned fuzzy needs into structured proposals; overlapped use-case-assistant;
complexity not justified by a visibly different promise.]

## Decision
[~120 words: sell context-aware scoping for non-independent projects, not a better spec-filler.
New flow: need → ecosystem graph → links/dependencies/risks → contextualized scoping.
Rename MAS → scopegraph; old repo stays private as mas-legacy.]

## Consequences
[Bullets: portfolio narrative use-case-assistant → scopegraph → ecosystem-foundry;
MAS patterns ported surgically (propose/validate/apply, runtime authority, hermetic tests);
MAS features explicitly dropped (Confluence, EDB/SPEC pipelines, multi-agent layout).]
```

- [ ] **Step 2: Verify.** Run: `./scripts/docs-list` → the ADR appears with its summary, no `[missing front matter]` flag.

- [ ] **Step 3: Commit.**

```bash
git add docs/adr/ && git commit -m "docs: ADR 0000 — pivot from MAS to scopegraph"
```

---

### Task 2: ADR 0001 — graph schema v1

**Files:**
- Create: `docs/adr/0001-graph-schema-v1.md`

- [ ] **Step 1: Write the ADR.** Source: kickoff §4 (this ADR is the canonical home of the schema; the kickoff remains historical record). Structure:

```markdown
---
summary: ADR 0001 — graph schema v1 (frozen contract): 5 node types, 5 edge types, domain vocabulary
read_when:
  - touching core/graph/models.py or any YAML under graph/
  - proposing any schema or domain-vocabulary change (requires a new ADR)
---

# ADR 0001 — Graph schema v1

Date: 2026-06-09 · Status: accepted

## Context
[~80 words: the schema is the only contact point between scopegraph (consumer) and the future
ecosystem-foundry (producer). Drift would silently break the contract → frozen, changes need an ADR.]

## Decision
[Reproduce from kickoff §4, in ADR voice:
- the 5 node types with their fields (System, Project, Decision, Constraint, Risk)
- shared fields: id slug, domains[], tags[], created_from (seed | scoping:<id> | ingestion:<id>)
- the 10-entry controlled domain vocabulary, with the rule: extensible only via ADR
- the 5 edge types; RELATES_TO is last resort and MUST carry a note
- edge fields: source_id, target_id, type, note, evidence, created_from, verified
- storage: one YAML per node in graph/nodes/, edges in graph/edges.yaml, in-memory at runtime]

## Consequences
[Bullets: Pydantic models in core/graph/models.py are the executable form of this ADR;
domains_in_vocabulary and RELATES_TO-note rules enforced at model level;
ecosystem-foundry output must validate against these models unchanged.]
```

- [ ] **Step 2: Verify.** Run: `./scripts/docs-list` → both ADRs listed clean.

- [ ] **Step 3: Commit.**

```bash
git add docs/adr/ && git commit -m "docs: ADR 0001 — graph schema v1 (frozen contract)"
```

---

### Task 3: Schema models — enums, domains, Edge

**Files:**
- Create: `core/graph/models.py`, `core/graph/__init__.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_models.py
import pytest
from pydantic import ValidationError

from core.graph.models import DOMAINS, Edge, EdgeType


def test_domain_vocabulary_is_the_adr_0001_set():
    assert "monetique" in DOMAINS
    assert "tpe-acceptation" in DOMAINS
    assert len(DOMAINS) == 10


def test_edge_valid():
    edge = Edge(
        source_id="sys-app-mobile",
        target_id="sys-moteur-autorisation",
        type=EdgeType.DEPENDS_ON,
        evidence="description of sys-app-mobile",
    )
    assert edge.verified is False
    assert edge.created_from == "seed"


def test_relates_to_requires_note():
    with pytest.raises(ValidationError, match="RELATES_TO"):
        Edge(source_id="a-b", target_id="c-d", type=EdgeType.RELATES_TO)


def test_edge_created_from_format_enforced():
    with pytest.raises(ValidationError):
        Edge(source_id="a-b", target_id="c-d", type=EdgeType.DEPENDS_ON, created_from="manual")
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_models.py -v` → FAIL: `ModuleNotFoundError: No module named 'core.graph'`.

- [ ] **Step 3: Implement.**

```python
# core/graph/models.py
"""Graph schema v1 — the frozen contract (ADR 0001). Changes require a new ADR."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

DOMAINS: frozenset[str] = frozenset({
    "monetique",
    "tpe-acceptation",
    "paiement-instantane",
    "dsp2-open-banking",
    "lcb-ft",
    "credit",
    "banque-en-ligne",
    "referentiel-client",
    "editique-reporting",
    "socle-si",
})

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
CREATED_FROM_PATTERN = r"^(seed|scoping:[a-z0-9-]+|ingestion:[a-z0-9-]+)$"


class EdgeType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    PRODUCED = "PRODUCED"
    CONSTRAINS = "CONSTRAINS"
    SUPERSEDES = "SUPERSEDES"
    RELATES_TO = "RELATES_TO"


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(pattern=SLUG_PATTERN)
    target_id: str = Field(pattern=SLUG_PATTERN)
    type: EdgeType
    note: str = ""
    evidence: str = ""
    created_from: str = Field(default="seed", pattern=CREATED_FROM_PATTERN)
    verified: bool = False

    @model_validator(mode="after")
    def relates_to_must_carry_note(self) -> "Edge":
        if self.type is EdgeType.RELATES_TO and not self.note.strip():
            raise ValueError("RELATES_TO is a last-resort link and must carry a note (ADR 0001)")
        return self
```

```python
# core/graph/__init__.py
from core.graph.models import DOMAINS, Edge, EdgeType

__all__ = ["DOMAINS", "Edge", "EdgeType"]
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_models.py -v` → 4 PASS.

- [ ] **Step 5: Commit.**

```bash
git add core/graph tests/test_models.py
git commit -m "feat: graph schema v1 — domain vocabulary and Edge model"
```

---

### Task 4: Schema models — the five node types

**Files:**
- Modify: `core/graph/models.py`, `core/graph/__init__.py`
- Test: `tests/test_models.py` (append)

- [ ] **Step 1: Append the failing tests.**

```python
# append to tests/test_models.py
import datetime

from pydantic import TypeAdapter

from core.graph.models import Decision, Node, System


def test_system_valid_and_frozen():
    sys_node = System(
        id="sys-moteur-autorisation",
        name="Moteur d'autorisation carte",
        aliases=["MONAUT"],
        description="Autorise les transactions carte en temps réel.",
        owner_team="Équipe Monétique",
        domains=["monetique"],
    )
    assert sys_node.type == "system"
    with pytest.raises(ValidationError):
        sys_node.name = "autre"  # frozen


def test_unknown_domain_rejected():
    with pytest.raises(ValidationError, match="vocabulary"):
        System(
            id="sys-x",
            name="X",
            description="d",
            owner_team="t",
            domains=["blockchain"],
        )


def test_node_union_discriminates_on_type():
    adapter = TypeAdapter(Node)
    node = adapter.validate_python({
        "type": "decision",
        "id": "dec-scoring-unique",
        "title": "Scoring fraude unique",
        "statement": "Le scoring fraude est l'unique point de décision risque paiement.",
        "rationale": "Éviter les scorings parallèles divergents.",
        "date": datetime.date(2024, 3, 1),
        "decided_by": "Comité d'architecture",
        "domains": ["lcb-ft"],
    })
    assert isinstance(node, Decision)
    assert node.still_active is True


def test_node_requires_at_least_one_domain():
    with pytest.raises(ValidationError):
        System(id="sys-x", name="X", description="d", owner_team="t", domains=[])
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_models.py -v` → FAIL: `ImportError: cannot import name 'Decision'`.

- [ ] **Step 3: Implement — append to `core/graph/models.py`.**

```python
import datetime
from typing import Annotated, Literal, Union

from pydantic import field_validator


class NodeBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=SLUG_PATTERN)
    domains: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    created_from: str = Field(default="seed", pattern=CREATED_FROM_PATTERN)

    @field_validator("domains")
    @classmethod
    def domains_in_vocabulary(cls, value: list[str]) -> list[str]:
        unknown = set(value) - DOMAINS
        if unknown:
            raise ValueError(
                f"unknown domains {sorted(unknown)}: the vocabulary is fixed by ADR 0001"
            )
        return value


class System(NodeBase):
    type: Literal["system"] = "system"
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    owner_team: str
    data_quality_notes: str = ""
    known_risks: list[str] = Field(default_factory=list)


class Project(NodeBase):
    type: Literal["project"] = "project"
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    status: Literal["done", "ongoing", "cancelled"]
    owner_team: str
    outcomes: str = ""
    known_risks: list[str] = Field(default_factory=list)


class Decision(NodeBase):
    type: Literal["decision"] = "decision"
    title: str
    statement: str
    rationale: str
    date: datetime.date
    decided_by: str
    still_active: bool = True


class Constraint(NodeBase):
    type: Literal["constraint"] = "constraint"
    title: str
    statement: str
    source: str
    severity: Literal["low", "medium", "high"]


class Risk(NodeBase):
    type: Literal["risk"] = "risk"
    title: str
    statement: str
    likelihood: Literal["low", "medium", "high"]
    impact: Literal["low", "medium", "high"]
    mitigations: list[str] = Field(default_factory=list)


Node = Annotated[
    Union[System, Project, Decision, Constraint, Risk],
    Field(discriminator="type"),
]
```

Update `core/graph/__init__.py`:

```python
from core.graph.models import (
    DOMAINS,
    Constraint,
    Decision,
    Edge,
    EdgeType,
    Node,
    Project,
    Risk,
    System,
)

__all__ = [
    "DOMAINS", "Constraint", "Decision", "Edge", "EdgeType",
    "Node", "Project", "Risk", "System",
]
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_models.py -v` → 8 PASS. Also run `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit.**

```bash
git add core/graph tests/test_models.py
git commit -m "feat: graph schema v1 — five node types as discriminated union"
```

---

### Task 5: YAML loader

**Files:**
- Create: `core/graph/loader.py`
- Test: `tests/test_loader.py`

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_loader.py
import pytest

from core.graph.loader import GraphLoadError, load_graph

SYSTEM_YAML = """
type: system
id: sys-moteur-autorisation
name: Moteur d'autorisation carte
aliases: [MONAUT]
description: Autorise les transactions carte en temps réel.
owner_team: Équipe Monétique
domains: [monetique]
"""

RISK_YAML = """
type: risk
id: risk-kyc-obsolete
title: Données KYC obsolètes
statement: Une part des dossiers KYC n'a pas été revue depuis plus de 3 ans.
likelihood: high
impact: medium
domains: [referentiel-client]
"""


def write_graph(tmp_path, node_yamls, edges_yaml="edges: []\n"):
    nodes_dir = tmp_path / "nodes"
    nodes_dir.mkdir()
    for i, content in enumerate(node_yamls):
        (nodes_dir / f"node{i}.yaml").write_text(content, encoding="utf-8")
    (tmp_path / "edges.yaml").write_text(edges_yaml, encoding="utf-8")
    return tmp_path


def test_loads_nodes_and_edges(tmp_path):
    edges = """
edges:
  - source_id: risk-kyc-obsolete
    target_id: sys-moteur-autorisation
    type: RELATES_TO
    note: le scoring consomme des données KYC potentiellement périmées
"""
    nodes, edge_list = load_graph(write_graph(tmp_path, [SYSTEM_YAML, RISK_YAML], edges))
    assert set(nodes) == {"sys-moteur-autorisation", "risk-kyc-obsolete"}
    assert len(edge_list) == 1


def test_duplicate_id_fails_with_filename(tmp_path):
    with pytest.raises(GraphLoadError, match="node1.yaml"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, SYSTEM_YAML]))


def test_invalid_node_fails_with_filename(tmp_path):
    bad = SYSTEM_YAML.replace("domains: [monetique]", "domains: [blockchain]")
    with pytest.raises(GraphLoadError, match="node0.yaml"):
        load_graph(write_graph(tmp_path, [bad]))


def test_edge_to_unknown_node_fails(tmp_path):
    edges = """
edges:
  - source_id: sys-moteur-autorisation
    target_id: sys-fantome
    type: DEPENDS_ON
"""
    with pytest.raises(GraphLoadError, match="sys-fantome"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML], edges))
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_loader.py -v` → FAIL: no module `core.graph.loader`.

- [ ] **Step 3: Implement.**

```python
# core/graph/loader.py
"""Load the YAML graph (graph/nodes/*.yaml + graph/edges.yaml) into validated schema-v1 objects.

Fail-fast: any invalid file aborts the load with the offending path in the error (spec §6).
"""

from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from core.graph.models import Edge, Node

_NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)


class GraphLoadError(Exception):
    """The graph on disk violates schema v1."""


def load_graph(graph_dir: Path) -> tuple[dict[str, Node], list[Edge]]:
    nodes: dict[str, Node] = {}
    for path in sorted((graph_dir / "nodes").glob("*.yaml")):
        data = _read_yaml(path)
        try:
            node = _NODE_ADAPTER.validate_python(data)
        except ValidationError as exc:
            raise GraphLoadError(f"{path}: invalid node: {exc}") from exc
        if node.id in nodes:
            raise GraphLoadError(f"{path}: duplicate node id '{node.id}'")
        nodes[node.id] = node

    edges: list[Edge] = []
    edges_path = graph_dir / "edges.yaml"
    raw_edges = (_read_yaml(edges_path) or {}).get("edges") or []
    for index, raw in enumerate(raw_edges):
        try:
            edge = Edge.model_validate(raw)
        except ValidationError as exc:
            raise GraphLoadError(f"{edges_path}: edge #{index}: {exc}") from exc
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in nodes:
                raise GraphLoadError(
                    f"{edges_path}: edge #{index} references unknown node '{endpoint}'"
                )
        edges.append(edge)
    return nodes, edges


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GraphLoadError(f"{path}: invalid YAML: {exc}") from exc
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_loader.py -v` → 4 PASS.

- [ ] **Step 5: Commit.**

```bash
git add core/graph/loader.py tests/test_loader.py
git commit -m "feat: fail-fast YAML graph loader"
```

---

### Task 6: GraphService — lookup and neighbors

**Files:**
- Create: `core/graph/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing tests.** The fixture builds a tiny chain `con-pci-dss -CONSTRAINS→ sys-moteur-autorisation ←DEPENDS_ON- sys-logiciel-tpe` (the shape of the real 2-hop trap).

```python
# tests/test_service.py
import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService, UnknownNodeError


@pytest.fixture()
def service() -> GraphService:
    nodes = [
        Constraint(
            id="con-pci-dss",
            title="Périmètre PCI DSS",
            statement="Tout composant manipulant des données carte entre dans le périmètre PCI DSS.",
            source="PCI Security Standards Council",
            severity="high",
            domains=["monetique"],
        ),
        System(
            id="sys-moteur-autorisation",
            name="Moteur d'autorisation carte",
            description="Autorise les transactions carte.",
            owner_team="Monétique",
            domains=["monetique"],
        ),
        System(
            id="sys-logiciel-tpe",
            name="Logiciel TPE",
            description="Logiciel embarqué des terminaux de paiement.",
            owner_team="Acceptation",
            domains=["tpe-acceptation"],
        ),
        System(
            id="sys-isole",
            name="Système isolé",
            description="Aucun lien.",
            owner_team="Autre",
            domains=["socle-si"],
        ),
    ]
    edges = [
        Edge(source_id="con-pci-dss", target_id="sys-moteur-autorisation",
             type=EdgeType.CONSTRAINS),
        Edge(source_id="sys-logiciel-tpe", target_id="sys-moteur-autorisation",
             type=EdgeType.DEPENDS_ON),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def test_get_node(service):
    assert service.get_node("con-pci-dss").severity == "high"


def test_get_unknown_node_raises(service):
    with pytest.raises(UnknownNodeError, match="sys-fantome"):
        service.get_node("sys-fantome")


def test_neighbors_are_bidirectional(service):
    hits = service.neighbors("sys-moteur-autorisation")
    ids = {node.id for _, node in hits}
    assert ids == {"con-pci-dss", "sys-logiciel-tpe"}


def test_neighbors_filter_by_edge_type(service):
    hits = service.neighbors("sys-moteur-autorisation", edge_types={EdgeType.CONSTRAINS})
    assert [node.id for _, node in hits] == ["con-pci-dss"]


def test_neighbors_of_isolated_node_empty(service):
    assert service.neighbors("sys-isole") == []
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_service.py -v` → FAIL: no module `core.graph.service`.

- [ ] **Step 3: Implement.**

```python
# core/graph/service.py
"""In-memory graph service: the deterministic read API over the loaded graph."""

from collections.abc import Iterable
from pathlib import Path

from core.graph.loader import load_graph
from core.graph.models import Edge, EdgeType, Node


class UnknownNodeError(KeyError):
    """Raised when a node id does not exist in the graph."""


class GraphService:
    def __init__(self, nodes: dict[str, Node], edges: list[Edge]) -> None:
        self._nodes = nodes
        self._edges = edges
        self._adjacency: dict[str, list[Edge]] = {node_id: [] for node_id in nodes}
        for edge in edges:
            self._adjacency[edge.source_id].append(edge)
            self._adjacency[edge.target_id].append(edge)

    @classmethod
    def from_dir(cls, graph_dir: Path) -> "GraphService":
        return cls(*load_graph(graph_dir))

    def get_node(self, node_id: str) -> Node:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise UnknownNodeError(f"unknown node id '{node_id}'") from None

    def all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def all_edges(self) -> list[Edge]:
        return list(self._edges)

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
    ) -> list[tuple[Edge, Node]]:
        """Adjacent (edge, node) pairs, both directions, in stable edge order."""
        self.get_node(node_id)  # raises on unknown id
        wanted = set(edge_types) if edge_types is not None else None
        result: list[tuple[Edge, Node]] = []
        for edge in self._adjacency[node_id]:
            if wanted is not None and edge.type not in wanted:
                continue
            other_id = edge.target_id if edge.source_id == node_id else edge.source_id
            result.append((edge, self._nodes[other_id]))
        return result
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_service.py -v` → 5 PASS.

- [ ] **Step 5: Commit.**

```bash
git add core/graph/service.py tests/test_service.py
git commit -m "feat: GraphService with lookup and bidirectional neighbors"
```

---

### Task 7: GraphService — k-hop traversal with path provenance

**Files:**
- Modify: `core/graph/service.py`
- Test: `tests/test_service.py` (append)

- [ ] **Step 1: Append the failing tests.** Provenance matters: W2 retrieval must say "included via `sys-moteur-autorisation` → CONSTRAINS" (spec §4).

```python
# append to tests/test_service.py


def test_k_hop_finds_two_hop_constraint(service):
    # The canonical trap shape: from the TPE software, PCI DSS is 2 hops away.
    reached = service.k_hop("sys-logiciel-tpe", k=2)
    assert "con-pci-dss" in reached
    path = reached["con-pci-dss"]
    assert len(path) == 2
    assert path[0].type == EdgeType.DEPENDS_ON
    assert path[1].type == EdgeType.CONSTRAINS


def test_k_hop_respects_radius(service):
    reached = service.k_hop("sys-logiciel-tpe", k=1)
    assert set(reached) == {"sys-moteur-autorisation"}


def test_k_hop_excludes_start_and_unreachable(service):
    reached = service.k_hop("sys-logiciel-tpe", k=3)
    assert "sys-logiciel-tpe" not in reached
    assert "sys-isole" not in reached
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_service.py -v` → FAIL: `GraphService` has no attribute `k_hop`.

- [ ] **Step 3: Implement — append method to `GraphService`.**

```python
    def k_hop(self, start: str, k: int) -> dict[str, list[Edge]]:
        """BFS up to k hops (edges treated as undirected).

        Returns reached node id -> shortest path as the list of edges from start.
        The start node itself is excluded.
        """
        self.get_node(start)
        paths: dict[str, list[Edge]] = {start: []}
        frontier = [start]
        for _ in range(k):
            next_frontier: list[str] = []
            for node_id in frontier:
                for edge, node in self.neighbors(node_id):
                    if node.id in paths:
                        continue
                    paths[node.id] = [*paths[node_id], edge]
                    next_frontier.append(node.id)
            frontier = next_frontier
        del paths[start]
        return paths
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest -v` → all PASS (models + loader + service + smoke). `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Update `core/graph/__init__.py`** — add `GraphService`, `UnknownNodeError`, `GraphLoadError`, `load_graph` to imports and `__all__`.

- [ ] **Step 6: Commit.**

```bash
git add core/graph tests/test_service.py
git commit -m "feat: k-hop BFS traversal with shortest-path provenance"
```

---

### Task 8: Seed data — 24 French banking-IT nodes + edges

**Files:**
- Create: `graph/nodes/<id>.yaml` × 24 (one per node, filename = `<id>.yaml`)
- Modify: `graph/edges.yaml`
- Delete: `graph/nodes/.gitkeep`
- Test: `tests/test_seed.py`

All content **in French**, all entities **fictional** (AGENTS.md hard rules 5–6). Every node needs `description`/`statement` rich enough to embed (2–4 sentences), and Systems/Projects need meaningful `data_quality_notes`/`known_risks` where indicated — they feed the challenge step (kickoff §4).

- [ ] **Step 1: Write the failing integration test.**

```python
# tests/test_seed.py
"""Integration: the real seed graph loads and contains the deliberate traps (kickoff §5.1)."""

from pathlib import Path

import pytest

from core.graph.models import EdgeType
from core.graph.service import GraphService

GRAPH_DIR = Path(__file__).resolve().parent.parent / "graph"


@pytest.fixture(scope="module")
def service() -> GraphService:
    return GraphService.from_dir(GRAPH_DIR)


def test_seed_size_and_domain_coverage(service):
    nodes = service.all_nodes()
    assert 15 <= len(nodes) <= 25
    covered = {domain for node in nodes for domain in node.domains}
    assert len(covered) >= 4


def test_alias_trap_monaut(service):
    node = service.get_node("sys-moteur-autorisation")
    assert "MONAUT" in node.aliases


def test_superseded_decision_trap(service):
    superseding = [
        edge for edge in service.all_edges() if edge.type == EdgeType.SUPERSEDES
    ]
    assert any(
        edge.source_id == "dec-scoring-unique"
        and edge.target_id == "dec-scoring-par-canal-2021"
        for edge in superseding
    )
    assert service.get_node("dec-scoring-par-canal-2021").still_active is False


def test_contradiction_trap_is_marked(service):
    hits = service.neighbors(
        "dec-gel-evolutions-monetique", edge_types={EdgeType.RELATES_TO}
    )
    assert any(node.id == "dec-reutilisation-sca" for _, node in hits)


def test_cross_domain_two_hop_chain(service):
    # The monétique constraint must reach the TPE software through 2 hops.
    reached = service.k_hop("sys-logiciel-tpe", k=2)
    assert "con-pci-dss" in reached
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_seed.py -v` → FAIL (empty graph).

- [ ] **Step 3: Write the 24 node files.** Full roster (id · domains · content brief):

**Systems (7):**
| id | domains | brief |
|---|---|---|
| `sys-moteur-autorisation` | monetique | "Moteur d'autorisation carte" (MONAUT), autorisations temps réel, owner Monétique. `aliases: [MONAUT, "moteur d'autorisation"]` ← **alias trap**. known_risks: dette technique COBOL partielle |
| `sys-logiciel-tpe` | tpe-acceptation | "Logiciel d'acceptation TPE" (PAYTERM), embarqué sur la flotte de terminaux, owner Acceptation. known_risks: fragmentation des versions firmware |
| `sys-app-mobile` | banque-en-ligne | "Application mobile bancaire" (MOBANK), parcours clients particuliers |
| `sys-passerelle-ip` | paiement-instantane | "Passerelle paiement instantané" (FLUXINST), rails SEPA Inst |
| `sys-scoring-fraude` | lcb-ft, monetique | "Moteur de scoring fraude" (FRAUDSCORE), scoring temps réel des paiements |
| `sys-referentiel-client` | referentiel-client | "Référentiel client" (REFCLI), données KYC. data_quality_notes: revues KYC en retard sur le stock ancien ← feeds the challenge |
| `sys-core-banking` | socle-si | "Core banking" (LEDGERIS), tenue de compte |

**Projects (5):** `proj-programme-dsp2` (done, dsp2-open-banking+monetique, a produit l'orchestration SCA) · `proj-migration-flotte-tpe` (ongoing, tpe-acceptation, migration logicielle de la flotte) · `proj-lancement-paiement-instantane` (done, paiement-instantane) · `proj-refonte-scoring-fraude` (done, lcb-ft, a produit la décision scoring unique) · `proj-dedup-incidents` (done, socle-si).

**Decisions (5):** `dec-reutilisation-sca` (2023, active : tout nouveau flux de paiement réutilise l'orchestration SCA du programme DSP2) · `dec-scoring-unique` (2024, active : le scoring fraude est l'unique point de décision risque paiement) · `dec-scoring-par-canal-2021` (2021, **`still_active: false`** ← superseded trap) · `dec-releases-tpe-trimestrielles` (active : mises à jour TPE trimestrielles, pas de hors-cycle) · `dec-gel-evolutions-monetique` (active : gel des évolutions non réglementaires sur MONAUT pendant la migration TPE ← **contradiction trap** vs dec-reutilisation-sca, matérialisée par un RELATES_TO noté).

**Constraints (4):** `con-pci-dss` (monetique, high) · `con-lcb-ft-screening` (lcb-ft + paiement-instantane, high : screening obligatoire sur tout nouveau rail) · `con-standard-api-interne` (socle-si, medium) · `con-ai-act` (socle-si + lcb-ft, medium : classification de risque des composants IA).

**Risks (3):** `risk-kyc-obsolete` (referentiel-client, high/medium) · `risk-fragmentation-tpe` (tpe-acceptation, medium/high) · `risk-contournement-plafonds-ip` (paiement-instantane + lcb-ft, low/high).

Template (every file follows this shape; complete example for the alias-trap node):

```yaml
# graph/nodes/sys-moteur-autorisation.yaml
type: system
id: sys-moteur-autorisation
name: Moteur d'autorisation carte
aliases: [MONAUT, "moteur d'autorisation"]
description: >-
  Cœur de la chaîne monétique : autorise ou refuse chaque transaction carte en
  temps réel (plafonds, opposition, solde, règles réseau). Sollicité par les TPE,
  les automates et l'app mobile. Toute évolution touche un chemin critique.
owner_team: Équipe Monétique
data_quality_notes: ""
known_risks:
  - Dette technique sur les modules COBOL historiques de tarification.
domains: [monetique]
tags: [temps-reel, chemin-critique]
created_from: seed
```

- [ ] **Step 4: Write `graph/edges.yaml`** — complete edge list (every edge carries `evidence` naming the node field that justifies it, e.g. `description of sys-app-mobile`; seed edges are `verified: true` — hand-curated):

```yaml
edges:
  # DEPENDS_ON — runtime dependency spine
  - {source_id: sys-app-mobile, target_id: sys-moteur-autorisation, type: DEPENDS_ON,
     evidence: description of sys-app-mobile, verified: true}
  - {source_id: sys-logiciel-tpe, target_id: sys-moteur-autorisation, type: DEPENDS_ON,
     evidence: description of sys-logiciel-tpe, verified: true}
  - {source_id: sys-moteur-autorisation, target_id: sys-scoring-fraude, type: DEPENDS_ON,
     evidence: description of sys-moteur-autorisation, verified: true}
  - {source_id: sys-passerelle-ip, target_id: sys-scoring-fraude, type: DEPENDS_ON,
     evidence: description of sys-passerelle-ip, verified: true}
  - {source_id: sys-app-mobile, target_id: sys-referentiel-client, type: DEPENDS_ON,
     evidence: description of sys-app-mobile, verified: true}
  - {source_id: sys-moteur-autorisation, target_id: sys-core-banking, type: DEPENDS_ON,
     evidence: description of sys-moteur-autorisation, verified: true}
  - {source_id: sys-passerelle-ip, target_id: sys-core-banking, type: DEPENDS_ON,
     evidence: description of sys-passerelle-ip, verified: true}
  # PRODUCED — provenance of decisions/systems
  - {source_id: proj-programme-dsp2, target_id: dec-reutilisation-sca, type: PRODUCED,
     evidence: outcomes of proj-programme-dsp2, verified: true}
  - {source_id: proj-refonte-scoring-fraude, target_id: dec-scoring-unique, type: PRODUCED,
     evidence: outcomes of proj-refonte-scoring-fraude, verified: true}
  - {source_id: proj-lancement-paiement-instantane, target_id: sys-passerelle-ip, type: PRODUCED,
     evidence: outcomes of proj-lancement-paiement-instantane, verified: true}
  # CONSTRAINS — the inherited-constraint web
  - {source_id: con-pci-dss, target_id: sys-moteur-autorisation, type: CONSTRAINS,
     evidence: statement of con-pci-dss, verified: true}
  - {source_id: con-lcb-ft-screening, target_id: sys-passerelle-ip, type: CONSTRAINS,
     evidence: statement of con-lcb-ft-screening, verified: true}
  - {source_id: dec-releases-tpe-trimestrielles, target_id: sys-logiciel-tpe, type: CONSTRAINS,
     evidence: statement of dec-releases-tpe-trimestrielles, verified: true}
  - {source_id: dec-releases-tpe-trimestrielles, target_id: proj-migration-flotte-tpe, type: CONSTRAINS,
     evidence: statement of dec-releases-tpe-trimestrielles, verified: true}
  - {source_id: dec-scoring-unique, target_id: sys-moteur-autorisation, type: CONSTRAINS,
     evidence: statement of dec-scoring-unique, verified: true}
  - {source_id: dec-scoring-unique, target_id: sys-passerelle-ip, type: CONSTRAINS,
     evidence: statement of dec-scoring-unique, verified: true}
  - {source_id: dec-reutilisation-sca, target_id: sys-app-mobile, type: CONSTRAINS,
     evidence: statement of dec-reutilisation-sca, verified: true}
  - {source_id: dec-gel-evolutions-monetique, target_id: sys-moteur-autorisation, type: CONSTRAINS,
     evidence: statement of dec-gel-evolutions-monetique, verified: true}
  - {source_id: con-ai-act, target_id: sys-scoring-fraude, type: CONSTRAINS,
     evidence: statement of con-ai-act, verified: true}
  # SUPERSEDES — the superseded-decision trap
  - {source_id: dec-scoring-unique, target_id: dec-scoring-par-canal-2021, type: SUPERSEDES,
     evidence: statement of dec-scoring-unique, verified: true}
  # RELATES_TO — weak links, note mandatory
  - {source_id: dec-gel-evolutions-monetique, target_id: dec-reutilisation-sca, type: RELATES_TO,
     note: tension non arbitrée — le gel monétique contredit la réutilisation SCA pour tout nouveau flux,
     evidence: statements of both decisions, verified: true}
  - {source_id: risk-fragmentation-tpe, target_id: proj-migration-flotte-tpe, type: RELATES_TO,
     note: la migration de flotte est la mitigation principale de ce risque,
     evidence: mitigations of risk-fragmentation-tpe, verified: true}
  - {source_id: risk-kyc-obsolete, target_id: sys-referentiel-client, type: RELATES_TO,
     note: risque porté par la qualité des données du référentiel,
     evidence: data_quality_notes of sys-referentiel-client, verified: true}
  - {source_id: risk-contournement-plafonds-ip, target_id: sys-passerelle-ip, type: RELATES_TO,
     note: scénario de contournement des plafonds via rafales de virements instantanés,
     evidence: statement of risk-contournement-plafonds-ip, verified: true}
```

- [ ] **Step 5: Run to verify pass.** `.venv/bin/python -m pytest tests/test_seed.py -v` → 5 PASS. Then full suite: `.venv/bin/python -m pytest -v` → all PASS.

- [ ] **Step 6: Commit.**

```bash
git rm graph/nodes/.gitkeep && git add graph tests/test_seed.py
git commit -m "feat: seed graph — 24 fictional French banking-IT nodes with deliberate traps"
```

---

### Task 9: README v1

**Files:**
- Modify: `README.md` (replace the placeholder entirely)

- [ ] **Step 1: Write the README** (English; kickoff §7 mandates it as a deliverable). Required sections, in order:

1. **Title + one-liner** ("An AI scoping runtime for projects that don't exist in isolation.") + 2-3 status badges-free honest line: design public, MVP in progress.
2. **The five-line pitch** (verbatim from AGENTS.md north star).
3. **Why this project exists** — condensed pivot story, link to ADR 0000. The portfolio narrative: use-case-assistant → scopegraph → ecosystem-foundry, "three links, zero redundancy".
4. **How it works** — the 6-step workflow (kickoff §5) + a small Mermaid diagram of the flow `idea → ecosystem graph → grounded links → challenge → dossier → write-back`.
5. **The demo scenario** — abridged BNPL story (kickoff §5): what a naive assistant does vs what scopegraph surfaces (SCA inheritance, single fraud-scoring point, credit domain, 2-hop TPE constraint), and the killer move (second scoping sees the first).
6. **What keeps it honest** — grounding gate (every claim cites a node ID), runtime authority, human validation, hermetic tests.
7. **Language note** — demo, seed data and dossiers are French (French banking domain — by design); code and docs are English.
8. **The seeded registry statement** (verbatim requirement, kickoff §5.1): "the ecosystem registry is seeded; ingestion from documents is the roadmap (see ecosystem-foundry)". All entities fictional.
9. **Getting started** — `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`, run tests (`pytest`), explore docs (`./scripts/docs-list`).
10. **Roadmap** — W2-W4 milestones (spec §8) then ecosystem-foundry (kickoff §8).

- [ ] **Step 2: Verify.** Proofread rendered output (`gh markdown-preview` not required — read it raw); check every internal link resolves (`docs/adr/0000-pivot-from-mas.md`, etc.).

- [ ] **Step 3: Commit.**

```bash
git add README.md && git commit -m "docs: README v1 — positioning, pivot story, demo scenario"
```

---

### Task 10: Eval case drafts

**Files:**
- Create: `docs/eval/cases.md`
- Delete: `docs/eval/.gitkeep`

- [ ] **Step 1: Write the 5 cases** (French content, file gets front matter — it is an active doc). For each case: `Entrée` (the fuzzy idea, 1-2 sentences), `Dépendances critiques attendues` (node ids + why), `Pourquoi un prompt naïf le rate` (2 hops away / buried in a decision / wrong domain framing). The 5 cases:

```markdown
---
summary: 5 eval cases (French) where scopegraph must beat a naive well-written LLM prompt
read_when:
  - running or extending the evaluation (W4)
  - checking what the retrieval and challenge steps must catch
---

# Cas d'évaluation — scopegraph vs prompt naïf

Méthode : la même entrée est donnée (a) à un prompt naïf bien écrit ("tu es un assistant de
cadrage expérimenté…") et (b) à scopegraph. Réussite = scopegraph cite la dépendance critique
avec son node ID ; le prompt naïf ne peut pas la connaître ou ne la déduit pas.

## Cas 1 — BNPL mobile (le scénario démo)
Entrée : « Ajouter une option de paiement en 3 fois dans l'app mobile. »
Attendu : dec-reutilisation-sca (héritée), dec-scoring-unique (pas de scoring parallèle),
domaine credit (produit de crédit réglementé), sys-logiciel-tpe + dec-releases-tpe-trimestrielles
(à 2 sauts via monetique, si acceptation magasin), risk-kyc-obsolete.
Piège pour le naïf : la chaîne TPE à 2 sauts et la décision scoring enfouie.

## Cas 2 — Cash-back commerçants
[Entrée + attendus : sys-moteur-autorisation, dec-gel-evolutions-monetique (le gel bloque le
calendrier !), con-pci-dss, collision de périmètre avec le cas 1 après write-back.]

## Cas 3 — Relèvement des plafonds de virement instantané
[Attendus : con-lcb-ft-screening, risk-contournement-plafonds-ip, dec-scoring-unique via
sys-passerelle-ip.]

## Cas 4 — Assistant IA de réponse aux réclamations
[Attendus : con-ai-act (classification de risque), sys-referentiel-client + risk-kyc-obsolete,
con-standard-api-interne.]

## Cas 5 — Refonte de l'onboarding client digital
[Attendus : sys-referentiel-client, risk-kyc-obsolete, proj-programme-dsp2 (SCA à l'entrée en
relation via dec-reutilisation-sca), domaine lcb-ft (screening entrée en relation).]
```

(Cases 2–5: write them out fully in the same shape as Case 1 — Entrée as a quoted sentence, the listed node ids as attendus with one justification each, and the explicit "piège pour le naïf" line.)

- [ ] **Step 2: Verify.** `./scripts/docs-list` → `eval/cases.md` listed clean. Cross-check every node id cited exists in `graph/nodes/` (`ls graph/nodes/`).

- [ ] **Step 3: Commit.**

```bash
git rm docs/eval/.gitkeep && git add docs/eval/cases.md
git commit -m "docs: draft 5 eval cases — scopegraph vs naive prompt"
```

---

### Task 11: Close the chantier

**Files:**
- Modify: `docs/BUILD-ORDER.md`

- [ ] **Step 1: Full verification.** Run: `.venv/bin/python -m pytest -v` (expect ~20 PASS, 0 fail) and `.venv/bin/ruff check .` (clean) and `./scripts/docs-list` (all active docs clean).

- [ ] **Step 2: Update BUILD-ORDER.md.** Move W1 items to "Current state" (with date), promote W2 (retrieval: Embedder protocol + Chroma indexing + hybrid scorer + iterative MAPPING loop + first web screens) into "Next chantier" with the same level of detail W1 had, referencing spec §8.

- [ ] **Step 3: Commit.**

```bash
git add docs/BUILD-ORDER.md && git commit -m "docs: BUILD-ORDER — W1 foundations done, W2 retrieval next"
```

---

## Self-review notes

- **Spec coverage (W1 slice):** ADRs ✓ (Tasks 1-2) · models/loader/service ✓ (Tasks 3-7, incl. fail-fast load errors from spec §6) · seed with all four traps ✓ (Task 8: alias, superseded, contradiction, 2-hop chain — each has a test) · README ✓ (Task 9) · eval drafts ✓ (Task 10). W2+ items (retrieval, embeddings, web, LLM) intentionally absent — separate plan.
- **Type consistency:** `k_hop` returns `dict[str, list[Edge]]` and Task 8's test uses `reached["con-pci-dss"]` as a path list ✓; `neighbors` returns `list[tuple[Edge, Node]]` used as `(edge, node)` everywhere ✓; node `severity`/`likelihood`/`impact` are plain `Literal` strings, tests compare to `"high"` ✓.
- **Conventions:** all test commands use `.venv/bin/python -m pytest` (the venv created at bootstrap); commits follow AGENTS.md prefixes; French content only inside `graph/`, `docs/eval/cases.md`, and YAML test fixtures.
