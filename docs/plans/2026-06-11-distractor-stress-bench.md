---
summary: implementation plan for W3 lot 0 — distractor pool, multi-dir loader, polluted retrieval-eval
read_when:
  - executing W3 lot 0 (subagent-driven or inline)
  - checking what was planned vs what shipped
---

# Distractor Stress Bench (W3 lot 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure anchor ranking under distractor pressure (known-limits L4) by committing
a 2000-node synthetic pool and re-running the 11 retrieval-eval scenarios at
N = 0/500/1000/2000, with a pre-committed HOLDS / SWAP-EMBEDDER verdict.

**Architecture:** A committed pool in `graph-distractors/` (10 domain shards, each a
coherent fictional mini-ecosystem ordered parents-before-features, plus inter-domain
`edges.yaml`). A bench-only loading path (`core/graph/distractors.py` +
`GraphService.from_dirs`) merges seed + a deterministic prefix sample of N distractors.
`scripts/retrieval-eval` gains `--distractors N` / `--distractor-sweep` with intrusion,
pollution, realism-check and verdict output. Spec (build contract):
`docs/specs/2026-06-11-distractor-stress-bench-design.md`.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, ChromaDB (existing), pytest (hermetic),
SentenceTransformers only inside the bench script.

**Branch:** `w3-distractor-bench` (created in Task 1, from `main`).

**Conventions that bind every task:** French for graph/pool content, English for
code/comments/docs (AGENTS.md rule 6). Fictional entities only (rule 5). Hermetic tests —
no model download, no network (rule 4). Ruff line length 100. Run
`ruff check . && python -m pytest -q` before every commit.

---

### Task 1: Branch, ADR 0002, `created_from: synthetic`, spec §2 amendment

**Files:**
- Create: `docs/adr/0002-created-from-synthetic.md`
- Modify: `core/graph/models.py:14`
- Modify: `docs/specs/2026-06-11-distractor-stress-bench-design.md` (§2 layout)
- Test: `tests/test_models.py`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b w3-distractor-bench
```

- [ ] **Step 2: Write the failing test** — append to `tests/test_models.py`
  (match the file's existing style; it already imports the node classes):

```python
def test_created_from_accepts_synthetic():
    """ADR 0002: provenance label for generated stress-test data."""
    node = System(
        id="sys-dmon-exemple",
        name="Exemple",
        description="Système distracteur.",
        owner_team="X",
        domains=["monetique"],
        created_from="synthetic",
    )
    assert node.created_from == "synthetic"
```

If `tests/test_models.py` builds nodes through a helper/fixture, reuse it instead of the
literal constructor — the assertion is the only thing that matters.

- [ ] **Step 3: Run it, watch it fail**

Run: `python -m pytest tests/test_models.py -q -k synthetic`
Expected: FAIL — `ValidationError ... String should match pattern`

- [ ] **Step 4: Extend the pattern** in `core/graph/models.py:14`:

```python
CREATED_FROM_PATTERN = r"^(seed|synthetic|scoping:[a-z0-9-]+|ingestion:[a-z0-9-]+)$"
```

- [ ] **Step 5: Run the test, watch it pass**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS (whole file).

- [ ] **Step 6: Write ADR 0002** — `docs/adr/0002-created-from-synthetic.md`
  (match the heading style of `docs/adr/0001-graph-schema-v1.md`):

```markdown
# ADR 0002 — `created_from: synthetic` provenance label

Date: 2026-06-11 · Status: accepted

## Context

Schema v1 (ADR 0001) freezes `created_from` to `seed | scoping:<id> | ingestion:<id>`.
W3 lot 0 (distractor stress bench, spec 2026-06-11) needs a committed pool of generated
stress-test nodes that must be distinguishable from real ecosystem data everywhere
(loader gates, bench metrics, any future UI filter). `ingestion:synthetic` would fit the
existing pattern but lies about provenance: nothing was ingested.

## Decision

Add the literal `synthetic` to `CREATED_FROM_PATTERN`. It labels generated stress-test
data only. The runtime never produces it; the app and the demo never load nodes carrying
it (the pool lives outside `graph/`). Loader-level enforcement that pool content carries
exactly this label lives in `core/graph/distractors.py`, not in the schema.

## Consequences

- `graph-distractors/` content is schema-valid and mechanically identifiable.
- Bench metrics (anchor intrusion, map pollution) key off `created_from == "synthetic"`.
- Any other future provenance still requires its own ADR.
```

- [ ] **Step 7: Amend spec §2** — in
  `docs/specs/2026-06-11-distractor-stress-bench-design.md`, the generation session needs
  conflict-free parallel writes, so intra-domain edges move into the shards. Replace the
  directory listing and the line after it:

Replace:
```
graph-distractors/
  monetique.yaml            # ~200 nodes, YAML list under a `nodes:` key
  tpe-acceptation.yaml
  ... (one shard per domain, 10 total)
  edges.yaml                # PART_OF (intra-domain) + inter-domain edges, `edges:` key
```
With:
```
graph-distractors/
  monetique.yaml            # 200 nodes (`nodes:` list) + intra-domain edges (`edges:` list)
  tpe-acceptation.yaml
  ... (one shard per domain, 10 total)
  edges.yaml                # inter-domain edges among distractors only (`edges:` key)
```
And in "Edge rules", change "to a distractor system *in the same shard*" context if
needed so it reads: PART_OF/OPERATES_ON/intra-domain edges live in the shard's `edges:`
list; `edges.yaml` carries only the inter-domain edges. (Keep the "no seed id" rule
untouched.)

- [ ] **Step 8: Verify and commit**

```bash
ruff check . && python -m pytest -q
git add core/graph/models.py tests/test_models.py docs/adr/0002-created-from-synthetic.md \
  docs/specs/2026-06-11-distractor-stress-bench-design.md
git commit -m "feat: created_from 'synthetic' provenance label (ADR 0002)"
```

---

### Task 2: Loader refactor — extract `validate_node` (behavior-neutral)

**Files:**
- Modify: `core/graph/loader.py:46-67`
- Test: existing `tests/test_loader.py` (no new tests — pure extraction)

- [ ] **Step 1: Extract the helper.** In `core/graph/loader.py`, the node loop inside
  `load_graph` currently validates schema, id prefix, and domain vocabulary inline.
  Add this function (above `load_graph`):

```python
def validate_node(data: dict, path: Path, vocabulary: frozenset[str]) -> Node:
    """Validate one raw node mapping: schema v1, id prefix, domain vocabulary."""
    try:
        node = _NODE_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise GraphLoadError(f"{path}: invalid node: {exc}") from exc
    expected_prefix = _ID_PREFIXES[node.type]
    if not node.id.startswith(expected_prefix):
        raise GraphLoadError(
            f"{path}: id '{node.id}' must carry the '{expected_prefix}' prefix "
            f"for type '{node.type}' (ADR 0001)"
        )
    unknown = set(node.domains) - vocabulary
    if unknown:
        raise GraphLoadError(
            f"{path}: unknown domains {sorted(unknown)} "
            "(vocabulary: graph/domains.yaml, governed by ADR)"
        )
    return node
```

- [ ] **Step 2: Rewrite the node loop in `load_graph`** to use it (the duplicate-id
  check stays in the caller — it is per-collection, not per-node):

```python
    nodes: dict[str, Node] = {}
    for path in sorted((graph_dir / "nodes").glob("*.yaml")):
        node = validate_node(_read_yaml(path), path, vocabulary)
        if node.id in nodes:
            raise GraphLoadError(f"{path}: duplicate node id '{node.id}'")
        nodes[node.id] = node
```

- [ ] **Step 3: Verify nothing changed behaviorally**

Run: `ruff check . && python -m pytest -q`
Expected: all 103 tests pass (102 from W2 + Task 1's), zero modified test files.

- [ ] **Step 4: Commit**

```bash
git add core/graph/loader.py
git commit -m "refactor: extract validate_node from load_graph (reused by distractor pool)"
```

---

### Task 3: `core/graph/distractors.py` — pool parsing + validation

**Files:**
- Create: `core/graph/distractors.py`
- Test: `tests/test_distractors.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_distractors.py`:

```python
"""Distractor pool loading + prefix sampling (hermetic: tmp-path YAML only)."""

from pathlib import Path

import pytest

from core.graph.distractors import load_distractor_pool, sample_pool
from core.graph.loader import GraphLoadError

DOMAINS_YAML = "domains:\n  - alpha\n  - beta\n"

SEED_NODE = """\
type: system
id: sys-core
name: Coeur seed
description: Système du seed.
owner_team: Equipe Seed
domains: [alpha]
"""

ALPHA_SHARD = """\
nodes:
  - type: system
    id: sys-da-un
    name: DA Un
    description: Premier système distracteur.
    owner_team: Equipe A
    domains: [alpha]
    created_from: synthetic
  - type: feature
    id: feat-da-un-a
    name: Fonction A
    description: Fonction du système DA Un.
    domains: [alpha]
    created_from: synthetic
  - type: feature
    id: feat-da-un-b
    name: Fonction B
    description: Autre fonction du système DA Un.
    domains: [alpha]
    created_from: synthetic
edges:
  - {source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF, created_from: synthetic}
  - {source_id: feat-da-un-b, target_id: sys-da-un, type: PART_OF, created_from: synthetic}
"""

BETA_SHARD = """\
nodes:
  - type: system
    id: sys-db-un
    name: DB Un
    description: Système distracteur du domaine beta.
    owner_team: Equipe B
    domains: [beta]
    created_from: synthetic
  - type: risk
    id: risk-db-un
    title: Risque distracteur
    statement: Un risque plausible du domaine beta.
    likelihood: low
    impact: medium
    domains: [beta]
    created_from: synthetic
"""


def write_seed(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "graph"
    (graph_dir / "nodes").mkdir(parents=True)
    (graph_dir / "domains.yaml").write_text(DOMAINS_YAML, encoding="utf-8")
    (graph_dir / "nodes" / "sys-core.yaml").write_text(SEED_NODE, encoding="utf-8")
    (graph_dir / "edges.yaml").write_text("edges: []\n", encoding="utf-8")
    return graph_dir


def write_pool(
    tmp_path: Path,
    alpha: str = ALPHA_SHARD,
    beta: str = BETA_SHARD,
    inter: str | None = None,
) -> Path:
    pool_dir = tmp_path / "graph-distractors"
    pool_dir.mkdir()
    (pool_dir / "alpha.yaml").write_text(alpha, encoding="utf-8")
    (pool_dir / "beta.yaml").write_text(beta, encoding="utf-8")
    if inter is not None:
        (pool_dir / "edges.yaml").write_text(inter, encoding="utf-8")
    return pool_dir


VOCAB = frozenset({"alpha", "beta"})


def test_pool_loads_shards_in_file_order(tmp_path):
    pool_dir = write_pool(tmp_path)
    shards, edges = load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))
    assert [n.id for n in shards["alpha"]] == ["sys-da-un", "feat-da-un-a", "feat-da-un-b"]
    assert [n.id for n in shards["beta"]] == ["sys-db-un", "risk-db-un"]
    assert len(edges) == 2  # the two PART_OF


def test_inter_domain_edges_yaml_is_loaded(tmp_path):
    inter = (
        "edges:\n"
        "  - {source_id: sys-da-un, target_id: sys-db-un, type: DEPENDS_ON,"
        " created_from: synthetic}\n"
    )
    pool_dir = write_pool(tmp_path, inter=inter)
    _, edges = load_distractor_pool(pool_dir, VOCAB, frozenset())
    assert len(edges) == 3


def test_non_synthetic_node_rejected(tmp_path):
    bad = ALPHA_SHARD.replace("created_from: synthetic", "created_from: seed", 1)
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="created_from: synthetic"):
        load_distractor_pool(pool_dir, VOCAB, frozenset())


def test_non_synthetic_edge_rejected(tmp_path):
    bad = ALPHA_SHARD.replace(
        "{source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF,"
        " created_from: synthetic}",
        "{source_id: feat-da-un-a, target_id: sys-da-un, type: PART_OF}",
    )
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="created_from: synthetic"):
        load_distractor_pool(pool_dir, VOCAB, frozenset())


def test_edge_referencing_seed_id_rejected(tmp_path):
    inter = (
        "edges:\n"
        "  - {source_id: sys-da-un, target_id: sys-core, type: DEPENDS_ON,"
        " created_from: synthetic}\n"
    )
    pool_dir = write_pool(tmp_path, inter=inter)
    with pytest.raises(GraphLoadError, match="outside the pool"):
        load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))


def test_pool_id_colliding_with_seed_rejected(tmp_path):
    bad = ALPHA_SHARD.replace("id: sys-da-un", "id: sys-core")
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="already used"):
        load_distractor_pool(pool_dir, VOCAB, frozenset({"sys-core"}))


def test_missing_pool_dir_rejected(tmp_path):
    with pytest.raises(GraphLoadError, match="not found"):
        load_distractor_pool(tmp_path / "nope", VOCAB, frozenset())


def test_sample_pool_prefix_and_remainder(tmp_path):
    pool_dir = write_pool(tmp_path)
    shards, _ = load_distractor_pool(pool_dir, VOCAB, frozenset())
    # n=3 over 2 shards: divmod -> base 1, remainder to alphabetically-first (alpha)
    assert [n.id for n in sample_pool(shards, 3)] == ["sys-da-un", "feat-da-un-a", "sys-db-un"]
    assert sample_pool(shards, 0) == []
```

- [ ] **Step 2: Run them, watch them fail**

Run: `python -m pytest tests/test_distractors.py -q`
Expected: collection error — `ModuleNotFoundError: core.graph.distractors`

- [ ] **Step 3: Implement** — create `core/graph/distractors.py`:

```python
"""Distractor pool: parsing, validation, deterministic prefix sampling (W3 lot 0).

The pool lives in graph-distractors/ — one YAML shard per domain (a coherent fictional
mini-ecosystem: `nodes:` ordered parents-before-features, plus intra-domain `edges:`)
and edges.yaml for inter-domain edges among distractors. Bench/test-only: the app and
the demo never load this. Spec: docs/specs/2026-06-11-distractor-stress-bench-design.md.
"""

from pathlib import Path

from pydantic import ValidationError

from core.graph.loader import GraphLoadError, _check_topology, _read_yaml, validate_node
from core.graph.models import Edge, Node

EDGES_FILE = "edges.yaml"


def load_distractor_pool(
    pool_dir: Path, vocabulary: frozenset[str], reserved_ids: frozenset[str]
) -> tuple[dict[str, list[Node]], list[Edge]]:
    """Parse and validate the full pool.

    Returns (shard name -> nodes in file order, all pool edges). Fail-fast on:
    non-synthetic provenance, id collisions (pool-internal or vs reserved seed ids),
    edges referencing anything outside the pool (which bans distractor↔seed edges),
    topology violations (ADR 0001).
    """
    if not pool_dir.is_dir():
        raise GraphLoadError(f"{pool_dir}: distractor pool directory not found")
    shard_paths = sorted(p for p in pool_dir.glob("*.yaml") if p.name != EDGES_FILE)
    if not shard_paths:
        raise GraphLoadError(f"{pool_dir}: no distractor shards found")

    shards: dict[str, list[Node]] = {}
    pool_nodes: dict[str, Node] = {}
    raw_edges: list[tuple[Path, int, dict]] = []
    for path in shard_paths:
        data = _read_yaml(path) or {}
        shard: list[Node] = []
        for raw in data.get("nodes") or []:
            node = validate_node(raw, path, vocabulary)
            if node.id in pool_nodes or node.id in reserved_ids:
                raise GraphLoadError(f"{path}: id '{node.id}' already used (pool or seed)")
            if node.created_from != "synthetic":
                raise GraphLoadError(
                    f"{path}: node '{node.id}' must carry created_from: synthetic"
                )
            pool_nodes[node.id] = node
            shard.append(node)
        shards[path.stem] = shard
        raw_edges.extend((path, i, raw) for i, raw in enumerate(data.get("edges") or []))

    inter_path = pool_dir / EDGES_FILE
    if inter_path.exists():
        inter_raw = (_read_yaml(inter_path) or {}).get("edges") or []
        raw_edges.extend((inter_path, i, raw) for i, raw in enumerate(inter_raw))

    edges: list[Edge] = []
    for path, i, raw in raw_edges:
        try:
            edge = Edge.model_validate(raw)
        except ValidationError as exc:
            raise GraphLoadError(f"{path}: edge #{i}: {exc}") from exc
        if edge.created_from != "synthetic":
            raise GraphLoadError(f"{path}: edge #{i} must carry created_from: synthetic")
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in pool_nodes:
                raise GraphLoadError(
                    f"{path}: edge #{i} references '{endpoint}' outside the pool"
                )
        _check_topology(edge, pool_nodes, path, i)
        edges.append(edge)
    return shards, edges


def sample_pool(shards: dict[str, list[Node]], n: int) -> list[Node]:
    """Deterministic prefix sample: the first ~n/len(shards) nodes of each shard.

    Shards are ordered parents-before-features, so any prefix keeps every sampled
    feature's parent system (PART_OF cardinality holds at any n — verified again by
    _check_graph_rules on the merged graph). The remainder n % len(shards) goes to
    the alphabetically-first shards. No RNG anywhere.
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    names = sorted(shards)
    base, extra = divmod(n, len(names))
    sampled: list[Node] = []
    for rank, name in enumerate(names):
        quota = base + (1 if rank < extra else 0)
        sampled.extend(shards[name][:quota])
    return sampled
```

- [ ] **Step 4: Run the tests, watch them pass**

Run: `python -m pytest tests/test_distractors.py -q`
Expected: 8 passed.

- [ ] **Step 5: Verify and commit**

```bash
ruff check . && python -m pytest -q
git add core/graph/distractors.py tests/test_distractors.py
git commit -m "feat: distractor pool loader — synthetic-only, pool-closed edges, topology-checked"
```

---

### Task 4: `GraphService.from_dirs` — merged seed + sampled distractors

**Files:**
- Modify: `core/graph/service.py`
- Test: `tests/test_distractors.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_distractors.py`
  (also add `from core.graph.service import GraphService` to its imports — it was
  deliberately left out in Task 3 to keep ruff green):

```python
def test_from_dirs_merges_seed_and_prefix_sample(tmp_path):
    graph_dir = write_seed(tmp_path)
    pool_dir = write_pool(tmp_path)
    # n=3 → alpha gets 2 (sys-da-un, feat-da-un-a), beta gets 1 (sys-db-un)
    service = GraphService.from_dirs(graph_dir, pool_dir, 3)
    ids = {node.id for node in service.all_nodes()}
    assert ids == {"sys-core", "sys-da-un", "feat-da-un-a", "sys-db-un"}
    # the sampled feature's PART_OF edge survived the endpoint filter
    assert any(e.type.value == "PART_OF" for e in service.all_edges())


def test_from_dirs_is_deterministic(tmp_path):
    graph_dir = write_seed(tmp_path)
    pool_dir = write_pool(tmp_path)
    first = [n.id for n in GraphService.from_dirs(graph_dir, pool_dir, 3).all_nodes()]
    second = [n.id for n in GraphService.from_dirs(graph_dir, pool_dir, 3).all_nodes()]
    assert first == second


def test_from_dirs_n_zero_equals_seed_only(tmp_path):
    graph_dir = write_seed(tmp_path)
    pool_dir = write_pool(tmp_path)
    service = GraphService.from_dirs(graph_dir, pool_dir, 0)
    assert [n.id for n in service.all_nodes()] == ["sys-core"]


def test_shard_violating_parent_order_fails_at_cutting_n(tmp_path):
    # feature first, its parent system after: a prefix of 1 strands the feature
    bad = """\
nodes:
  - type: feature
    id: feat-da-orphelin
    name: Orpheline
    description: Feature déclarée avant son système parent.
    domains: [alpha]
    created_from: synthetic
  - type: system
    id: sys-da-parent
    name: Parent
    description: Système parent déclaré trop tard.
    owner_team: Equipe A
    domains: [alpha]
    created_from: synthetic
edges:
  - {source_id: feat-da-orphelin, target_id: sys-da-parent, type: PART_OF, created_from: synthetic}
"""
    graph_dir = write_seed(tmp_path)
    pool_dir = write_pool(tmp_path, alpha=bad)
    with pytest.raises(GraphLoadError, match="exactly one PART_OF"):
        GraphService.from_dirs(graph_dir, pool_dir, 1)
```

- [ ] **Step 2: Run them, watch them fail**

Run: `python -m pytest tests/test_distractors.py -q`
Expected: 4 new failures — `AttributeError: ... no attribute 'from_dirs'`

- [ ] **Step 3: Implement.** In `core/graph/service.py`, extend the imports and add the
  classmethod right under `from_dir`:

```python
from core.graph.distractors import load_distractor_pool, sample_pool
from core.graph.loader import _check_graph_rules, load_domains, load_graph
```

```python
    @classmethod
    def from_dirs(cls, graph_dir: Path, distractor_dir: Path, n: int) -> "GraphService":
        """Seed + the first n pool distractors, merged and re-validated.

        Bench/test-only entry point — the app always uses from_dir. Pool edges are
        kept only when both endpoints made the sample; graph rules (PART_OF
        cardinality, cancelled-project) re-run on the merged graph.
        """
        nodes, edges = load_graph(graph_dir)
        vocabulary = load_domains(graph_dir)
        shards, pool_edges = load_distractor_pool(distractor_dir, vocabulary, frozenset(nodes))
        for node in sample_pool(shards, n):
            nodes[node.id] = node
        kept = [e for e in pool_edges if e.source_id in nodes and e.target_id in nodes]
        merged = [*edges, *kept]
        _check_graph_rules(nodes, merged)
        return cls(nodes, merged)
```

- [ ] **Step 4: Run the tests, watch them pass**

Run: `python -m pytest tests/test_distractors.py -q`
Expected: 12 passed.

- [ ] **Step 5: Verify and commit**

```bash
ruff check . && python -m pytest -q
git add core/graph/service.py tests/test_distractors.py
git commit -m "feat: GraphService.from_dirs — seed + deterministic distractor prefix sample"
```

---

### Task 5: `retrieval-eval --distractors N` / `--distractor-sweep`

**Files:**
- Modify: `scripts/retrieval-eval`

No hermetic tests (the script is real-model, out of CI, like today). Verification is a
real run at the end of the task.

- [ ] **Step 1: Restructure `run_cases` to return a summary object.** Replace the
  current `run_cases` and add the imports/dataclass:

At the top of the script add:

```python
import statistics
from dataclasses import dataclass, field
```

Replace `run_cases` with:

```python
@dataclass
class RunSummary:
    recall: float
    size: float
    precision: float
    found: dict[str, set[str]] = field(default_factory=dict)  # scenario -> expected hits


def run_cases(service: GraphService, index: VectorIndex) -> RunSummary:
    distractor_ids = {n.id for n in service.all_nodes() if n.created_from == "synthetic"}
    total = len(service.all_nodes())
    recalls, sizes, precisions = [], [], []
    found: dict[str, set[str]] = {}
    for name, brief, expected, trap in SCENARIOS:
        result = retrieve(brief, service, index)
        got = set(result.node_ids())
        hit = expected & got
        found[name] = hit
        recalls.append(len(hit) / len(expected))
        sizes.append(len(got))
        precisions.append(len(hit) / max(len(got), 1))
        missing = ", ".join(sorted(expected - got)) or "-"
        line = (f"  {name:30s} recall {len(hit)}/{len(expected)}  map {len(got):3d}/{total}")
        if distractor_ids:
            intrusion = sum(1 for a in result.anchors if a.node_id in distractor_ids)
            pollution = len(got & distractor_ids) / max(len(got), 1)
            line += (f"  anchor-intrusion {intrusion}/{len(result.anchors)}"
                     f"  pollution {pollution:.0%}")
        print(f"{line}  missing: {missing}")
        if expected - got:
            print(f"    trap: {trap}")
    n = len(SCENARIOS)
    return RunSummary(sum(recalls) / n, sum(sizes) / n, sum(precisions) / n, found)
```

- [ ] **Step 2: Adapt the two existing call sites** (default run and `--sweep`) to the
  new return type — in `main`, replace the unpacking:

```python
        summary = run_cases(service, index)
        print(f"\n  mean recall {summary.recall:.0%} | mean map {summary.size:.1f}"
              f" | mean precision {summary.precision:.0%}")
```

and in the sweep loop:

```python
        summary = run_cases(service, index)
        print(f"==> recall {summary.recall:.0%} | map {summary.size:.1f}"
              f" | precision {summary.precision:.0%}")
```

- [ ] **Step 3: Add the distractor machinery.** Add these functions:

```python
def build_service(n: int) -> GraphService:
    if n == 0:
        return GraphService.from_dir(ROOT / "graph")
    return GraphService.from_dirs(ROOT / "graph", ROOT / "graph-distractors", n)


def realism_check(service: GraphService, index: VectorIndex) -> None:
    """Brief↔distractor sims vs brief↔seed-noise sims: warn when the pool is easy noise.

    Real seed noise sits at ≈0.25-0.40 (known-limits L1). If the distractors' median
    similarity sits well below the seed noise median, the pool does not exert real
    anchor pressure and the verdict cannot be trusted.
    """
    distractor_ids = {n.id for n in service.all_nodes() if n.created_from == "synthetic"}
    if not distractor_ids:
        return
    total = len(service.all_nodes())
    pool_sims: list[float] = []
    noise_sims: list[float] = []
    for _, brief, expected, _ in SCENARIOS:
        for node_id, sim in index.query(brief, total):
            if node_id in distractor_ids:
                pool_sims.append(sim)
            elif node_id not in expected:
                noise_sims.append(sim)

    def dist(values: list[float]) -> str:
        q1, med, q3 = statistics.quantiles(values, n=4)
        return f"q1 {q1:.2f} med {med:.2f} q3 {q3:.2f} max {max(values):.2f}"

    print(f"  realism: distractors [{dist(pool_sims)}] vs seed noise [{dist(noise_sims)}]")
    if statistics.median(pool_sims) < statistics.median(noise_sims) - 0.05:
        print("  WARNING: distractor sims sit well below real seed noise — the pool is"
              " too easy, this verdict is not trustworthy")


SWEEP_POINTS = [0, 500, 1000, 2000]


def distractor_sweep(embedder) -> None:
    runs: dict[int, RunSummary] = {}
    for n in SWEEP_POINTS:
        service = build_service(n)
        index = VectorIndex(embedder)
        index.build(service)
        print(f"\n--- distractors N={n} ({len(service.all_nodes())} nodes) ---")
        realism_check(service, index)
        runs[n] = run_cases(service, index)
        print(f"==> recall {runs[n].recall:.0%} | map {runs[n].size:.1f}"
              f" | precision {runs[n].precision:.0%}")
    print_verdict(runs[0], runs[max(SWEEP_POINTS)])


def print_verdict(base: RunSummary, worst: RunSummary) -> None:
    """Criterion fixed BEFORE measurement (spec §1): per-case survival + mean drop ≤10pts."""
    dead = {
        name: sorted(base.found[name] - worst.found[name])
        for name in base.found
        if base.found[name] - worst.found[name]
    }
    drop = base.recall - worst.recall
    print(f"\nrecall N=0 {base.recall:.0%} -> N={SWEEP_POINTS[-1]} {worst.recall:.0%}"
          f" (drop {drop:.0%})")
    if not dead and drop <= 0.10:
        print("VERDICT: HOLDS — no per-case regression, mean drop within 10 pts")
    else:
        print("VERDICT: SWAP EMBEDDER (multilingual-e5) — see spec §1 criterion")
        for name, nodes in sorted(dead.items()):
            print(f"  {name}: lost {', '.join(nodes)}")
```

- [ ] **Step 4: Wire the CLI.** In `main()`:

```python
    parser.add_argument("--distractors", type=int, default=0, metavar="N",
                        help="merge the first N pool distractors before running")
    parser.add_argument("--distractor-sweep", action="store_true",
                        help=f"run at N={SWEEP_POINTS} and print the verdict")
```

The embedder is built once (`SentenceTransformersEmbedder()`); `--distractor-sweep`
branches to `distractor_sweep(embedder)` and returns; otherwise
`service = build_service(args.distractors)` replaces the current `from_dir` line
(default 0 keeps today's behavior byte-identical). `GraphService.from_dirs` import goes
alongside the existing imports. Each sweep point builds a fresh `VectorIndex` (fresh
ephemeral Chroma client) — never reuse one index across N values.

- [ ] **Step 5: Verify no regression at N=0 (real model, ~1 min)**

Run: `ruff check . && ./scripts/retrieval-eval`
Expected: same per-scenario output shape as before (plus nothing — no distractor
columns at N=0), mean recall 89 %. `--distractors`/`--distractor-sweep` will only be
runnable after Task 8; `./scripts/retrieval-eval --distractors 500` must currently fail
with `GraphLoadError: ... distractor pool directory not found`.

- [ ] **Step 6: Commit**

```bash
git add scripts/retrieval-eval
git commit -m "feat: retrieval-eval --distractors/--distractor-sweep with verdict + realism check"
```

---

### Task 6: Pool data tests (red until the pool lands)

**Files:**
- Create: `tests/test_distractor_pool.py`

These are the mechanical gates of spec §3 step 4. They go red now and turn green when
Tasks 7–8 finish. **Do not commit in this task** — they are committed together with the
pool in Task 9 (never leave CI red).

- [ ] **Step 1: Write the gates** — create `tests/test_distractor_pool.py`:

```python
"""Data gates over the committed distractor pool (pure YAML — CI-safe, no model).

Pool-shape contract from the W3 lot 0 spec: 10 shards × 200 nodes, parents before
features, synthetic-only, edges closed over the pool. Skipped only if the pool has
not been generated yet (pre-Task-9 working tree).
"""

from pathlib import Path

import pytest

from core.graph.distractors import load_distractor_pool
from core.graph.loader import load_domains, load_graph
from core.graph.service import GraphService

ROOT = Path(__file__).resolve().parent.parent
POOL_DIR = ROOT / "graph-distractors"

pytestmark = pytest.mark.skipif(
    not POOL_DIR.is_dir(), reason="distractor pool not generated yet (W3 lot 0 task 7-9)"
)


@pytest.fixture(scope="module")
def pool():
    vocabulary = load_domains(ROOT / "graph")
    nodes, _ = load_graph(ROOT / "graph")
    return load_distractor_pool(POOL_DIR, vocabulary, frozenset(nodes))


def test_ten_shards_of_two_hundred(pool):
    shards, _ = pool
    assert len(shards) == 10
    assert {name: len(nodes) for name, nodes in shards.items()} == dict.fromkeys(shards, 200)


def test_pool_has_inter_domain_edges(pool):
    shards, edges = pool
    domain_of = {n.id: name for name, nodes in shards.items() for n in nodes}
    inter = [e for e in edges if domain_of[e.source_id] != domain_of[e.target_id]]
    assert len(inter) >= 60, "edge agent must produce a real inter-domain mesh"


def test_full_merge_loads(pool):
    service = GraphService.from_dirs(ROOT / "graph", POOL_DIR, 2000)
    assert len(service.all_nodes()) == 72 + 2000


@pytest.mark.parametrize("n", [1, 7, 500, 1000, 1999])
def test_any_prefix_n_is_loadable(n):
    service = GraphService.from_dirs(ROOT / "graph", POOL_DIR, n)
    assert len(service.all_nodes()) == 72 + n
```

(The synthetic-only, id-uniqueness, no-seed-edge, and topology gates need no dedicated
test here: `load_distractor_pool` — exercised by the fixture and `from_dirs` — fail-fasts
on all of them, with unit coverage in `tests/test_distractors.py`. A pool violation makes
this whole file error out, which is the gate doing its job.)

- [ ] **Step 2: Run — confirm the skip guard works**

Run: `python -m pytest tests/test_distractor_pool.py -q`
Expected: all skipped (`distractor pool not generated yet`). No commit.

---

### Task 7: Generate the 10 domain shards (parallel subagents)

**Files:**
- Create: `graph-distractors/<domain>.yaml` × 10

This is the agent-session deliverable of spec §3 (there is deliberately no generator
script). Dispatch **10 subagents in parallel**, one per domain, each with the prompt
template below filled from this table (counts per type sum to 200; id codes are
distractor-unique and never collide with seed id segments):

| shard file | domain | id code |
|---|---|---|
| `monetique.yaml` | monetique | `dmon` |
| `tpe-acceptation.yaml` | tpe-acceptation | `dtpe` |
| `paiement-instantane.yaml` | paiement-instantane | `dpin` |
| `dsp2-open-banking.yaml` | dsp2-open-banking | `ddsp` |
| `lcb-ft.yaml` | lcb-ft | `dlcb` |
| `credit.yaml` | credit | `dcre` |
| `banque-en-ligne.yaml` | banque-en-ligne | `dbel` |
| `referentiel-client.yaml` | referentiel-client | `dref` |
| `editique-reporting.yaml` | editique-reporting | `dedi` |
| `socle-si.yaml` | socle-si | `dsoc` |

Per-shard type mix (every shard identical): **25 system, 67 feature, 17 business_object,
19 project, 22 decision, 33 constraint, 17 risk = 200.**

- [ ] **Step 1: Dispatch the 10 agents.** Prompt template below uses Python
  `str.format` semantics: fill `{domain}`, `{file}`, `{code}` (and `{definition}` =
  the domain's comment line in `graph/domains.yaml`); every doubled brace `{{`/`}}`
  becomes a single brace in the final prompt (they appear only inside the embedded
  self-check snippet):

````
You are generating DISTRACTOR data for a retrieval stress bench in the scopegraph repo
(working dir: the repo root). Your single deliverable is the file
`graph-distractors/{file}` — a fictional French banking-IT mini-ecosystem for the
domain `{domain}` ({definition}). It must be plausible, internally coherent noise:
realistic enough to compete in an embedding index, entirely fictional.

HARD RULES
- 100% fictional: invented system/team/project names. No real bank, vendor, product,
  or system name, ever. No name reuse from `graph/nodes/` (run `ls graph/nodes/` and
  `grep -h "name:\|title:" graph/nodes/*.yaml` to see what to avoid).
- All content text in FRENCH. Descriptions/statements: 1-3 sentences, varied phrasing —
  do not reuse one sentence skeleton across nodes (this data must not cluster on a
  template in embedding space). Read 2-3 files in graph/nodes/ for style and realism.
- Every node and every edge carries `created_from: synthetic`.
- Every id embeds your shard code right after the type prefix:
  `sys-{code}-…`, `feat-{code}-…`, `obj-{code}-…`, `proj-{code}-…`, `dec-{code}-…`,
  `con-{code}-…`, `risk-{code}-…`. Ids are kebab-case slugs.
- `domains:` is `[{domain}]` for every node (a second existing domain from
  graph/domains.yaml is allowed on at most ~10 nodes).
- Project nodes: status `done` or `ongoing` only — NEVER `cancelled`.

FILE SHAPE — `graph-distractors/{file}` has exactly two top-level keys:

nodes:        # EXACTLY 200 nodes: 25 system, 67 feature, 17 business_object,
              # 19 project, 22 decision, 33 constraint, 17 risk
edges:        # intra-shard edges only (both endpoints in YOUR file):
              # - exactly one PART_OF per feature (feature -> its parent system)
              # - 20-40 OPERATES_ON (feature|system -> business_object)
              # - 10-20 DEPENDS_ON (system->system, feature->feature, feature->system)
              # - 15-30 CONSTRAINS (constraint|decision -> system|feature|business_object|project)
              # All edges: created_from: synthetic. No other edge types.

ORDERING INVARIANT (critical): in `nodes:`, every system appears BEFORE all of its
features. Recommended layout: system, then its features, then the next system, etc.,
with business_objects/projects/decisions/constraints/risks interleaved freely.
The bench samples file PREFIXES — a feature whose parent comes later breaks the build.

NODE SCHEMAS (Pydantic, extra fields forbidden — exact required fields):
- system: type, id, name, description, owner_team, domains  (optional: aliases, tags,
  data_quality_notes, known_risks)
- feature: type, id, name, description, domains  (optional: parameters, tags)
- business_object: type, id, name, description, domains  (optional: aliases, steward_team)
- project: type, id, name, description, status(done|ongoing), owner_team, domains
  (optional: aliases, outcomes, known_risks)
- decision: type, id, title, statement, rationale, date(YYYY-MM-DD), decided_by, domains
  (optional: still_active)
- constraint: type, id, title, statement, source, severity(low|medium|high), domains
- risk: type, id, title, statement, likelihood(low|medium|high),
  impact(low|medium|high), domains  (optional: mitigations)

Example node entry (block style, follow it):

  - type: system
    id: sys-{code}-exemple-remplacer
    name: Nom Fictif
    description: Description française plausible en une ou deux phrases.
    owner_team: Équipe Fictive
    domains: [{domain}]
    created_from: synthetic

WORKFLOW
1. Write the file in 3-4 chunks (Write the first ~50 nodes, then append with Edit) —
   do not attempt 200 nodes in one tool call.
2. Self-check when done (must print OK):

python3 - <<'EOF'
from pathlib import Path
from core.graph.loader import _read_yaml, load_domains, validate_node
from core.graph.models import Edge
from collections import Counter
path = Path("graph-distractors/{file}")
vocab = load_domains(Path("graph"))
data = _read_yaml(path)
nodes, ids = [], set()
for raw in data["nodes"]:
    node = validate_node(raw, path, vocab)
    assert node.created_from == "synthetic", node.id
    assert node.id not in ids, f"duplicate {{node.id}}"
    ids.add(node.id)
    nodes.append(node)
counts = Counter(n.type for n in nodes)
assert counts == {{"system": 25, "feature": 67, "business_object": 17, "project": 19,
                  "decision": 22, "constraint": 33, "risk": 17}}, counts
part_of = {{}}
for i, raw in enumerate(data["edges"]):
    e = Edge.model_validate(raw)
    assert e.created_from == "synthetic", f"edge #{{i}}"
    assert e.source_id in ids and e.target_id in ids, f"edge #{{i}} leaves the shard"
    if e.type.value == "PART_OF":
        assert e.source_id not in part_of, f"second PART_OF for {{e.source_id}}"
        part_of[e.source_id] = e.target_id
pos = {{n.id: i for i, n in enumerate(nodes)}}
feats = [n for n in nodes if n.type == "feature"]
assert all(f.id in part_of for f in feats), "feature without PART_OF"
assert all(pos[part_of[f.id]] < pos[f.id] for f in feats), "parent after feature"
print(f"OK: {{len(nodes)}} nodes, {{len(data['edges'])}} edges")
EOF

3. Fix and re-run until OK. Your final message: the OK line + 3 sample node titles.
````

- [ ] **Step 2: Gate after all 10 agents return.** Full-pool mechanical check:

Run: `python -m pytest tests/test_distractor_pool.py -q`
Expected at this point: `test_ten_shards_of_two_hundred`, `test_full_merge_loads` and
`test_any_prefix_n_is_loadable` PASS; **`test_pool_has_inter_domain_edges` FAILS**
(edges.yaml comes in Task 8). Any other failure → send the offending shard back to a
fresh agent with the error message.

No commit yet (Task 9 commits the pool atomically).

---

### Task 8: Inter-domain edges (edge agent)

**Files:**
- Create: `graph-distractors/edges.yaml`

- [ ] **Step 1: Dispatch one agent** with this prompt:

````
The repo (working dir: root) has 10 distractor shards in graph-distractors/*.yaml, each
a fictional French banking-IT mini-ecosystem for one domain. Your deliverable:
`graph-distractors/edges.yaml` — the INTER-domain edges that knit these fictional
ecosystems together, so that graph expansion from a distractor anchor drags realistic
cross-domain neighborhoods in.

Survey the material first (keep it cheap — titles only):
  grep -n "id:\|name:\|title:" graph-distractors/monetique.yaml   # etc. for all 10

Write `edges.yaml` with a single top-level `edges:` list of 100-150 edges:
- 40-60 DEPENDS_ON: system -> system across domains (plausible: a front consumes a
  backend, a reporting tool reads a payment engine...). feature->feature and
  feature->system allowed too.
- 30-50 CONSTRAINS: constraint|decision -> system|feature|business_object|project in
  ANOTHER domain (transverse rules: security, RGPD-like fictional rules, architecture
  decisions binding other domains).
- 10-25 OPERATES_ON: system|feature -> business_object of another domain.
- 5-15 RELATES_TO (any direction) — each MUST carry a `note:` field explaining the link
  in French (schema rejects RELATES_TO without note).

RULES
- Both endpoints must be distractor ids (they all embed a d-code: dmon, dtpe, dpin,
  ddsp, dlcb, dcre, dbel, dref, dedi, dsoc). NEVER reference an id from graph/nodes/
  (the seed) — one seed reference fails the whole build.
- The two endpoints of each edge must come from DIFFERENT shards.
- Every edge: `created_from: synthetic`. Optional `note:`/`evidence:` in French.
- Format, one edge per line:
  - {source_id: sys-dbel-x, target_id: sys-dmon-y, type: DEPENDS_ON, created_from: synthetic}

Self-check (must print counts then OK):

python3 - <<'EOF'
from pathlib import Path
from core.graph.distractors import load_distractor_pool
from core.graph.loader import load_domains, load_graph
root = Path(".")
vocab = load_domains(root / "graph")
nodes, _ = load_graph(root / "graph")
shards, edges = load_distractor_pool(root / "graph-distractors", vocab, frozenset(nodes))
domain_of = {n.id: name for name, ns in shards.items() for n in ns}
inter = [e for e in edges if domain_of[e.source_id] != domain_of[e.target_id]]
assert len(inter) >= 60, f"only {len(inter)} inter-domain edges"
print(f"pool OK: {sum(len(v) for v in shards.values())} nodes, {len(edges)} edges, "
      f"{len(inter)} inter-domain")
EOF

Fix and re-run until OK (the loader fail-fasts with the exact file/edge index on any
topology or endpoint error). Final message: the OK line.
````

- [ ] **Step 2: Gate**

Run: `python -m pytest tests/test_distractor_pool.py -q`
Expected: **all pool gates PASS** (incl. `test_pool_has_inter_domain_edges`).

---

### Task 9: Review by sampling, full verification, atomic pool commit

**Files:**
- Commit: `graph-distractors/` (11 files) + `tests/test_distractor_pool.py`

- [ ] **Step 1: Review by sampling (orchestrator does this directly, not a subagent).**
  Read ~10 nodes from each shard at varied offsets, e.g.:

```bash
for f in graph-distractors/[a-z]*.yaml; do echo "== $f"; sed -n '1,40p;400,440p;900,940p' "$f"; done
```

Check: French quality · plausibility (would pass for a real bank's wiki) · fictional
names only · phrasing actually varies (no template skeleton repeated). Also verify no
seed name leaked: spot-check a few seed system names from `grep -h "^name:" graph/nodes/sys-*.yaml`
against the pool. A weak shard (template-y, anglicisms, real names) goes back to a fresh
agent with specific feedback before committing.

- [ ] **Step 2: Full verification**

Run: `ruff check . && python -m pytest -q`
Expected: every test green, including the 5 pool gates (no skips besides any
pre-existing ones).

- [ ] **Step 3: Commit (pool + gates together — CI never sees a red or skipped-red state)**

```bash
git add graph-distractors/ tests/test_distractor_pool.py
git commit -m "feat: 2000-node distractor pool, 10 fictional domain shards + inter-domain mesh

Generated per the W3 lot 0 spec §3 agent protocol (10 domain agents + 1 edge agent,
reviewed by sampling). Bench-only data: never loaded by the app or the demo."
```

---

### Task 10: Run the sweep, record the verdict, close the chantier

**Files:**
- Modify: `docs/known-limits.md` (L4)
- Modify: `docs/BUILD-ORDER.md`
- Move: `docs/plans/2026-06-11-distractor-stress-bench.md` → `docs/archive/`

- [ ] **Step 1: Quick smoke at small N (real model)**

Run: `./scripts/retrieval-eval --distractors 100`
Expected: 11 scenarios print with `anchor-intrusion x/y` and `pollution z%` columns;
no exception; realism line printed.

- [ ] **Step 2: Full sweep**

Run: `./scripts/retrieval-eval --distractor-sweep 2>&1 | tee /tmp/distractor-sweep.log`
Expected: four blocks (N=0/500/1000/2000), realism check per block (no "too easy"
warning, or the verdict is void — investigate the pool before concluding anything),
final `VERDICT:` line.

- [ ] **Step 3: Record in `docs/known-limits.md` L4.** Append to the L4 section: date,
  the four (recall, map, precision, mean anchor-intrusion) tuples, the realism medians,
  per-case deaths if any, and the verdict line. Keep the existing L4 text — this is the
  measurement it called for.

- [ ] **Step 4: Update `docs/BUILD-ORDER.md`.** Move lot 0 into "Current state" with the
  measured numbers and the verdict. Next chantier becomes either W3 lot 1 (LLMProvider —
  verdict HOLDS) or the embedder swap (multilingual-e5, the spec's recorded escalation —
  verdict SWAP), explicitly ordered before lot 1 in that case.

- [ ] **Step 5: Archive this plan**

```bash
git mv docs/plans/2026-06-11-distractor-stress-bench.md docs/archive/
```

- [ ] **Step 6: Final verification + commit**

```bash
ruff check . && python -m pytest -q
git add docs/known-limits.md docs/BUILD-ORDER.md
git commit -m "docs: distractor sweep measured — L4 closed with verdict, build order updated"
```

- [ ] **Step 7: Merge.** Use superpowers:finishing-a-development-branch (merge
  `w3-distractor-bench` into `main`, as for W1/W2).

---

## Self-review notes (spec coverage)

- Spec §1 decisions → Tasks 1 (ADR/pattern), 7 (agent generation, 2000), 5+10 (sweep
  points + fixed criterion), 3 (truth-island isolation via pool-closed edges), 7 (domain
  vocabulary unchanged — agents constrained to existing domains), 1 (no generator script:
  none planned).
- Spec §2 layout → Tasks 1 (amendment), 7-8 (files); node rules → Task 3 gates + Task 7
  prompt; edge rules → Task 3 (pool-closed) + Task 8 prompt.
- Spec §3 protocol → Tasks 7 (domain agents), 8 (edge agent), 9 (review + gates).
- Spec §4 loading → Tasks 2-4 (`validate_node`, `load_distractor_pool`, `sample_pool`,
  `from_dirs`; app path untouched — `from_dir` unmodified).
- Spec §5 bench → Task 5 (flags, intrusion, pollution, realism, verdict).
- Spec §6 tests → Tasks 1, 3, 4 (unit) + 6 (data gates; ADR 0002 regression test is
  Task 1's).
- Spec §7 docs → Tasks 1 (ADR) and 10 (known-limits, BUILD-ORDER).
