---
summary: implementation plan for W3 lot 0bis — asymmetric Embedder Protocol, RetrievalProfile, bench grid flags + autopsy, then the calibration/grid/docs run
read_when:
  - executing W3 lot 0bis task by task
  - resuming a partially executed embedder-swap branch
---

# Embedder Swap + TOP_N Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap MiniLM → multilingual-e5-base behind per-embedder `RetrievalProfile`s, scale TOP_N with graph size, and judge both levers with the 2×2 distractor-sweep grid (spec `docs/specs/2026-06-12-embedder-swap-design.md`).

**Architecture:** The `Embedder` Protocol becomes asymmetric (`embed_queries`/`embed_passages`; e5 prefixes applied inside the embedder). Every band-dependent constant moves from module globals into a frozen `RetrievalProfile` dataclass threaded through `retrieve()`, `detect_trigger()`, and `ScopingSession`. The bench gains `--embedder`/`--top-n`/`--grid` flags plus a per-trap anchor autopsy. Code first (tasks 1–7, hermetic TDD), then the real-model calibration and grid run (tasks 8–9, human reads the output).

**Tech Stack:** Python 3.12, Pydantic v2, sentence-transformers (lazy, `embeddings` extra), ChromaDB, pytest (hermetic — FakeEmbedder only).

**Branch:** `w3-embedder-swap` off `main`.

**File map:**
- Modify: `core/retrieval/config.py` (constants → `RetrievalProfile` + `PROFILES` + `DEFAULT_PROFILE`; `TOP_K`/`MAX_HOPS`/`MAX_QUESTIONS` stay module constants)
- Modify: `core/retrieval/embedder.py` (Protocol methods, `prefixed()`, FakeEmbedder)
- Modify: `core/retrieval/st_embedder.py` (profile-driven model + prefixes)
- Modify: `core/retrieval/index.py` (build→passages, query→queries)
- Modify: `core/retrieval/retriever.py` (profile param, `expansion_only` stored field)
- Modify: `core/runtime/triggers.py`, `core/runtime/session.py` (profile threading)
- Modify: `scripts/retrieval-eval` (flags, autopsy, grid), `scripts/retrieval-smoke` (flag, raw sims)
- Create: `tests/test_config.py` · Modify: `tests/test_embedder.py`, `tests/test_retriever.py`
- Docs at the end: `core/retrieval/config.py` e5 values, `docs/known-limits.md`, `docs/BUILD-ORDER.md`

---

### Task 0: Branch

- [ ] **Step 1: Create the working branch**

```bash
git checkout -b w3-embedder-swap main
```

### Task 1: RetrievalProfile in config.py

**Files:**
- Modify: `core/retrieval/config.py` (full rewrite below)
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
"""RetrievalProfile: frozen MiniLM values (known-limits reproducibility) + TOP_N policy."""

from core.retrieval.config import DEFAULT_PROFILE, E5_BASE, MINILM, PROFILES


def test_minilm_profile_is_frozen_to_w2_values():
    # Regression lock: these are the 2026-06-11 calibrated constants (known-limits L1).
    assert MINILM.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
    assert (MINILM.tau_anchor, MINILM.tau_keep) == (0.35, 0.20)
    assert (MINILM.tau_weak, MINILM.tau_noise) == (0.45, 0.25)
    assert (MINILM.alpha, MINILM.delta) == (0.15, 0.15)
    assert (MINILM.domain_fraction, MINILM.decay) == (0.5, 0.7)
    assert MINILM.query_prefix == "" and MINILM.passage_prefix == ""
    assert MINILM.top_n_policy == "fixed"


def test_e5_profile_carries_asymmetric_prefixes():
    assert E5_BASE.model_name == "intfloat/multilingual-e5-base"
    assert E5_BASE.query_prefix == "query: "
    assert E5_BASE.passage_prefix == "passage: "


def test_top_n_fixed_ignores_graph_size():
    assert MINILM.top_n(72) == 20
    assert MINILM.top_n(2072) == 20


def test_top_n_coverage_scales_with_floor():
    from dataclasses import replace

    scaled = replace(MINILM, top_n_policy="coverage")
    assert scaled.top_n(72) == 21  # ceil(0.28 * 72)
    assert scaled.top_n(2072) == 581  # ceil(0.28 * 2072)
    assert scaled.top_n(10) == 20  # floor wins on small graphs


def test_registry_and_default():
    assert PROFILES == {"minilm": MINILM, "e5": E5_BASE}
    assert DEFAULT_PROFILE is MINILM  # flipped only by the exit contract (spec §1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_PROFILE'`

- [ ] **Step 3: Rewrite config.py**

Replace the whole of `core/retrieval/config.py` with:

```python
"""Retrieval & MAPPING knobs, profiled per embedder (W2 spec §3 · W3 lot 0bis spec §3).

Band-dependent values live in a RetrievalProfile: similarity bands differ per embedder
(MiniLM anchors ≈ 0.30-0.56, e5 ≈ 0.7-0.95), so a threshold is only meaningful relative
to a model. Profiles are calibrated by reading scripts/retrieval-smoke and
scripts/retrieval-eval output — never by intuition.

MiniLM findings (2026-06-11, docs/known-limits.md L1): a 2-hop expansion lands near
anchor·decay² ≈ 0.216 — raising tau_keep above ~0.21 kills the eval-case-1 TPE chain.
Retrieval is recall-first by design; precision is the W3 challenge layer's job. The
MiniLM profile is FROZEN for known-limits reproducibility (regression-tested) — never
retune it.
"""

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    model_name: str
    tau_anchor: float  # min boosted score to count as an anchor
    tau_keep: float  # min score for an expanded node to be kept
    tau_weak: float  # best anchor below this → T1 (vague brief)
    tau_noise: float  # semantic sim below this → node counts as expansion-only (T3)
    alpha: float  # score boost per shared domain between brief and node
    delta: float  # relative margin: top-2 domain scores closer than this → T2
    domain_fraction: float  # derived domains = candidate score ≥ fraction · top score
    decay: float  # expanded score = anchor score · decay^hops
    query_prefix: str = ""  # e5-style asymmetric prefixes; empty = symmetric model
    passage_prefix: str = ""
    top_n_policy: Literal["fixed", "coverage"] = "fixed"
    top_n_fixed: int = 20
    top_n_fraction: float = 0.28  # W2 coverage parity: 20/72 candidates (spec §1)
    top_n_floor: int = 20

    def top_n(self, graph_size: int) -> int:
        """Semantic candidates pulled from the vector index for this graph size."""
        if self.top_n_policy == "fixed":
            return self.top_n_fixed
        return max(self.top_n_floor, math.ceil(self.top_n_fraction * graph_size))


MINILM = RetrievalProfile(
    name="minilm",
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
    tau_anchor=0.35,
    tau_keep=0.20,
    tau_weak=0.45,
    tau_noise=0.25,
    alpha=0.15,
    delta=0.15,
    domain_fraction=0.5,
    decay=0.7,
)

# PROVISIONAL thresholds — band-transposition guesses pending §4.ii calibration
# (spec 2026-06-12): replace every value below from retrieval-smoke output, then
# delete this comment. decay is the known trouble spot: on a ~0.7-floor band a
# multiplicative 0.7² collapses 2-hop scores below noise; 0.9 is a stopgap and the
# calibration may impose a different form.
E5_BASE = RetrievalProfile(
    name="e5-base",
    model_name="intfloat/multilingual-e5-base",
    tau_anchor=0.82,
    tau_keep=0.76,
    tau_weak=0.86,
    tau_noise=0.78,
    alpha=0.06,
    delta=0.15,
    domain_fraction=0.5,
    decay=0.9,
    query_prefix="query: ",
    passage_prefix="passage: ",
)

PROFILES: dict[str, RetrievalProfile] = {"minilm": MINILM, "e5": E5_BASE}
DEFAULT_PROFILE = MINILM  # flipped to E5_BASE only by the exit contract (spec §1)

# Structural knobs — band-independent, shared by every profile.
TOP_K = 8  # max anchors
MAX_HOPS = 2  # expansion radius from anchors
MAX_QUESTIONS = 5  # hard cap of questions per session
```

Note: the old module constants (`EMBED_MODEL`, `TOP_N`, `ALPHA`, `TAU_*`, `DELTA`, `DOMAIN_FRACTION`, `DECAY`) are deliberately GONE — tasks 2–5 migrate their readers. The suite stays red until task 5; run only the targeted test files until then.

- [ ] **Step 4: Run the new tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/config.py tests/test_config.py
git commit -m "feat: RetrievalProfile — per-embedder constants, frozen MiniLM, provisional e5"
```

### Task 2: Asymmetric Embedder Protocol

**Files:**
- Modify: `core/retrieval/embedder.py`
- Modify: `core/retrieval/st_embedder.py`
- Modify: `tests/test_embedder.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_embedder.py`, add at the top (keep existing imports):

```python
from core.retrieval.embedder import DIM, FakeEmbedder, prefixed
```

and add these tests:

```python
def test_prefixed_applies_prefix():
    assert prefixed("query: ", ["plafonds", "fraude"]) == ["query: plafonds", "query: fraude"]


def test_prefixed_empty_prefix_is_identity():
    texts = ["plafonds"]
    assert prefixed("", texts) is texts


def test_fake_embedder_queries_and_passages_are_identical():
    emb = FakeEmbedder(["app mobile"])
    [q] = emb.embed_queries(["projet app mobile"])
    [p] = emb.embed_passages(["projet app mobile"])
    assert q == p
```

Then migrate every existing `emb.embed(...)` call in this file to `emb.embed_queries(...)` (5 call sites: lines 15, 22, 31, 37–39 in the current file).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_embedder.py -v`
Expected: FAIL — `ImportError: cannot import name 'prefixed'`

- [ ] **Step 3: Update the Protocol and FakeEmbedder**

In `core/retrieval/embedder.py`, replace the `Embedder` Protocol and add `prefixed`:

```python
class Embedder(Protocol):
    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...


def prefixed(prefix: str, texts: list[str]) -> list[str]:
    """e5-style prefix application — pure, so it tests without a model download."""
    return [prefix + text for text in texts] if prefix else texts
```

In `FakeEmbedder`, replace the `embed` method with:

```python
    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]
```

- [ ] **Step 4: Update SentenceTransformersEmbedder**

Replace the whole of `core/retrieval/st_embedder.py` with:

```python
"""The real embedder. Only module allowed to import sentence_transformers — lazily."""

from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
from core.retrieval.embedder import prefixed


class SentenceTransformersEmbedder:
    def __init__(self, profile: RetrievalProfile = DEFAULT_PROFILE) -> None:
        self.model_name = profile.model_name  # embedder_id() folds this into fingerprints
        self._query_prefix = profile.query_prefix
        self._passage_prefix = profile.passage_prefix
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # clear startup error (W2 spec: error handling)
            raise RuntimeError(
                "sentence-transformers is not installed — run: pip install -e '.[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(profile.model_name)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        rows = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._encode(prefixed(self._query_prefix, texts))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode(prefixed(self._passage_prefix, texts))
```

(The existing import-error test in `tests/test_embedder.py` still passes: the constructor signature change keeps a no-arg default.)

- [ ] **Step 5: Run the embedder tests**

Run: `python -m pytest tests/test_embedder.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/retrieval/embedder.py core/retrieval/st_embedder.py tests/test_embedder.py
git commit -m "feat: asymmetric Embedder Protocol — embed_queries/embed_passages, e5 prefixes"
```

### Task 3: VectorIndex call sites

**Files:**
- Modify: `core/retrieval/index.py:74` and `core/retrieval/index.py:86`

- [ ] **Step 1: Switch build() to passages, query() to queries**

In `core/retrieval/index.py`, line 74: `embeddings=self._embedder.embed(documents),` → `embeddings=self._embedder.embed_passages(documents),`
Line 86: `[vector] = self._embedder.embed([text])` → `[vector] = self._embedder.embed_queries([text])`

- [ ] **Step 2: Run the index tests**

Run: `python -m pytest tests/test_index.py -v`
Expected: all PASS (FakeEmbedder implements both methods identically)

- [ ] **Step 3: Commit**

```bash
git add core/retrieval/index.py
git commit -m "feat: index embeds passages, queries embed queries (e5 asymmetry)"
```

### Task 4: retrieve() takes a profile

**Files:**
- Modify: `core/retrieval/retriever.py`
- Modify: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_retriever.py` (it already imports `VectorIndex`, `FakeEmbedder`, `retrieve` and builds a seed-fragment index in a fixture — reuse the same pattern):

```python
def test_profile_top_n_caps_the_candidate_pool():
    from dataclasses import replace

    from core.retrieval.config import MINILM

    fragments = ["bénéficiaire", "virement"]
    index = VectorIndex(FakeEmbedder(fragments))
    service = GraphService.from_dir(GRAPH_DIR)
    index.build(service)
    starved = replace(MINILM, top_n_fixed=1, tau_anchor=0.0)
    result = retrieve("création de bénéficiaire de virement", service, index, profile=starved)
    assert len(result.anchors) == 1  # only one candidate ever reached the scorer
```

(Adapt `GRAPH_DIR`/fixture names to what `tests/test_retriever.py` already defines at the top of the file — the file builds seed-backed indexes the same way at line 53.)

And the spec-§7 injected-threshold test:

```python
def test_expansion_only_threshold_comes_from_the_profile():
    from dataclasses import replace

    from core.retrieval.config import MINILM

    fragments = ["espace client"]
    index = VectorIndex(FakeEmbedder(fragments))
    service = GraphService.from_dir(GRAPH_DIR)
    index.build(service)
    strict = replace(MINILM, tau_noise=2.0)  # every expanded node is textually invisible
    result = retrieve("refonte espace client", service, index, profile=strict)
    assert result.expanded, "scenario must expand for the assertion to mean anything"
    assert all(scored.expansion_only for scored in result.expanded)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_retriever.py::test_profile_top_n_caps_the_candidate_pool -v`
Expected: FAIL — `TypeError: retrieve() got an unexpected keyword argument 'profile'`

- [ ] **Step 3: Thread the profile through retriever.py**

In `core/retrieval/retriever.py`:

a. Replace the `config` import line with:

```python
from core.retrieval import config
from core.retrieval.config import RetrievalProfile
```

b. In `ScoredNode`, replace the `expansion_only` property with a stored field (the
threshold is injected at construction — the dataclass stops reading module globals):

```python
@dataclass(frozen=True)
class ScoredNode:
    node_id: str
    score: float
    domains: tuple[str, ...] = ()
    semantic_sim: float | None = None
    anchor_id: str | None = None
    path: tuple[Edge, ...] = ()
    expansion_only: bool = False  # reached structurally, near-invisible textually (T3)
```

c. New `retrieve` signature and body changes:

```python
def retrieve(
    text: str,
    service: GraphService,
    index: VectorIndex,
    *,
    domains: Sequence[str] = (),
    excluded_domains: Sequence[str] = (),
    profile: RetrievalProfile = config.DEFAULT_PROFILE,
) -> RetrievalResult:
```

Inside the body: `config.TOP_N` → `profile.top_n(len(service.all_nodes()))` ·
`config.ALPHA` → `profile.alpha` · `config.TAU_ANCHOR` → `profile.tau_anchor` ·
`config.DOMAIN_FRACTION` → `profile.domain_fraction` · pass `profile` to `_expand`:

```python
    sims = dict(index.query(text, profile.top_n(len(service.all_nodes()))))
    ...
    expanded = _expand(anchors, service, sims, set(excluded_domains), set(domains), profile)
```

d. `_expand` gains the parameter and sets the field; `config.MAX_HOPS`/`config.DECAY`/`config.TAU_KEEP` readers become:

```python
def _expand(
    anchors: list[ScoredNode],
    service: GraphService,
    sims: dict[str, float],
    excluded: set[str],
    confirmed: set[str],
    profile: RetrievalProfile,
) -> list[ScoredNode]:
    anchor_ids = {anchor.node_id for anchor in anchors}
    best: dict[str, ScoredNode] = {}
    for anchor in anchors:  # strongest first → ties resolve to the strongest anchor
        for node_id, path in service.k_hop(anchor.node_id, config.MAX_HOPS).items():
            if node_id in anchor_ids:
                continue
            node = service.get_node(node_id)
            node_domains = set(node.domains)
            # exclusion drops a node only if no user-confirmed domain rescues it
            if node_domains & excluded and not (node_domains & confirmed):
                continue
            score = anchor.score * profile.decay ** len(path)
            if score < profile.tau_keep:
                continue
            if node_id not in best or score > best[node_id].score:
                best[node_id] = ScoredNode(
                    node_id=node_id,
                    score=score,
                    domains=tuple(node.domains),
                    semantic_sim=sims.get(node_id),
                    anchor_id=anchor.node_id,
                    path=tuple(path),
                    expansion_only=(sims.get(node_id) or 0.0) < profile.tau_noise,
                )
    return sorted(best.values(), key=lambda scored: (-scored.score, scored.node_id))
```

(`MAX_HOPS` stays a module constant — structural, spec §3.)

- [ ] **Step 4: Run the retriever and eval-case tests**

Run: `python -m pytest tests/test_retriever.py tests/test_retrieval_eval_cases.py -v`
Expected: all PASS (default profile = MINILM = old constants; `expansion_only` keeps its semantics as a field)

- [ ] **Step 5: Commit**

```bash
git add core/retrieval/retriever.py tests/test_retriever.py
git commit -m "feat: retrieve() reads band-dependent knobs from a RetrievalProfile"
```

### Task 5: Profile threading — triggers and session

**Files:**
- Modify: `core/runtime/triggers.py:40-53`
- Modify: `core/runtime/session.py:41-48,88-96`

- [ ] **Step 1: Thread the profile into detect_trigger**

In `core/runtime/triggers.py`, change the imports and signature:

```python
from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
```

(drop `from core.retrieval import config`), then:

```python
def detect_trigger(
    result: RetrievalResult,
    brief: ProjectBrief,
    asked: set[str],
    profile: RetrievalProfile = DEFAULT_PROFILE,
) -> Trigger | None:
```

Body: `config.TAU_WEAK` → `profile.tau_weak` (line 45) · `config.DELTA` → `profile.delta` (line 53).

- [ ] **Step 2: Thread the profile into ScopingSession**

In `core/runtime/session.py`:

```python
from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
```

(keep `from core.retrieval import config` — `config.MAX_QUESTIONS` stays), then:

```python
    def __init__(
        self,
        service: GraphService,
        index: VectorIndex,
        profile: RetrievalProfile = DEFAULT_PROFILE,
    ) -> None:
        self._service = service
        self._index = index
        self._profile = profile
        ...
```

In `_map_round()`: pass `profile=self._profile` to `retrieve(...)` and
`detect_trigger(result, self.brief, self.asked, self._profile)`.

- [ ] **Step 3: Run the runtime and web tests**

Run: `python -m pytest tests/test_triggers.py tests/test_session.py tests/test_web.py -v`
Expected: all PASS (defaults preserve W2 behavior; `web/app.py` needs no change — the session default flows)

- [ ] **Step 4: Commit**

```bash
git add core/runtime/triggers.py core/runtime/session.py
git commit -m "feat: profile threading through triggers and ScopingSession"
```

### Task 6: Full suite + ruff green

- [ ] **Step 1: Run the whole hermetic suite**

Run: `python -m pytest -q`
Expected: 135+ tests PASS, 0 failures. If anything still imports a dead constant (`config.TOP_N`, `config.TAU_ANCHOR`, …), fix that call site to use a profile — do NOT re-add module constants.

- [ ] **Step 2: Ruff**

Run: `ruff check . && ruff format --check .`
Expected: clean. Fix and re-run if not.

- [ ] **Step 3: Commit (only if fixes were needed)**

```bash
git add -A && git commit -m "fix: migrate remaining readers of the dead module constants"
```

### Task 7: Bench — `--embedder` / `--top-n` / `--grid` + anchor autopsy

**Files:**
- Modify: `scripts/retrieval-eval` (no hermetic tests — real-model script, out of CI like today)

- [ ] **Step 1: Imports and profile resolution**

Replace the `config` import block of `scripts/retrieval-eval` with:

```python
from dataclasses import replace as dc_replace

from core.graph.service import GraphService  # noqa: E402
from core.retrieval import config  # noqa: E402
from core.retrieval.config import PROFILES, RetrievalProfile  # noqa: E402
from core.retrieval.index import VectorIndex  # noqa: E402
from core.retrieval.retriever import retrieve  # noqa: E402
from core.retrieval.st_embedder import SentenceTransformersEmbedder  # noqa: E402
```

Add after `SWEEP_POINTS`:

```python
def resolve_profile(name: str, top_n: str | None) -> RetrievalProfile:
    profile = PROFILES[name]
    if top_n is not None:
        profile = dc_replace(profile, top_n_policy="coverage" if top_n == "scaled" else "fixed")
    return profile
```

- [ ] **Step 2: Thread the profile through run_cases and record thieves**

`RunSummary` gains the thief lineup (the §5 autopsy data):

```python
@dataclass
class RunSummary:
    recall: float
    size: float
    precision: float
    found: dict[str, set[str]] = field(default_factory=dict)  # scenario -> expected hits
    thieves: dict[str, list[tuple[str, str, tuple[str, ...], float]]] = field(
        default_factory=dict
    )  # scenario -> [(id, title, domains, sim)] for distractor anchors
```

`run_cases` signature becomes `run_cases(service, index, profile)`; the `retrieve` call
becomes `retrieve(brief, service, index, profile=profile)`; and inside the
`if distractor_ids:` block, record the lineup:

```python
        if distractor_ids:
            intrusion = sum(1 for a in result.anchors if a.node_id in distractor_ids)
            pollution = len(got & distractor_ids) / max(len(got), 1)
            line += (f"  anchor-intrusion {intrusion}/{len(result.anchors)}"
                     f"  pollution {pollution:.0%}")
            found_thieves = []
            for scored in result.anchors:
                if scored.node_id in distractor_ids:
                    node = service.get_node(scored.node_id)
                    title = getattr(node, "name", "") or getattr(node, "title", "")
                    found_thieves.append(
                        (scored.node_id, title, tuple(node.domains), scored.semantic_sim or 0.0)
                    )
            thieves[name] = found_thieves
```

(declare `thieves: dict[str, list] = {}` next to `found` and pass both to `RunSummary`).

- [ ] **Step 3: Autopsy in print_verdict**

`print_verdict` gains the worst-run service (for dead-node domains) and prints the
lineup with the mechanical same-domain/cross-domain flag (spec §5 — the a-vs-b call
stays human, this output makes it a 10-minute read):

```python
def print_verdict(base: RunSummary, worst: RunSummary, service: GraphService) -> bool:
    """Criterion fixed BEFORE measurement (spec §6): per-case survival + mean drop ≤10pts."""
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
        return True
    print("VERDICT: TRAPS DIE — read the autopsy, then spec §5 annotation before escalating")
    for name, nodes in sorted(dead.items()):
        dead_domains = {d for node_id in nodes for d in service.get_node(node_id).domains}
        print(f"  {name}: lost {', '.join(nodes)}")
        for thief_id, title, domains, sim in worst.thieves.get(name, []):
            flag = "same-domain" if set(domains) & dead_domains else "cross-domain"
            print(f"    thief [{flag}] {thief_id} (sim {sim:.3f}) — {title} {list(domains)}")
    return False
```

- [ ] **Step 4: distractor_sweep returns its verdict**

```python
def distractor_sweep(embedder: SentenceTransformersEmbedder, profile: RetrievalProfile) -> bool:
    runs: dict[int, RunSummary] = {}
    service = None
    for n in SWEEP_POINTS:
        service = build_service(n)
        index = VectorIndex(embedder)
        index.build(service)
        top_n = profile.top_n(len(service.all_nodes()))
        print(f"\n--- distractors N={n} ({len(service.all_nodes())} nodes,"
              f" top_n {top_n}) ---")
        realism_check(service, index)
        runs[n] = run_cases(service, index, profile)
        print(f"==> recall {runs[n].recall:.0%} | map {runs[n].size:.1f}"
              f" | precision {runs[n].precision:.0%}")
    return print_verdict(runs[0], runs[max(SWEEP_POINTS)], service)
```

- [ ] **Step 5: The grid runner and the new main()**

```python
def run_grid() -> None:
    """Spec §5: the four cells, each a full sweep; one embedder load per row."""
    outcomes: dict[str, bool] = {}
    for embedder_name in ("minilm", "e5"):
        embedder = SentenceTransformersEmbedder(PROFILES[embedder_name])
        for top_n in ("fixed", "scaled"):
            cell = f"{embedder_name} × top-n {top_n}"
            print(f"\n{'=' * 20} CELL {cell} {'=' * 20}")
            outcomes[cell] = distractor_sweep(embedder, resolve_profile(embedder_name, top_n))
    print("\n===== GRID SUMMARY =====")
    for cell, holds in outcomes.items():
        print(f"  {cell:28s} {'HOLDS' if holds else 'TRAPS DIE'}")
```

`main()` becomes:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true", help="run the threshold grid sweep")
    parser.add_argument("--distractors", type=int, default=0, metavar="N",
                        help="merge the first N pool distractors before running")
    parser.add_argument("--distractor-sweep", action="store_true",
                        help=f"run at N={SWEEP_POINTS} and print the verdict")
    parser.add_argument("--embedder", choices=sorted(PROFILES), default=None,
                        help="profile to run (default: DEFAULT_PROFILE)")
    parser.add_argument("--top-n", choices=["fixed", "scaled"], default=None,
                        help="override the profile's TOP_N policy")
    parser.add_argument("--grid", action="store_true",
                        help="run the 2x2 grid (embedder x top-n policy) as full sweeps")
    args = parser.parse_args()

    if args.grid:
        run_grid()
        return

    name = args.embedder or config.DEFAULT_PROFILE.name.replace("-base", "")
    profile = resolve_profile(name if name in PROFILES else "minilm", args.top_n)
    embedder = SentenceTransformersEmbedder(PROFILES[name if name in PROFILES else "minilm"])

    if args.distractor_sweep:
        distractor_sweep(embedder, profile)
        return

    service = build_service(args.distractors)
    index = VectorIndex(embedder)
    index.build(service)

    if not args.sweep:
        print(f"profile: {profile.name}  tau_anchor={profile.tau_anchor}"
              f" tau_keep={profile.tau_keep} top_n_policy={profile.top_n_policy}"
              f" TOP_K={config.TOP_K} MAX_HOPS={config.MAX_HOPS}")
        summary = run_cases(service, index, profile)
        print(f"\n  mean recall {summary.recall:.0%} | mean map {summary.size:.1f}"
              f" | mean precision {summary.precision:.0%}")
        return

    print(f"{'grid':14s} TAU_A TAU_K K hops | recall | map   | precision")
    for grid_name, tau_a, tau_k, top_k, hops in GRIDS:
        grid_profile = dc_replace(profile, tau_anchor=tau_a, tau_keep=tau_k)
        config.TOP_K, config.MAX_HOPS = top_k, hops
        print(f"\n--- {grid_name} ---")
        summary = run_cases(service, index, grid_profile)
        print(f"==> recall {summary.recall:.0%} | map {summary.size:.1f}"
              f" | precision {summary.precision:.0%}")
```

(The `--sweep` GRIDS loop keeps mutating `config.TOP_K`/`config.MAX_HOPS` — those stayed
module constants; the band thresholds now go through `dc_replace` on the profile.)

- [ ] **Step 6: Sanity-run the script's argument paths (no model needed)**

Run: `./scripts/retrieval-eval --help`
Expected: the six flags listed, exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/retrieval-eval
git commit -m "feat: bench grid flags (--embedder/--top-n/--grid) + per-trap anchor autopsy"
```

### Task 8: retrieval-smoke — profile flag + raw similarity block

**Files:**
- Modify: `scripts/retrieval-smoke`

- [ ] **Step 1: Add the flag and the calibration output**

The §4.ii calibration reads the RAW similarity band — the existing output is TAU-gated,
which is circular when the TAUs are the thing being calibrated. Replace `main()` with:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedder", choices=sorted(PROFILES), default=None,
                        help="profile to run (default: DEFAULT_PROFILE)")
    args = parser.parse_args()
    profile = PROFILES[args.embedder] if args.embedder else DEFAULT_PROFILE

    service = GraphService.from_dir(ROOT / "graph")
    index = VectorIndex(SentenceTransformersEmbedder(profile))
    index.build(service, f"{graph_fingerprint(ROOT / 'graph')}:{profile.model_name}")
    for case, brief in BRIEFS.items():
        result = retrieve(brief, service, index, profile=profile)
        print(f"\n=== {case}: {brief}")
        print("  -- raw top-20 sims (ungated — calibration reads THIS band)")
        for node_id, sim in index.query(brief, 20):
            print(f"    {sim:.3f}  {node_id}")
        print("  -- anchors")
        for scored in result.anchors:
            print(f"    {scored.score:.3f}  {scored.node_id}  (sim {scored.semantic_sim:.3f})")
        print("  -- expanded (top 12)")
        for scored in result.expanded[:12]:
            hops = len(scored.path)
            print(f"    {scored.score:.3f}  {scored.node_id}  via {scored.anchor_id} ({hops} hop)")
        print(f"  -- domains {result.domain_scores} -> derived {result.derived_domains}")
```

with the matching imports added at the top:

```python
import argparse

from core.retrieval.config import DEFAULT_PROFILE, PROFILES  # noqa: E402
```

- [ ] **Step 2: Sanity-run**

Run: `./scripts/retrieval-smoke --help`
Expected: `--embedder {e5,minilm}` listed, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/retrieval-smoke
git commit -m "feat: smoke takes --embedder and prints the raw sim band for calibration"
```

### Task 9: Calibration (REAL MODEL — human reads every output, spec §4 order is strict)

No code beyond editing `E5_BASE` values in `core/retrieval/config.py`. Each step's
output must be READ, not skimmed — constants come from the output, never from intuition
(L1 doctrine).

- [ ] **Step 1: Install the extra and pre-pull the model**

```bash
pip install -e ".[embeddings]"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"
```

Expected: model downloads (~1.1 GB), no error.

- [ ] **Step 2: Read the e5 band (spec §4.ii)**

```bash
./scripts/retrieval-smoke --embedder e5 | tee /tmp/e5-smoke.txt
```

Read the `raw top-20 sims` blocks across the 6 briefs and write down: the anchor band
(sims of obviously-right nodes), the noise band (sims of obviously-wrong nodes), and the
gap. Then set `E5_BASE` in `core/retrieval/config.py` by band transposition — same
recall-first logic as W2: `tau_anchor` low enough to keep every documented trap anchor,
`tau_keep` low enough that a 2-hop chain survives `decay`, `tau_noise` at the noise
median, `tau_weak` just under the typical best-anchor sim, `alpha` ≈ the boost that
moves a borderline same-domain node past `tau_anchor`. Resolve `decay` here: check what
`best_anchor_sim · decay²` gives vs `tau_keep` — if the multiplicative form cannot keep
2-hop chains above noise without keeping everything, switch the e5 profile to a gentler
value and record the reasoning in the config comment. Delete the PROVISIONAL comment.

- [ ] **Step 3: e5 gate at N=0 (spec §4.iii — chantier stops here if it fails)**

```bash
./scripts/retrieval-eval --embedder e5 | tee /tmp/e5-n0.txt
./scripts/retrieval-eval --embedder minilm > /tmp/minilm-n0.txt
```

Gate: every documented trap node MiniLM finds at N=0 is still found by e5, AND e5 mean
recall ≥ 84 % (MiniLM 89 % − 5 pts). If the gate fails: iterate §4.ii once (the bands
were misread); if it still fails, STOP — report to Loïc with both outputs, the swap
itself is wrong and the spec's exit contract says so.

- [ ] **Step 4: Commit the calibrated profile**

```bash
git add core/retrieval/config.py
git commit -m "feat: e5 profile calibrated from smoke band (N=0 gate green)"
```

### Task 10: The 2×2 grid + docs + exit contract

- [ ] **Step 1: Run the grid (~30–60 min on CPU; embeddings of 2072 nodes × 4 cells)**

```bash
./scripts/retrieval-eval --grid | tee /tmp/grid.txt
```

- [ ] **Step 2: Read the GRID SUMMARY and apply the exit contract (spec §1)**

- Best cell HOLDS → in `core/retrieval/config.py`: `DEFAULT_PROFILE = E5_BASE` and set
  `E5_BASE`'s `top_n_policy="coverage"` if the scaled arm is what passed. Run
  `python -m pytest -q` (hermetic suite must stay green — it pins MINILM values, not the
  default) and `ruff check .`.
- Any trap death in the best cell → do NOT flip the default. The next action is the
  mandatory thief relevance annotation (spec §5) on `/tmp/grid.txt`, then the separate
  escalation brainstorm. Stop after Step 3's docs update.

- [ ] **Step 3: Update the docs (both outcomes)**

- `docs/known-limits.md` L4: append the 2×2 table (per cell: recall N=0→2000, anchor
  intrusion, dead traps), the verdict, and the autopsy summary. L5: re-evaluate the
  biased-recall note (if traps survive e5, record that the bias stops mattering).
- `docs/BUILD-ORDER.md`: lot 0bis done with the verdict; next = lots 1–4 unblocked
  (HOLDS) or thief annotation + escalation brainstorm (TRAPS DIE). Note the multi-turn
  polluted sweep as a conditional follow-up.

- [ ] **Step 4: Commit and report**

```bash
git add core/retrieval/config.py docs/known-limits.md docs/BUILD-ORDER.md
git commit -m "docs: 2x2 grid measured — verdict + L4/L5/BUILD-ORDER updated"
```

Report to Loïc: the grid table, the verdict, and (if traps died) the thief lineup ready
for his annotation pass.
