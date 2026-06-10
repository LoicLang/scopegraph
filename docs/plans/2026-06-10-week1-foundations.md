# Week 1 — Foundations Implementation Plan (feature-grain schema)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the W1 foundations on the refined schema: both ADRs, schema v1 as Pydantic models (7 node types / 7 edge types), domain vocabulary as graph data, fail-fast loader with topology validation, in-memory GraphService, the 72-node French banking-IT seed with its 7 deliberate traps, README v1, and the 6 eval case drafts.

**Architecture:** Schema v1 lives in `core/graph/models.py` as a frozen Pydantic discriminated union plus a `TOPOLOGY` table (the contract with ecosystem-foundry, ADR 0001). The domain vocabulary is ecosystem DATA (`graph/domains.yaml`), not code. A fail-fast loader turns `graph/` into an in-memory `GraphService` (lookup, neighbors, k-hop BFS with path provenance), enforcing: domains in vocabulary, edge endpoint existence, edge topology, one `PART_OF` parent per feature, cancelled projects restricted to `RELATES_TO`. Seed content is French; code/docs are English.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, pytest. No LLM, no embeddings, no web in W1.

**Context to read first:** `docs/specs/2026-06-10-graph-schema-fine-grain-design.md` (THE schema authority), `docs/specs/2026-06-09-scopegraph-mvp-design.md`, `docs/project-kickoff.md` §1 (pivot story) and §5 (demo), `AGENTS.md` (hard rules — hermetic tests, fictional entities only, language split).

---

## File structure

```
core/graph/__init__.py        # re-exports the public surface
core/graph/models.py          # schema v1: EdgeType, TOPOLOGY, Edge, 7 node types (frozen contract)
core/graph/loader.py          # domains.yaml + YAML -> validated objects; GraphLoadError with file context
core/graph/service.py         # GraphService: get_node, all_nodes, all_edges, neighbors, k_hop
tests/test_models.py
tests/test_loader.py
tests/test_service.py
tests/test_seed.py            # integration: the real seed graph + the 7 trap assertions
graph/domains.yaml            # controlled vocabulary (ecosystem data)
graph/nodes/<72 files>.yaml   # seed nodes (French content), filename = <id>.yaml
graph/edges.yaml              # seed edges (~100)
docs/adr/0000-pivot-from-mas.md
docs/adr/0001-graph-schema-v1.md
docs/eval/cases.md            # 6 eval case drafts (French)
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

### Task 2: ADR 0001 — graph schema v1 (feature grain)

**Files:**
- Create: `docs/adr/0001-graph-schema-v1.md`

- [ ] **Step 1: Write the ADR.** Source: `docs/specs/2026-06-10-graph-schema-fine-grain-design.md` §3 (NOT kickoff §4, which is superseded). This ADR is the canonical home of the schema. Structure:

```markdown
---
summary: ADR 0001 — graph schema v1 (frozen contract): 7 node types, 7 edge types with
  topology matrix, domain vocabulary as ecosystem data
read_when:
  - touching core/graph/models.py, core/graph/loader.py, or any YAML under graph/
  - proposing any schema or domain-vocabulary change (requires a new ADR)
---

# ADR 0001 — Graph schema v1

Date: 2026-06-10 · Status: accepted

## Context
[~100 words: the schema is the only contact point between scopegraph (consumer) and the future
ecosystem-foundry (producer). Drift would silently break the contract → frozen, changes need an
ADR. The schema must be domain-agnostic (universal across IT estates); only the domain
vocabulary and the graph content are environment-specific.]

## Decision
[Reproduce from spec §3, in ADR voice:
- the 7 node types with their fields (System, Feature, BusinessObject, Project, Decision,
  Constraint, Risk); shared fields incl. id prefixes (sys- feat- obj- proj- dec- con- risk-)
- the 7 edge types and the full allowed-topology matrix; RELATES_TO is last resort and MUST
  carry a note; PART_OF: exactly one parent per feature
- shared-constraint semantics: a Constraint on a BusinessObject binds every feature that
  OPERATES_ON it; on a Feature, it is feature-specific
- cancelled projects: only RELATES_TO edges allowed (memorial influence, not structural)
- the domain vocabulary lives in graph/domains.yaml (per-ecosystem data, governed by ADR),
  validated at load time
- storage: one YAML per node in graph/nodes/, edges in graph/edges.yaml, in-memory at runtime]

## Consequences
[Bullets: Pydantic models + TOPOLOGY table in core/graph/models.py are the executable form of
this ADR; all graph rules enforced at load time (fail fast); ecosystem-foundry output must
validate against these models unchanged; porting scopegraph to another estate = swapping
graph/domains.yaml and graph content, zero code change.]
```

- [ ] **Step 2: Verify.** Run: `./scripts/docs-list` → both ADRs listed clean.

- [ ] **Step 3: Commit.**

```bash
git add docs/adr/ && git commit -m "docs: ADR 0001 — graph schema v1 (frozen contract, feature grain)"
```

---

### Task 3: Schema models — EdgeType, TOPOLOGY, Edge

**Files:**
- Create: `core/graph/models.py`, `core/graph/__init__.py`
- Test: `tests/test_models.py`

Note: the domain vocabulary is NOT in this module (it is graph data — Task 5 loads it).

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_models.py
import pytest
from pydantic import ValidationError

from core.graph.models import TOPOLOGY, Edge, EdgeType


def test_edge_type_has_the_seven_adr_0001_members():
    assert {e.value for e in EdgeType} == {
        "DEPENDS_ON", "PART_OF", "OPERATES_ON", "PRODUCED",
        "CONSTRAINS", "SUPERSEDES", "RELATES_TO",
    }


def test_topology_covers_every_type_except_relates_to():
    assert set(TOPOLOGY) == set(EdgeType) - {EdgeType.RELATES_TO}
    assert ("feature", "system") in TOPOLOGY[EdgeType.PART_OF]
    assert ("system", "business_object") in TOPOLOGY[EdgeType.OPERATES_ON]


def test_edge_valid():
    edge = Edge(
        source_id="feat-mobile-ajout-benef",
        target_id="feat-benef-api",
        type=EdgeType.DEPENDS_ON,
        evidence="description of feat-mobile-ajout-benef",
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
"""Graph schema v1 — the frozen contract (ADR 0001). Changes require a new ADR.

The domain vocabulary is NOT defined here: it is ecosystem data, loaded from
graph/domains.yaml and enforced by the loader.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
CREATED_FROM_PATTERN = r"^(seed|scoping:[a-z0-9-]+|ingestion:[a-z0-9-]+)$"


class EdgeType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    PART_OF = "PART_OF"
    OPERATES_ON = "OPERATES_ON"
    PRODUCED = "PRODUCED"
    CONSTRAINS = "CONSTRAINS"
    SUPERSEDES = "SUPERSEDES"
    RELATES_TO = "RELATES_TO"


# Allowed (source node type, target node type) pairs per edge type (ADR 0001).
# RELATES_TO is deliberately absent: it is the any-to-any last resort.
TOPOLOGY: dict[EdgeType, frozenset[tuple[str, str]]] = {
    EdgeType.PART_OF: frozenset({("feature", "system")}),
    EdgeType.OPERATES_ON: frozenset({
        ("feature", "business_object"),
        ("system", "business_object"),
    }),
    EdgeType.DEPENDS_ON: frozenset({
        ("system", "system"),
        ("feature", "feature"),
        ("feature", "system"),
    }),
    EdgeType.CONSTRAINS: frozenset({
        (source, target)
        for source in ("constraint", "decision")
        for target in ("system", "feature", "business_object", "project")
    }),
    EdgeType.PRODUCED: frozenset({
        ("project", "system"),
        ("project", "feature"),
        ("project", "decision"),
    }),
    EdgeType.SUPERSEDES: frozenset({("decision", "decision")}),
}


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
from core.graph.models import TOPOLOGY, Edge, EdgeType

__all__ = ["TOPOLOGY", "Edge", "EdgeType"]
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_models.py -v` → 5 PASS.

- [ ] **Step 5: Commit.**

```bash
git add core/graph tests/test_models.py
git commit -m "feat: graph schema v1 — edge types, topology matrix, Edge model"
```

---

### Task 4: Schema models — the seven node types

**Files:**
- Modify: `core/graph/models.py`, `core/graph/__init__.py`
- Test: `tests/test_models.py` (append)

- [ ] **Step 1: Append the failing tests.**

```python
# append to tests/test_models.py
import datetime

from pydantic import TypeAdapter

from core.graph.models import BusinessObject, Feature, Node, System


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


def test_feature_valid():
    feat = Feature(
        id="feat-benef-ajout",
        name="Ajout de bénéficiaire",
        description="Crée un bénéficiaire avec IBAN, BIC et libellé.",
        parameters=["IBAN", "BIC", "libellé"],
        domains=["referentiel-client"],
    )
    assert feat.type == "feature"


def test_business_object_valid():
    obj = BusinessObject(
        id="obj-beneficiaire",
        name="Bénéficiaire",
        description="Tiers destinataire de virements, rattaché à un client.",
        steward_team="Équipe Référentiels",
        domains=["referentiel-client"],
    )
    assert obj.type == "business_object"


def test_node_union_discriminates_on_type():
    adapter = TypeAdapter(Node)
    node = adapter.validate_python({
        "type": "feature",
        "id": "feat-ip-emission",
        "name": "Émission de virement instantané",
        "description": "Émet un virement SEPA Inst en moins de 10 secondes.",
        "domains": ["paiement-instantane"],
    })
    assert isinstance(node, Feature)
    assert node.parameters == []


def test_node_requires_at_least_one_domain():
    with pytest.raises(ValidationError):
        System(id="sys-x", name="X", description="d", owner_team="t", domains=[])
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_models.py -v` → FAIL: `ImportError: cannot import name 'BusinessObject'`.

- [ ] **Step 3: Implement — append to `core/graph/models.py`.**

```python
import datetime
from typing import Annotated, Literal, Union


class NodeBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=SLUG_PATTERN)
    domains: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    created_from: str = Field(default="seed", pattern=CREATED_FROM_PATTERN)


class System(NodeBase):
    type: Literal["system"] = "system"
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    owner_team: str
    data_quality_notes: str = ""
    known_risks: list[str] = Field(default_factory=list)


class Feature(NodeBase):
    type: Literal["feature"] = "feature"
    name: str
    description: str
    parameters: list[str] = Field(default_factory=list)


class BusinessObject(NodeBase):
    type: Literal["business_object"] = "business_object"
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    steward_team: str = ""


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
    Union[System, Feature, BusinessObject, Project, Decision, Constraint, Risk],
    Field(discriminator="type"),
]
```

Update `core/graph/__init__.py`:

```python
from core.graph.models import (
    TOPOLOGY,
    BusinessObject,
    Constraint,
    Decision,
    Edge,
    EdgeType,
    Feature,
    Node,
    Project,
    Risk,
    System,
)

__all__ = [
    "TOPOLOGY", "BusinessObject", "Constraint", "Decision", "Edge", "EdgeType",
    "Feature", "Node", "Project", "Risk", "System",
]
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_models.py -v` → 10 PASS. Also run `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit.**

```bash
git add core/graph tests/test_models.py
git commit -m "feat: graph schema v1 — seven node types as discriminated union"
```

---

### Task 5: YAML loader — vocabulary, nodes, edges

**Files:**
- Create: `core/graph/loader.py`
- Test: `tests/test_loader.py`

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_loader.py
import pytest

from core.graph.loader import GraphLoadError, load_graph

DOMAINS_YAML = "domains: [monetique, referentiel-client, banque-en-ligne]\n"

SYSTEM_YAML = """
type: system
id: sys-gestion-beneficiaires
name: Gestion des bénéficiaires
aliases: [BENEFGEST]
description: Référentiel et règles de gestion des bénéficiaires de virement.
owner_team: Équipe Référentiels
domains: [referentiel-client]
"""

FEATURE_YAML = """
type: feature
id: feat-benef-ajout
name: Ajout de bénéficiaire
description: Crée un bénéficiaire avec IBAN, BIC et libellé.
parameters: [IBAN, BIC, libellé]
domains: [referentiel-client]
"""

OBJECT_YAML = """
type: business_object
id: obj-beneficiaire
name: Bénéficiaire
description: Tiers destinataire de virements, rattaché à un client.
steward_team: Équipe Référentiels
domains: [referentiel-client]
"""

PART_OF_EDGE = """
  - source_id: feat-benef-ajout
    target_id: sys-gestion-beneficiaires
    type: PART_OF
"""


def write_graph(tmp_path, node_yamls, edges_yaml="edges: []\n", domains_yaml=DOMAINS_YAML):
    nodes_dir = tmp_path / "nodes"
    nodes_dir.mkdir()
    for i, content in enumerate(node_yamls):
        (nodes_dir / f"node{i}.yaml").write_text(content, encoding="utf-8")
    (tmp_path / "edges.yaml").write_text(edges_yaml, encoding="utf-8")
    (tmp_path / "domains.yaml").write_text(domains_yaml, encoding="utf-8")
    return tmp_path


def test_loads_nodes_and_edges(tmp_path):
    edges = "edges:\n" + PART_OF_EDGE
    nodes, edge_list = load_graph(
        write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges)
    )
    assert set(nodes) == {"sys-gestion-beneficiaires", "feat-benef-ajout"}
    assert len(edge_list) == 1


def test_missing_domains_file_fails(tmp_path):
    graph_dir = write_graph(tmp_path, [SYSTEM_YAML])
    (graph_dir / "domains.yaml").unlink()
    with pytest.raises(GraphLoadError, match="domains.yaml"):
        load_graph(graph_dir)


def test_unknown_domain_fails_with_filename(tmp_path):
    bad = SYSTEM_YAML.replace(
        "domains: [referentiel-client]", "domains: [blockchain]"
    )
    with pytest.raises(GraphLoadError, match="node0.yaml"):
        load_graph(write_graph(tmp_path, [bad]))


def test_duplicate_id_fails_with_filename(tmp_path):
    with pytest.raises(GraphLoadError, match="node1.yaml"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, SYSTEM_YAML]))


def test_edge_to_unknown_node_fails(tmp_path):
    edges = """
edges:
  - source_id: feat-benef-ajout
    target_id: sys-fantome
    type: PART_OF
"""
    with pytest.raises(GraphLoadError, match="sys-fantome"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges))
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_loader.py -v` → FAIL: no module `core.graph.loader`.

- [ ] **Step 3: Implement.**

```python
# core/graph/loader.py
"""Load the YAML graph (domains.yaml + nodes/*.yaml + edges.yaml) into schema-v1 objects.

Fail-fast: any invalid file aborts the load with the offending path in the error.
All graph rules of ADR 0001 are enforced here: domain vocabulary, edge endpoint
existence, edge topology, PART_OF cardinality, cancelled-project restrictions.
"""

from collections import Counter
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from core.graph.models import TOPOLOGY, Edge, EdgeType, Node

_NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)


class GraphLoadError(Exception):
    """The graph on disk violates schema v1 (ADR 0001)."""


def load_domains(graph_dir: Path) -> frozenset[str]:
    path = graph_dir / "domains.yaml"
    if not path.exists():
        raise GraphLoadError(f"{path}: missing domain vocabulary file")
    domains = (_read_yaml(path) or {}).get("domains") or []
    if not domains:
        raise GraphLoadError(f"{path}: empty domain vocabulary")
    return frozenset(domains)


def load_graph(graph_dir: Path) -> tuple[dict[str, Node], list[Edge]]:
    vocabulary = load_domains(graph_dir)

    nodes: dict[str, Node] = {}
    for path in sorted((graph_dir / "nodes").glob("*.yaml")):
        data = _read_yaml(path)
        try:
            node = _NODE_ADAPTER.validate_python(data)
        except ValidationError as exc:
            raise GraphLoadError(f"{path}: invalid node: {exc}") from exc
        if node.id in nodes:
            raise GraphLoadError(f"{path}: duplicate node id '{node.id}'")
        unknown = set(node.domains) - vocabulary
        if unknown:
            raise GraphLoadError(
                f"{path}: unknown domains {sorted(unknown)} "
                "(vocabulary: graph/domains.yaml, governed by ADR)"
            )
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
        _check_topology(edge, nodes, edges_path, index)
        edges.append(edge)

    _check_graph_rules(nodes, edges)
    return nodes, edges


def _check_topology(
    edge: Edge, nodes: dict[str, Node], path: Path, index: int
) -> None:
    if edge.type is EdgeType.RELATES_TO:
        return
    pair = (nodes[edge.source_id].type, nodes[edge.target_id].type)
    if pair not in TOPOLOGY[edge.type]:
        raise GraphLoadError(
            f"{path}: edge #{index}: {edge.type.value} not allowed "
            f"from '{pair[0]}' to '{pair[1]}' (ADR 0001 topology)"
        )


def _check_graph_rules(nodes: dict[str, Node], edges: list[Edge]) -> None:
    parent_counts = Counter(
        edge.source_id for edge in edges if edge.type is EdgeType.PART_OF
    )
    for node in nodes.values():
        if node.type == "feature" and parent_counts.get(node.id, 0) != 1:
            raise GraphLoadError(
                f"feature '{node.id}' must have exactly one PART_OF edge "
                f"(found {parent_counts.get(node.id, 0)})"
            )

    cancelled = {
        node.id
        for node in nodes.values()
        if node.type == "project" and node.status == "cancelled"
    }
    for edge in edges:
        if edge.type is EdgeType.RELATES_TO:
            continue
        if edge.source_id in cancelled or edge.target_id in cancelled:
            raise GraphLoadError(
                f"cancelled project may only carry RELATES_TO edges: "
                f"{edge.source_id} -{edge.type.value}-> {edge.target_id}"
            )


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GraphLoadError(f"{path}: invalid YAML: {exc}") from exc
```

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_loader.py -v` → 5 PASS. (One PART_OF edge satisfies the cardinality rule in the first test; the rule's negative cases come in Task 6.)

- [ ] **Step 5: Commit.**

```bash
git add core/graph/loader.py tests/test_loader.py
git commit -m "feat: fail-fast YAML graph loader with vocabulary validation"
```

---

### Task 6: Loader — topology and graph-rule negative cases

**Files:**
- Modify: `core/graph/loader.py` (only if a test exposes a bug — the rules are already implemented)
- Test: `tests/test_loader.py` (append)

- [ ] **Step 1: Append the failing-or-passing tests** (they exercise code written in Task 5; expect them to pass — if one fails, fix the loader).

```python
# append to tests/test_loader.py


def test_topology_violation_fails(tmp_path):
    edges = """
edges:
  - source_id: sys-gestion-beneficiaires
    target_id: feat-benef-ajout
    type: PART_OF
"""
    graph = write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], "edges: []\n")
    (graph / "edges.yaml").write_text(edges, encoding="utf-8")
    with pytest.raises(GraphLoadError, match="topology"):
        load_graph_with_orphan_feature_allowed(graph)


def load_graph_with_orphan_feature_allowed(graph_dir):
    # The topology error must fire BEFORE the PART_OF-cardinality error,
    # so this helper just calls load_graph directly.
    return load_graph(graph_dir)


def test_feature_without_parent_fails(tmp_path):
    with pytest.raises(GraphLoadError, match="exactly one PART_OF"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML]))


def test_feature_with_two_parents_fails(tmp_path):
    edges = "edges:\n" + PART_OF_EDGE + PART_OF_EDGE
    with pytest.raises(GraphLoadError, match="exactly one PART_OF"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, FEATURE_YAML], edges))


CANCELLED_PROJECT_YAML = """
type: project
id: proj-refonte-parcours-beneficiaire
name: Refonte du parcours bénéficiaire
description: Tentative de refonte abandonnée en 2023.
status: cancelled
owner_team: Équipe Canaux
outcomes: Migration du stock jugée infaisable sans fenêtre de gel.
domains: [banque-en-ligne]
"""


def test_cancelled_project_with_structural_edge_fails(tmp_path):
    edges = """
edges:
  - source_id: proj-refonte-parcours-beneficiaire
    target_id: sys-gestion-beneficiaires
    type: PRODUCED
"""
    with pytest.raises(GraphLoadError, match="cancelled"):
        load_graph(write_graph(tmp_path, [SYSTEM_YAML, CANCELLED_PROJECT_YAML], edges))


def test_cancelled_project_relates_to_is_allowed(tmp_path):
    edges = """
edges:
  - source_id: proj-refonte-parcours-beneficiaire
    target_id: obj-beneficiaire
    type: RELATES_TO
    note: tentative de refonte abandonnée en 2023 — migration du stock infaisable
"""
    nodes, edge_list = load_graph(
        write_graph(tmp_path, [SYSTEM_YAML, OBJECT_YAML, CANCELLED_PROJECT_YAML], edges)
    )
    assert len(edge_list) == 1
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_loader.py -v` → 10 PASS (fix the loader if any rule misfires; the error precedence is: per-edge topology errors during edge iteration, then graph-wide rules).

- [ ] **Step 3: Commit.**

```bash
git add tests/test_loader.py core/graph/loader.py
git commit -m "test: loader topology and graph-rule negative cases"
```

---

### Task 7: GraphService — lookup and neighbors

**Files:**
- Create: `core/graph/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing tests.** The fixture mirrors the founding trap shape: a feature reaches a shared constraint through a business object.

```python
# tests/test_service.py
import pytest

from core.graph.models import (
    BusinessObject, Constraint, Edge, EdgeType, Feature, System,
)
from core.graph.service import GraphService, UnknownNodeError


@pytest.fixture()
def service() -> GraphService:
    nodes = [
        System(
            id="sys-gestion-beneficiaires",
            name="Gestion des bénéficiaires",
            description="Référentiel des bénéficiaires.",
            owner_team="Référentiels",
            domains=["referentiel-client"],
        ),
        Feature(
            id="feat-benef-ajout",
            name="Ajout de bénéficiaire",
            description="Crée un bénéficiaire.",
            domains=["referentiel-client"],
        ),
        Feature(
            id="feat-mobile-ajout-benef",
            name="Ajout de bénéficiaire (mobile)",
            description="Crée un bénéficiaire depuis l'app mobile.",
            domains=["banque-en-ligne"],
        ),
        BusinessObject(
            id="obj-beneficiaire",
            name="Bénéficiaire",
            description="Tiers destinataire de virements.",
            domains=["referentiel-client"],
        ),
        Constraint(
            id="con-carence-beneficiaire-48h",
            title="Délai de carence bénéficiaire",
            statement="Tout nouveau bénéficiaire est inutilisable pendant 48 heures.",
            source="politique interne fraude",
            severity="high",
            domains=["referentiel-client"],
        ),
        System(
            id="sys-isole",
            name="Système isolé",
            description="Aucun lien.",
            owner_team="Autre",
            domains=["referentiel-client"],
        ),
    ]
    edges = [
        Edge(source_id="feat-benef-ajout", target_id="sys-gestion-beneficiaires",
             type=EdgeType.PART_OF),
        Edge(source_id="feat-benef-ajout", target_id="obj-beneficiaire",
             type=EdgeType.OPERATES_ON),
        Edge(source_id="feat-mobile-ajout-benef", target_id="obj-beneficiaire",
             type=EdgeType.OPERATES_ON),
        Edge(source_id="con-carence-beneficiaire-48h", target_id="obj-beneficiaire",
             type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def test_get_node(service):
    assert service.get_node("con-carence-beneficiaire-48h").severity == "high"


def test_get_unknown_node_raises(service):
    with pytest.raises(UnknownNodeError, match="sys-fantome"):
        service.get_node("sys-fantome")


def test_neighbors_are_bidirectional(service):
    hits = service.neighbors("obj-beneficiaire")
    ids = {node.id for _, node in hits}
    assert ids == {
        "feat-benef-ajout", "feat-mobile-ajout-benef", "con-carence-beneficiaire-48h",
    }


def test_neighbors_filter_by_edge_type(service):
    hits = service.neighbors("obj-beneficiaire", edge_types={EdgeType.CONSTRAINS})
    assert [node.id for _, node in hits] == ["con-carence-beneficiaire-48h"]


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

### Task 8: GraphService — k-hop traversal with path provenance

**Files:**
- Modify: `core/graph/service.py`, `core/graph/__init__.py`
- Test: `tests/test_service.py` (append)

- [ ] **Step 1: Append the failing tests.** Provenance matters: W2 retrieval must say "included via `obj-beneficiaire` → CONSTRAINS".

```python
# append to tests/test_service.py


def test_k_hop_finds_constraint_through_shared_object(service):
    # The founding trap shape: from the mobile feature, the shared rule is 2 hops away.
    reached = service.k_hop("feat-mobile-ajout-benef", k=2)
    assert "con-carence-beneficiaire-48h" in reached
    path = reached["con-carence-beneficiaire-48h"]
    assert len(path) == 2
    assert path[0].type == EdgeType.OPERATES_ON
    assert path[1].type == EdgeType.CONSTRAINS


def test_k_hop_respects_radius(service):
    reached = service.k_hop("feat-mobile-ajout-benef", k=1)
    assert set(reached) == {"obj-beneficiaire"}


def test_k_hop_excludes_start_and_unreachable(service):
    reached = service.k_hop("feat-mobile-ajout-benef", k=3)
    assert "feat-mobile-ajout-benef" not in reached
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

- [ ] **Step 4: Update `core/graph/__init__.py`** — add `GraphService`, `UnknownNodeError`, `GraphLoadError`, `load_graph`, `load_domains` to imports and `__all__`.

- [ ] **Step 5: Run to verify pass.** `.venv/bin/python -m pytest -v` → all PASS. `.venv/bin/ruff check .` → clean.

- [ ] **Step 6: Commit.**

```bash
git add core/graph tests/test_service.py
git commit -m "feat: k-hop BFS traversal with shortest-path provenance"
```

---

### Task 9: Seed part 1 — domains, systems, business objects

**Files:**
- Create: `graph/domains.yaml`, `graph/nodes/<id>.yaml` × 15 (9 systems + 6 objects)
- Delete: `graph/nodes/.gitkeep`

All content **French**, all entities **fictional** (AGENTS.md rules 5–6). Every `description` is 2–4 sentences rich enough to embed. Filename = `<id>.yaml`. NO test runs against the real `graph/` until Task 12 (the graph is incomplete until then — features without PART_OF would fail the load).

- [ ] **Step 1: Write `graph/domains.yaml`.**

```yaml
# Controlled domain vocabulary (ADR 0001): extensible only via a new ADR.
domains:
  - monetique            # card payments: authorization, clearing, card lifecycle
  - tpe-acceptation      # POS terminals & merchant acceptance
  - paiement-instantane  # instant payment / SEPA Inst rails
  - dsp2-open-banking    # PSD2, SCA, APIs, TPP access
  - lcb-ft               # AML/CFT, fraud scoring, sanctions screening
  - credit               # consumer & mortgage credit
  - banque-en-ligne      # web & mobile banking front ends
  - referentiel-client   # customer master data, KYC
  - editique-reporting   # statements, regulatory reporting
  - socle-si             # shared infrastructure, core banking, standards
```

- [ ] **Step 2: Write the 9 system files.** Roster (id · alias · domains · content brief — write the French prose from the brief):

| id | alias | domains | brief |
|---|---|---|---|
| `sys-moteur-autorisation` | MONAUT, "moteur d'autorisation" | monetique | autorise chaque transaction carte en temps réel (plafonds, opposition, solde, règles réseau); chemin critique; known_risks: dette COBOL sur la tarification ← **alias trap** |
| `sys-logiciel-tpe` | PAYTERM | tpe-acceptation | logiciel embarqué de la flotte de terminaux; known_risks: fragmentation des versions firmware. Stays coarse (no features) |
| `sys-app-mobile` | MOBANK | banque-en-ligne | parcours clients particuliers (comptes, virements, bénéficiaires, crédit conso) |
| `sys-passerelle-ip` | FLUXINST | paiement-instantane | rails SEPA Inst, émission/réception < 10 s |
| `sys-scoring-fraude` | FRAUDSCORE | lcb-ft, monetique | scoring temps réel des paiements; le point de décision risque unique. Stays coarse |
| `sys-referentiel-client` | REFCLI | referentiel-client | données client et KYC; data_quality_notes: revues KYC en retard sur le stock ancien |
| `sys-core-banking` | LEDGERIS | socle-si | tenue de compte, positions, mouvements. Stays coarse |
| `sys-gestion-beneficiaires` | BENEFGEST | referentiel-client, banque-en-ligne | référentiel unique des bénéficiaires de virement et ses règles de gestion; expose la seule API d'écriture autorisée |
| `sys-moteur-credit` | CREDIFLOW | credit | octroi et gestion des crédits conso; règles d'éligibilité et scoring d'octroi. Stays coarse |

Template (complete example for the alias-trap node — every system file follows this shape):

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

- [ ] **Step 3: Write the 6 business-object files.** Roster:

| id | steward_team | domains | brief |
|---|---|---|---|
| `obj-beneficiaire` | Équipe Référentiels | referentiel-client, banque-en-ligne | tiers destinataire de virements rattaché à un client; aliases [bénéficiaire de virement] |
| `obj-virement-instantane` | Équipe Paiements | paiement-instantane | ordre de virement SEPA Inst, du dépôt à l'irrévocabilité |
| `obj-dossier-client-kyc` | Équipe Référentiels | referentiel-client, lcb-ft | dossier de connaissance client (identité, justificatifs, revue périodique) |
| `obj-transaction-carte` | Équipe Monétique | monetique | transaction carte de l'autorisation au clearing |
| `obj-contrat-credit` | Équipe Crédit | credit | contrat de crédit conso, de la simulation au remboursement |
| `obj-alerte-fraude` | Équipe LCB-FT | lcb-ft | alerte émise par le scoring, qualifiée par un analyste |

Object template:

```yaml
# graph/nodes/obj-beneficiaire.yaml
type: business_object
id: obj-beneficiaire
name: Bénéficiaire
aliases: [bénéficiaire de virement]
description: >-
  Tiers destinataire de virements, rattaché à un client titulaire. Porte l'IBAN,
  le BIC, un libellé et l'état d'activation. Toute création ou modification est
  soumise aux règles de sécurité partagées (carence, SCA, sanctions).
steward_team: Équipe Référentiels
domains: [referentiel-client, banque-en-ligne]
tags: [donnee-sensible]
created_from: seed
```

- [ ] **Step 4: Sanity check (no pytest yet).** `ls graph/nodes/ | wc -l` → 15. `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit.**

```bash
git rm graph/nodes/.gitkeep && git add graph
git commit -m "feat: seed part 1 — domain vocabulary, 9 systems, 6 business objects"
```

---

### Task 10: Seed part 2 — the 24 features

**Files:**
- Create: `graph/nodes/<id>.yaml` × 24

Feature roster. For each: `description` 2–3 French sentences from the brief, `parameters` as listed, `domains` as listed. The PART_OF / OPERATES_ON / DEPENDS_ON columns are written into `graph/edges.yaml` in Task 12 — NOT here (keep them in mind for description wording: a feature's description should textually justify its edges, since edge `evidence` cites it).

**BENEFGEST (5)** — all OPERATES_ON `obj-beneficiaire`, domains `[referentiel-client, banque-en-ligne]`:

| id | parameters | brief |
|---|---|---|
| `feat-benef-ajout` | IBAN, BIC, libellé, canal | crée un bénéficiaire; déclenche carence 48 h, SCA, vérification sanctions |
| `feat-benef-modification` | IBAN, libellé | modifier l'IBAN relance la carence — équivaut à une re-création côté risque |
| `feat-benef-suppression` | identifiant bénéficiaire | suppression logique, conservation pour traçabilité |
| `feat-benef-consultation` | identifiant client | liste les bénéficiaires actifs d'un client avec leur état de carence |
| `feat-benef-api` | opérations CRUD exposées | la SEULE porte d'écriture autorisée sur les bénéficiaires (décision dec-ecriture-via-api-benef); contrat d'API conforme au standard interne |

**MOBANK (5)** — domains `[banque-en-ligne]` (+ second domain where noted):

| id | parameters | brief |
|---|---|---|
| `feat-mobile-ajout-benef` | IBAN, libellé | parcours mobile d'ajout de bénéficiaire; appelle feat-benef-api; OPERATES_ON obj-beneficiaire; hérite carence/SCA/sanctions |
| `feat-mobile-virement-ip` | montant, bénéficiaire, motif | virement instantané depuis le mobile; appelle feat-ip-emission; OPERATES_ON obj-virement-instantane; + domain paiement-instantane |
| `feat-mobile-souscription-credit` | montant, durée, revenus | souscription crédit conso en autonomie; dépend de sys-moteur-credit; OPERATES_ON obj-contrat-credit; + domain credit |
| `feat-mobile-consultation-comptes` | identifiant client | soldes et mouvements; dépend de sys-core-banking |
| `feat-mobile-activation-carte` | identifiant carte | activation et plafonds carte depuis le mobile; dépend de sys-moteur-autorisation; + domain monetique |

**FLUXINST (4)** — all OPERATES_ON `obj-virement-instantane`, domains `[paiement-instantane]`:

| id | parameters | brief |
|---|---|---|
| `feat-ip-emission` | IBAN bénéficiaire, montant | émet un SEPA Inst en < 10 s; appelle le scoring fraude avant émission |
| `feat-ip-reception` | référence de virement | réception et crédit en compte; contrôles de cohérence |
| `feat-ip-rappel-fonds` | référence, motif | recall interbancaire après émission frauduleuse ou erreur |
| `feat-ip-gestion-plafonds` | plafond, période | gestion des plafonds d'émission par client (défaut 15 k€, décision dec-plafond-ip-defaut) |

**MONAUT (5)** — all OPERATES_ON `obj-transaction-carte` except routage/tarification, domains `[monetique]`:

| id | parameters | brief |
|---|---|---|
| `feat-aut-temps-reel` | numéro de carte, montant, commerçant | décision d'autorisation < 100 ms; consulte le scoring fraude |
| `feat-aut-oppositions` | identifiant carte, motif | mise en opposition immédiate, propagation aux réseaux |
| `feat-aut-controle-plafonds` | plafonds par période | contrôle des plafonds carte à l'autorisation |
| `feat-aut-routage-reseaux` | réseau (CB, Visa, MC) | routage des demandes vers les réseaux; pas d'OPERATES_ON |
| `feat-aut-tarification` | grille tarifaire | calcul des commissions; modules COBOL historiques (le known_risk du système); pas d'OPERATES_ON |

**REFCLI (5)** — all OPERATES_ON `obj-dossier-client-kyc`, domains `[referentiel-client]` (+ lcb-ft where noted):

| id | parameters | brief |
|---|---|---|
| `feat-ref-creation-client` | identité, justificatifs | création du dossier client avec contrôles d'identité |
| `feat-ref-maj-kyc` | justificatifs, revenus | mise à jour et revue périodique du dossier KYC |
| `feat-ref-screening-periodique` | listes de sanctions | criblage périodique du stock client contre les listes; + domain lcb-ft |
| `feat-ref-fusion-doublons` | identifiants à fusionner | détection et fusion des dossiers client en double |
| `feat-ref-exposition` | API de consultation | expose le référentiel aux autres systèmes; toute consultation est tracée |

Feature template:

```yaml
# graph/nodes/feat-benef-ajout.yaml
type: feature
id: feat-benef-ajout
name: Ajout de bénéficiaire
description: >-
  Crée un bénéficiaire de virement pour un client titulaire : saisie de l'IBAN,
  du BIC et d'un libellé. La création déclenche le délai de carence de 48 heures,
  exige une authentification forte et soumet l'IBAN à la vérification sanctions.
parameters: [IBAN, BIC, libellé, canal]
domains: [referentiel-client, banque-en-ligne]
tags: [ecriture, donnee-sensible]
created_from: seed
```

- [ ] **Step 1: Write the 24 files** following the roster and template.

- [ ] **Step 2: Sanity check.** `ls graph/nodes/ | wc -l` → 39.

- [ ] **Step 3: Commit.**

```bash
git add graph/nodes
git commit -m "feat: seed part 2 — 24 features across the 5 zoomed systems"
```

---

### Task 11: Seed part 3 — projects, decisions, constraints, risks

**Files:**
- Create: `graph/nodes/<id>.yaml` × 33 (7 + 8 + 12 + 6)

- [ ] **Step 1: Write the 7 project files.**

| id | status | domains | brief |
|---|---|---|---|
| `proj-programme-dsp2` | done | dsp2-open-banking, monetique | programme de conformité DSP2; outcomes: a produit l'orchestration SCA réutilisable et la décision dec-reutilisation-sca |
| `proj-migration-flotte-tpe` | ongoing | tpe-acceptation | migration logicielle de la flotte de terminaux; mitigation principale du risque de fragmentation |
| `proj-lancement-paiement-instantane` | done | paiement-instantane | lancement des rails SEPA Inst; a produit FLUXINST |
| `proj-refonte-scoring-fraude` | done | lcb-ft | refonte du scoring; a produit la décision du point de décision unique |
| `proj-dedup-incidents` | done | socle-si | nettoyage et déduplication du référentiel d'incidents |
| `proj-api-beneficiaires` | done | referentiel-client | a produit feat-benef-api et la décision dec-ecriture-via-api-benef; outcomes: suppression des écritures directes en base |
| `proj-refonte-parcours-beneficiaire` | **cancelled** | banque-en-ligne, referentiel-client | refonte du parcours bénéficiaire abandonnée en 2023; outcomes: « migration du stock de bénéficiaires jugée infaisable sans fenêtre de gel des virements » ← **cancelled trap**; NO structural edges |

- [ ] **Step 2: Write the 8 decision files.**

| id | date | still_active | brief |
|---|---|---|---|
| `dec-reutilisation-sca` | 2023-05-15 | true | tout nouveau flux de paiement réutilise l'orchestration SCA du programme DSP2 |
| `dec-scoring-unique` | 2024-03-01 | true | le scoring fraude est l'unique point de décision risque paiement; remplace la décision par canal |
| `dec-scoring-par-canal-2021` | 2021-09-01 | **false** | chaque canal portait son scoring ← **superseded trap** |
| `dec-releases-tpe-trimestrielles` | 2022-11-01 | true | mises à jour TPE trimestrielles, pas de hors-cycle |
| `dec-gel-evolutions-monetique` | 2026-01-15 | true | gel des évolutions non réglementaires sur MONAUT pendant la migration TPE ← **contradiction trap** vs dec-reutilisation-sca |
| `dec-ecriture-via-api-benef` | 2024-06-01 | true | toute création/modification de bénéficiaire passe par l'API BENEFGEST, écriture directe interdite |
| `dec-double-validation-entreprise` | 2025-02-01 | true | les virements initiés par un canal entreprise exigent une double validation |
| `dec-plafond-ip-defaut` | 2024-10-01 | true | plafond d'émission instantané par défaut 15 k€, modifiable uniquement via la gestion des plafonds FLUXINST |

- [ ] **Step 3: Write the 12 constraint files.**

| id | severity | domains | brief |
|---|---|---|---|
| `con-pci-dss` | high | monetique | tout composant manipulant des données carte entre dans le périmètre PCI DSS ← anchor of the 2-hop trap |
| `con-lcb-ft-screening` | high | lcb-ft, paiement-instantane | screening obligatoire sur tout nouveau rail de paiement |
| `con-standard-api-interne` | medium | socle-si | toute API interne respecte le standard d'API maison (auth, versionnage, traçabilité) |
| `con-ai-act` | medium | socle-si, lcb-ft | classification de risque des composants IA (AI Act) |
| `con-carence-beneficiaire-48h` | high | referentiel-client, banque-en-ligne | tout nouveau bénéficiaire (ou IBAN modifié) est inutilisable 48 h ← **shared rule** |
| `con-sca-ajout-beneficiaire` | high | referentiel-client, dsp2-open-banking | authentification forte exigée à l'ajout et à la modification ← **shared rule** |
| `con-verif-sanctions-creation` | high | referentiel-client, lcb-ft | IBAN et titulaire criblés contre les listes de sanctions à la création ← **shared rule** |
| `con-plafonds-virement-ip` | medium | paiement-instantane | plafonds d'émission par client et par période sur l'instantané |
| `con-rgpd-conservation` | medium | referentiel-client | durées de conservation des données client (RGPD) |
| `con-tracabilite-consultations` | medium | referentiel-client, socle-si | toute consultation du référentiel client est journalisée et auditable |
| `con-credit-conso-kyc` | high | credit, referentiel-client | tout octroi de crédit conso exige un dossier KYC à jour |
| `con-archivage-alertes-fraude` | medium | lcb-ft, editique-reporting | conservation 5 ans des alertes de fraude qualifiées |

- [ ] **Step 4: Write the 6 risk files.**

| id | likelihood/impact | domains | brief |
|---|---|---|---|
| `risk-kyc-obsolete` | high/medium | referentiel-client | une part des dossiers KYC n'a pas été revue depuis plus de 3 ans |
| `risk-fragmentation-tpe` | medium/high | tpe-acceptation | versions firmware hétérogènes sur la flotte |
| `risk-contournement-plafonds-ip` | low/high | paiement-instantane, lcb-ft | rafales de virements instantanés sous les plafonds unitaires |
| `risk-doublons-beneficiaires` | medium/medium | referentiel-client | stock historique de bénéficiaires saisis en double avant l'API unique |
| `risk-modele-fraude-derive` | medium/high | lcb-ft | modèle de scoring non recalibré depuis la refonte; dérive possible |
| `risk-indispo-service-sanctions` | low/high | lcb-ft, referentiel-client | le service externe de vérification sanctions connaît des indisponibilités |

Use the kickoff-era templates for these four types (same shape as schema fields; see Task 9 templates for YAML style — `>-` folded descriptions, `tags`, `created_from: seed`).

- [ ] **Step 5: Sanity check.** `ls graph/nodes/ | wc -l` → 72.

- [ ] **Step 6: Commit.**

```bash
git add graph/nodes
git commit -m "feat: seed part 3 — projects, decisions, constraints, risks"
```

---

### Task 12: Seed part 4 — edges and the 7 trap tests

**Files:**
- Modify: `graph/edges.yaml`
- Test: `tests/test_seed.py`

- [ ] **Step 1: Write the failing integration tests.**

```python
# tests/test_seed.py
"""Integration: the real seed graph loads and contains the 7 deliberate traps
(design spec 2026-06-10 §4)."""

from pathlib import Path

import pytest

from core.graph.models import EdgeType
from core.graph.service import GraphService

GRAPH_DIR = Path(__file__).resolve().parent.parent / "graph"


@pytest.fixture(scope="module")
def service() -> GraphService:
    return GraphService.from_dir(GRAPH_DIR)


def test_seed_size_and_layer_counts(service):
    nodes = service.all_nodes()
    assert 70 <= len(nodes) <= 80
    by_type = {}
    for node in nodes:
        by_type[node.type] = by_type.get(node.type, 0) + 1
    assert by_type == {
        "system": 9, "feature": 24, "business_object": 6,
        "project": 7, "decision": 8, "constraint": 12, "risk": 6,
    }
    covered = {domain for node in nodes for domain in node.domains}
    assert len(covered) == 10


def test_trap_1_alias_monaut(service):
    node = service.get_node("sys-moteur-autorisation")
    assert "MONAUT" in node.aliases


def test_trap_2_superseded_decision(service):
    superseding = [
        edge for edge in service.all_edges() if edge.type == EdgeType.SUPERSEDES
    ]
    assert any(
        edge.source_id == "dec-scoring-unique"
        and edge.target_id == "dec-scoring-par-canal-2021"
        for edge in superseding
    )
    assert service.get_node("dec-scoring-par-canal-2021").still_active is False


def test_trap_3_contradiction_is_marked(service):
    hits = service.neighbors(
        "dec-gel-evolutions-monetique", edge_types={EdgeType.RELATES_TO}
    )
    assert any(node.id == "dec-reutilisation-sca" for _, node in hits)


def test_trap_4_cross_domain_two_hop_chain(service):
    # From the TPE software, PCI DSS is reachable only through MONAUT.
    reached = service.k_hop("sys-logiciel-tpe", k=2)
    assert "con-pci-dss" in reached
    path = reached["con-pci-dss"]
    assert [edge.type for edge in path] == [EdgeType.DEPENDS_ON, EdgeType.CONSTRAINS]


def test_trap_5_constraint_inheritance_via_shared_object(service):
    # The founding example: the mobile add-beneficiary feature inherits the
    # 48h cooling-off rule through obj-beneficiaire, with full provenance.
    reached = service.k_hop("feat-mobile-ajout-benef", k=2)
    for constraint_id in (
        "con-carence-beneficiaire-48h",
        "con-sca-ajout-beneficiaire",
        "con-verif-sanctions-creation",
    ):
        assert constraint_id in reached
        path = reached[constraint_id]
        assert [edge.type for edge in path] == [
            EdgeType.OPERATES_ON, EdgeType.CONSTRAINS,
        ]
    # ... and discovers the sibling feature in BENEFGEST the same way.
    assert "feat-benef-ajout" in reached


def test_trap_6_non_uniform_depth(service):
    zoomed = set()
    for edge in service.all_edges():
        if edge.type == EdgeType.PART_OF:
            zoomed.add(edge.target_id)
    assert zoomed == {
        "sys-gestion-beneficiaires", "sys-app-mobile", "sys-passerelle-ip",
        "sys-moteur-autorisation", "sys-referentiel-client",
    }
    # A coarse system still participates in the object web at system grain.
    hits = service.neighbors("sys-scoring-fraude", edge_types={EdgeType.OPERATES_ON})
    assert any(node.id == "obj-alerte-fraude" for _, node in hits)


def test_trap_7_cancelled_project_is_memorial_only(service):
    node = service.get_node("proj-refonte-parcours-beneficiaire")
    assert node.status == "cancelled"
    hits = service.neighbors("proj-refonte-parcours-beneficiaire")
    assert len(hits) == 1
    edge, target = hits[0]
    assert edge.type == EdgeType.RELATES_TO
    assert target.id == "obj-beneficiaire"
    assert edge.note  # the abandon reason travels with the link
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_seed.py -v` → FAIL (no edges yet: every feature violates the PART_OF rule).

- [ ] **Step 3: Write `graph/edges.yaml`.** Complete list, grouped. Every edge carries `evidence` naming the node field that justifies it; all seed edges `verified: true`. Format per entry: `- {source_id: X, target_id: Y, type: T, evidence: "...", verified: true}` (add `note` where shown).

**PART_OF (24)** — each feature to its system, evidence `description of <feature-id>`:
`feat-benef-ajout`, `feat-benef-modification`, `feat-benef-suppression`, `feat-benef-consultation`, `feat-benef-api` → `sys-gestion-beneficiaires` · `feat-mobile-ajout-benef`, `feat-mobile-virement-ip`, `feat-mobile-souscription-credit`, `feat-mobile-consultation-comptes`, `feat-mobile-activation-carte` → `sys-app-mobile` · `feat-ip-emission`, `feat-ip-reception`, `feat-ip-rappel-fonds`, `feat-ip-gestion-plafonds` → `sys-passerelle-ip` · `feat-aut-temps-reel`, `feat-aut-oppositions`, `feat-aut-controle-plafonds`, `feat-aut-routage-reseaux`, `feat-aut-tarification` → `sys-moteur-autorisation` · `feat-ref-creation-client`, `feat-ref-maj-kyc`, `feat-ref-screening-periodique`, `feat-ref-fusion-doublons`, `feat-ref-exposition` → `sys-referentiel-client`

**OPERATES_ON (23)** — evidence `description of <source-id>`:
- → `obj-beneficiaire` (6): the 5 BENEFGEST features + `feat-mobile-ajout-benef`
- → `obj-virement-instantane` (5): the 4 FLUXINST features + `feat-mobile-virement-ip`
- → `obj-transaction-carte` (4): `feat-aut-temps-reel`, `feat-aut-oppositions`, `feat-aut-controle-plafonds`, + `sys-scoring-fraude` (system grain)
- → `obj-dossier-client-kyc` (5): the 5 REFCLI features
- → `obj-contrat-credit` (2): `feat-mobile-souscription-credit`, `sys-moteur-credit` (system grain)
- → `obj-alerte-fraude` (1): `sys-scoring-fraude` (system grain)

**DEPENDS_ON (17)** — evidence `description of <source-id>`:
- System spine (10): `sys-app-mobile`→`sys-moteur-autorisation` · `sys-logiciel-tpe`→`sys-moteur-autorisation` · `sys-moteur-autorisation`→`sys-scoring-fraude` · `sys-passerelle-ip`→`sys-scoring-fraude` · `sys-app-mobile`→`sys-referentiel-client` · `sys-moteur-autorisation`→`sys-core-banking` · `sys-passerelle-ip`→`sys-core-banking` · `sys-gestion-beneficiaires`→`sys-referentiel-client` · `sys-moteur-credit`→`sys-referentiel-client` · `sys-moteur-credit`→`sys-core-banking`
- Feature grain (7): `feat-mobile-ajout-benef`→`feat-benef-api` (the canonical cross-app call) · `feat-mobile-virement-ip`→`feat-ip-emission` · `feat-mobile-souscription-credit`→`sys-moteur-credit` · `feat-mobile-consultation-comptes`→`sys-core-banking` · `feat-mobile-activation-carte`→`sys-moteur-autorisation` · `feat-ip-emission`→`sys-scoring-fraude` · `feat-aut-temps-reel`→`sys-scoring-fraude`

**PRODUCED (5)** — evidence `outcomes of <project-id>`:
`proj-programme-dsp2`→`dec-reutilisation-sca` · `proj-refonte-scoring-fraude`→`dec-scoring-unique` · `proj-lancement-paiement-instantane`→`sys-passerelle-ip` · `proj-api-beneficiaires`→`feat-benef-api` · `proj-api-beneficiaires`→`dec-ecriture-via-api-benef`

**CONSTRAINS (22)** — evidence `statement of <source-id>`:
- Constraints (13): `con-pci-dss`→`sys-moteur-autorisation` · `con-lcb-ft-screening`→`sys-passerelle-ip` · `con-standard-api-interne`→`feat-benef-api` · `con-standard-api-interne`→`feat-ref-exposition` · `con-ai-act`→`sys-scoring-fraude` · `con-carence-beneficiaire-48h`→`obj-beneficiaire` · `con-sca-ajout-beneficiaire`→`obj-beneficiaire` · `con-verif-sanctions-creation`→`obj-beneficiaire` · `con-plafonds-virement-ip`→`obj-virement-instantane` · `con-rgpd-conservation`→`obj-dossier-client-kyc` · `con-tracabilite-consultations`→`obj-dossier-client-kyc` · `con-credit-conso-kyc`→`obj-contrat-credit` · `con-archivage-alertes-fraude`→`obj-alerte-fraude`
- Decisions (9): `dec-releases-tpe-trimestrielles`→`sys-logiciel-tpe` · `dec-releases-tpe-trimestrielles`→`proj-migration-flotte-tpe` · `dec-scoring-unique`→`sys-moteur-autorisation` · `dec-scoring-unique`→`sys-passerelle-ip` · `dec-reutilisation-sca`→`sys-app-mobile` · `dec-gel-evolutions-monetique`→`sys-moteur-autorisation` · `dec-ecriture-via-api-benef`→`obj-beneficiaire` · `dec-double-validation-entreprise`→`obj-virement-instantane` · `dec-plafond-ip-defaut`→`feat-ip-gestion-plafonds`

**SUPERSEDES (1):** `dec-scoring-unique`→`dec-scoring-par-canal-2021`, evidence `statement of dec-scoring-unique`

**RELATES_TO (8)** — note mandatory, evidence as shown:
- `dec-gel-evolutions-monetique`→`dec-reutilisation-sca`, note `tension non arbitrée — le gel monétique contredit la réutilisation SCA pour tout nouveau flux`, evidence `statements of both decisions`
- `risk-fragmentation-tpe`→`proj-migration-flotte-tpe`, note `la migration de flotte est la mitigation principale de ce risque`
- `risk-kyc-obsolete`→`sys-referentiel-client`, note `risque porté par la qualité des données du référentiel`
- `risk-contournement-plafonds-ip`→`sys-passerelle-ip`, note `scénario de contournement des plafonds via rafales de virements instantanés`
- `risk-doublons-beneficiaires`→`obj-beneficiaire`, note `stock historique saisi en double avant l'API unique`
- `risk-modele-fraude-derive`→`sys-scoring-fraude`, note `modèle non recalibré depuis la refonte de 2024`
- `risk-indispo-service-sanctions`→`con-verif-sanctions-creation`, note `la contrainte repose sur un service externe sujet à indisponibilités`
- `proj-refonte-parcours-beneficiaire`→`obj-beneficiaire`, note `tentative de refonte abandonnée en 2023 — migration du stock jugée infaisable sans fenêtre de gel des virements`

Total: 24 + 23 + 17 + 5 + 22 + 1 + 8 = 100 edges.

- [ ] **Step 4: Run to verify pass.** `.venv/bin/python -m pytest tests/test_seed.py -v` → 8 PASS. Then full suite: `.venv/bin/python -m pytest -v` → all PASS. `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit.**

```bash
git add graph/edges.yaml tests/test_seed.py
git commit -m "feat: seed part 4 — 100 edges and the 7 deliberate-trap tests"
```

---

### Task 13: README v1

**Files:**
- Modify: `README.md` (replace the placeholder entirely)

- [ ] **Step 1: Write the README** (English). Required sections, in order:

1. **Title + one-liner** ("An AI scoping runtime for projects that don't exist in isolation.") + honest status line: design public, MVP in progress.
2. **The five-line pitch** (verbatim from AGENTS.md north star).
3. **Why this project exists** — condensed pivot story, link to ADR 0000. Portfolio narrative: use-case-assistant → scopegraph → ecosystem-foundry, "three links, zero redundancy".
4. **How it works** — the 6-step workflow (kickoff §5) + a small Mermaid diagram `idea → ecosystem graph → grounded links → challenge → dossier → write-back`.
5. **The ecosystem graph** — the 7 node types / 7 edge types in two sentences, the feature/business-object grain (a shared rule is ONE node, every app inherits it through the object), and the universality note: the schema is domain-agnostic; only `graph/domains.yaml` and the seed content are banking-specific (link to ADR 0001).
6. **The demo scenario** — abridged BNPL story (kickoff §5): naive assistant vs scopegraph (SCA inheritance, single fraud-scoring point, credit domain, 2-hop TPE constraint), and the killer move (second scoping sees the first).
7. **What keeps it honest** — grounding gate (every claim cites a node ID), runtime authority, human validation, hermetic tests.
8. **Language note** — demo, seed data and dossiers are French (French banking domain — by design); code and docs are English.
9. **The seeded registry statement** (verbatim requirement, kickoff §5.1): "the ecosystem registry is seeded; ingestion from documents is the roadmap (see ecosystem-foundry)". All entities fictional.
10. **Getting started** — `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`, run tests (`pytest`), explore docs (`./scripts/docs-list`).
11. **Roadmap** — W2–W4 milestones (MVP spec §8) then ecosystem-foundry (kickoff §8).

- [ ] **Step 2: Verify.** Read it raw; check every internal link resolves (`docs/adr/0000-pivot-from-mas.md`, `docs/adr/0001-graph-schema-v1.md`, both specs).

- [ ] **Step 3: Commit.**

```bash
git add README.md && git commit -m "docs: README v1 — positioning, pivot story, demo scenario"
```

---

### Task 14: Eval case drafts (6)

**Files:**
- Create: `docs/eval/cases.md`
- Delete: `docs/eval/.gitkeep`

- [ ] **Step 1: Write the 6 cases** (French content, front matter required). For each case: `Entrée` (the fuzzy idea, 1–2 quoted sentences), `Dépendances critiques attendues` (node ids + one-line justification each), `Pourquoi un prompt naïf le rate` (explicit line). Skeleton:

```markdown
---
summary: 6 eval cases (French) where scopegraph must beat a naive well-written LLM prompt
read_when:
  - running or extending the evaluation (W4)
  - checking what the retrieval and challenge steps must catch
---

# Cas d'évaluation — scopegraph vs prompt naïf

Méthode : la même entrée est donnée (a) à un prompt naïf bien écrit (« tu es un assistant de
cadrage expérimenté… ») et (b) à scopegraph. Réussite = scopegraph cite la dépendance critique
avec son node ID ; le prompt naïf ne peut pas la connaître ou ne la déduit pas.

## Cas 1 — BNPL mobile (le scénario démo)
Entrée : « Ajouter une option de paiement en 3 fois dans l'app mobile. »
Attendus : dec-reutilisation-sca (héritée) · dec-scoring-unique (pas de scoring parallèle) ·
con-credit-conso-kyc via obj-contrat-credit (produit de crédit réglementé) · sys-logiciel-tpe +
dec-releases-tpe-trimestrielles (2 sauts via monetique, si acceptation magasin) ·
risk-kyc-obsolete.
Piège pour le naïf : la chaîne TPE à 2 sauts et la décision scoring enfouie.

## Cas 2 — Bénéficiaires depuis l'espace entreprise (le cas fondateur du grain feature)
Entrée : « Permettre aux clients entreprise de créer des bénéficiaires depuis leur portail. »
Attendus : con-carence-beneficiaire-48h, con-sca-ajout-beneficiaire,
con-verif-sanctions-creation (héritées via obj-beneficiaire) · dec-ecriture-via-api-benef +
feat-benef-api (passage obligé) · dec-double-validation-entreprise ·
proj-refonte-parcours-beneficiaire (averti : déjà tenté, abandonné — raison dans la note) ·
risk-doublons-beneficiaires.
Piège pour le naïf : les règles partagées sont à 2 sauts via l'objet ; le projet annulé est
invisible hors du graphe ; il doit être restitué comme avertissement, pas comme contrainte.

## Cas 3 — Cash-back commerçants
[Entrée + attendus : sys-moteur-autorisation, dec-gel-evolutions-monetique (le gel bloque le
calendrier !), con-pci-dss, collision de périmètre avec le cas 1 après write-back.]

## Cas 4 — Relèvement des plafonds de virement instantané
[Attendus : feat-ip-gestion-plafonds + dec-plafond-ip-defaut, con-lcb-ft-screening,
risk-contournement-plafonds-ip, dec-scoring-unique via sys-passerelle-ip.]

## Cas 5 — Assistant IA de réponse aux réclamations
[Attendus : con-ai-act (classification de risque), sys-referentiel-client + risk-kyc-obsolete,
con-tracabilite-consultations, con-standard-api-interne.]

## Cas 6 — Refonte de l'onboarding client digital
[Attendus : feat-ref-creation-client + obj-dossier-client-kyc, risk-kyc-obsolete,
proj-programme-dsp2 (SCA à l'entrée en relation via dec-reutilisation-sca), domaine lcb-ft
(screening entrée en relation via con-verif-sanctions-creation).]
```

(Cases 3–6: write them out fully in the same shape as Cases 1–2 — Entrée as a quoted sentence, the listed node ids as attendus with one justification each, and the explicit « piège pour le naïf » line.)

- [ ] **Step 2: Verify.** `./scripts/docs-list` → `eval/cases.md` listed clean. Cross-check every cited node id exists: `ls graph/nodes/`.

- [ ] **Step 3: Commit.**

```bash
git rm docs/eval/.gitkeep && git add docs/eval/cases.md
git commit -m "docs: draft 6 eval cases — scopegraph vs naive prompt"
```

---

### Task 15: Close the chantier

**Files:**
- Modify: `docs/BUILD-ORDER.md`

- [ ] **Step 1: Full verification.** Run: `.venv/bin/python -m pytest -v` (expect ~31 PASS, 0 fail), `.venv/bin/ruff check .` (clean), `./scripts/docs-list` (all active docs clean).

- [ ] **Step 2: Update BUILD-ORDER.md.** Move W1 items to "Current state" (with date), promote W2 (retrieval: Embedder protocol + Chroma indexing + hybrid scorer + iterative MAPPING loop + first web screens) into "Next chantier", referencing MVP spec §8. Note that retrieval now indexes features and business objects too (richer corpus, same design).

- [ ] **Step 3: Commit.**

```bash
git add docs/BUILD-ORDER.md && git commit -m "docs: BUILD-ORDER — W1 foundations done, W2 retrieval next"
```

---

## Self-review notes

- **Spec coverage (2026-06-10 design spec):** 7 node types ✓ (Task 4) · 7 edge types + topology matrix ✓ (Task 3) · domains as data ✓ (Tasks 5, 9) · PART_OF cardinality + cancelled rules ✓ (Tasks 5–6) · shared-constraint semantics exercised ✓ (Task 12 trap 5) · 72-node seed, layer counts match spec §4 exactly ✓ (Tasks 9–12) · 7 traps each tested ✓ (Task 12) · README universality note ✓ (Task 13) · 6 eval cases ✓ (Task 14). W2+ items intentionally absent.
- **Type consistency:** `k_hop` returns `dict[str, list[Edge]]`, used as a path list in Tasks 8 and 12 ✓ · `neighbors` returns `list[tuple[Edge, Node]]` everywhere ✓ · node `type` discriminator values (`"system"`, `"feature"`, `"business_object"`, …) match between models (Task 4), loader rules (Task 5), TOPOLOGY (Task 3), and seed tests (Task 12) ✓ · layer counts: 9+24+6+7+8+12+6 = 72 ✓ · edge counts: 24+23+17+5+22+1+8 = 100 ✓.
- **Sequencing constraint:** the real `graph/` is only loadable after Task 12 (PART_OF rule); no test touches it before `tests/test_seed.py` exists — loader/service tests use tmp fixtures only.
- **Conventions:** all test commands use `.venv/bin/python -m pytest`; commits follow AGENTS.md prefixes; French content only inside `graph/`, `docs/eval/cases.md`, and YAML/Python test fixtures.
