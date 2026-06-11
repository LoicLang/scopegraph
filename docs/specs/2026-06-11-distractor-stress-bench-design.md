---
summary: validated W3-lot-0 design — synthetic distractor pool + polluted retrieval-eval, with a pre-committed embedder-swap criterion
read_when:
  - implementing the distractor pool, the multi-dir loader, or retrieval-eval --distractors
  - regenerating or extending graph-distractors/
  - interpreting the distractor bench verdict (HOLDS vs SWAP EMBEDDER)
---

# Distractor stress bench (W3 lot 0) — Design Spec

Date: 2026-06-11
Status: validated in brainstorming session (this doc is the build contract for W3 lot 0)
Upstream: known-limits **L4** (the scale-validity gap this bench closes) · BUILD-ORDER W3
lot 0 · ADR 0001 (schema v1; this chantier triggers micro-ADR 0002).

At 72 nodes the right anchors reach TOP_N almost by default; with thousands of plausible
distractors inside MiniLM's narrow similarity band, nobody knows. This bench measures that
one genuinely scale-biased quantity — **anchor ranking under distractor pressure** — before
W3 builds the challenge layer on top of retrieval. Everything else (expansion mechanics,
L2/L3 findings) already holds at any size and is not re-tested here.

---

## 1. Decisions taken (closing this brainstorm)

| Topic | Decision | Rationale |
|---|---|---|
| Distractor text generation | **Subagent-generated, committed pool**: one agent per domain (coherent fictional mini-ecosystem each), one agent for inter-domain edges, human-level review by sampling. No generator script. | Naturally varied phrasing is the load-bearing property — template/combinator output clusters in embedding space and produces unrealistically easy (or uniformly hard) noise. Per-domain agents diversify vocabulary by construction. Decided over: seeded template combinator, runtime LLM generation (needs a provider before W3 lot 1, non-deterministic). |
| Pool size & bench points | **Pool of 2000** (~200/domain), bench sweep at **N = 0 / 500 / 1000 / 2000**. | A degradation *curve* is the scale argument, not a point. Generating the top of the 500–2000 range once avoids a second generation session. |
| Embedder-swap criterion (fixed BEFORE measuring) | **Per-case**: at N=2000, every scenario keeps all expected nodes it found at N=0, AND mean recall drops ≤ 10 pts. Any documented trap death → `SWAP EMBEDDER` (multilingual-e5). | L5 lesson: aggregate recall hides critical-case death (the TPE chain died at 56% under an 84% mean). Fixing the criterion pre-measurement prevents post-hoc rationalization. |
| Truth-island isolation | **Zero edges between distractors and seed nodes.** Inter-domain edges exist only *among* distractors. | A single distractor↔seed edge changes seed neighborhoods, hence expansion results, hence the hand-derived ground truth of the 11 scenarios. Intra-distractor inter-domain edges still make expansion pollution realistic (a distractor anchor drags its own neighborhood in). |
| Domain vocabulary | Unchanged — distractors use the existing 10 domains. | In-domain noise is *closer* noise, the harder and more honest test. Also avoids a vocabulary ADR. |
| `created_from` | New literal **`synthetic`** → **ADR 0002** extends `CREATED_FROM_PATTERN`. | Schema v1 is frozen (hard rule 3). BUILD-ORDER already recorded the value; the ADR records the decision. `ingestion:synthetic` would fit the existing pattern but lies about provenance. |
| BUILD-ORDER deviation | `scripts/generate-distractors` is **not built**. The deliverables are the committed pool + the generation protocol (§3, replayable) + `retrieval-eval --distractors N` / `--distractor-sweep`. | Generation is a one-shot agent session; the pool is the artifact. A committed script would pretend the process is deterministic code when it is a reviewed LLM session. |

## 2. Data — `graph-distractors/`

New top-level directory, **never loaded by the app, the demo, or `graph-viz`** — only the
bench (and tests) read it.

```
graph-distractors/
  monetique.yaml            # ~200 nodes, YAML list under a `nodes:` key
  tpe-acceptation.yaml
  ... (one shard per domain, 10 total)
  edges.yaml                # PART_OF (intra-domain) + inter-domain edges, `edges:` key
```

Shard format: one file per domain holding a **list** of nodes (not one file per node —
2000 files would be repo noise). Within each shard, **every parent system precedes its
features**; this ordering is what makes prefix sampling valid (§4).

Node rules (all enforced by the existing fail-fast loader, plus new hermetic tests §6):
- Schema-v1 nodes, existing 10-domain vocabulary, standard id prefixes (`sys-`, `feat-`, …).
- `created_from: synthetic` on every node and every edge of the pool.
- Ids unique across pool **and** seed (seed ids are reserved).
- Type mix per shard ≈ seed proportions (features dominate: roughly 1/3 features, the rest
  spread over systems, constraints, decisions, projects, business objects, risks).
- **Fictional entities only** (hard rule 5) — restated in every generation prompt.

Edge rules:
- Every distractor feature has exactly one PART_OF to a distractor system *in the same
  shard* (loader cardinality rule).
- Inter-domain edges (DEPENDS_ON, CONSTRAINS, RELATES_TO, OPERATES_ON) connect distractors
  to distractors only. **No edge may reference a seed id** (tested).

## 3. Generation protocol (replayable, documented here)

1. **10 domain agents in parallel**, one per domain. Each prompt carries: the domain's
   one-line definition from `domains.yaml`, the node schema + id-prefix rules, the type
   mix, the systems-before-features ordering rule, the fictional-entities rule, the
   reserved seed ids for its domain, and an instruction to produce a *coherent fictional
   mini-ecosystem* (named systems with their features, plausible French banking-IT
   constraints/decisions/risks/projects around them) — not a flat list of lorem ipsum.
   Output: the domain shard + its intra-domain PART_OF/OPERATES_ON edges.
2. **1 edge agent** afterwards: reads shard summaries (system/object titles per domain),
   proposes inter-domain DEPENDS_ON/CONSTRAINS/RELATES_TO edges among distractors.
3. **Review by sampling** (orchestrator): read a random sample per shard for plausibility,
   French quality, and fictional-entities compliance; reject and regenerate weak shards.
4. **Mechanical gates**: full fail-fast load of seed + pool, id-uniqueness and
   no-seed-edge tests (§6). The pool is committed only once all gates pass.

To extend the pool later, rerun this protocol for additional shards/volume.

## 4. Loading — multi-dir support with deterministic prefix sampling

`core/graph/loader.py` (and a `GraphService` constructor on top) gains the ability to load
the seed dir **plus** a distractor dir with a node budget `N`:

- Take the first `ceil(N / 10)` nodes of each domain shard **in file order**; cap the
  total at `N` deterministically (alphabetical domain order for the remainder).
- Keep only pool edges whose endpoints are both included. The systems-before-features
  shard ordering guarantees a sampled feature's parent is always present, so PART_OF
  cardinality holds at any N — no RNG, no sampling seed to manage.
- Full validation (vocabulary, topology, cardinality, prefixes) runs on the merged graph.

The app-facing path (`GraphService.from_dir`) is untouched; the merged constructor is
bench/test-only API. `retrieval-eval` keeps rebuilding an ephemeral index per run, so no
fingerprint changes are needed.

## 5. Bench — `retrieval-eval --distractors N` / `--distractor-sweep`

- `--distractors N`: run the 11 scenarios against seed + N distractors (one point).
- `--distractor-sweep`: N = 0 / 500 / 1000 / 2000, printing the degradation curve.
- Per scenario and per N, in addition to today's recall / map size / missing:
  - **anchor intrusion** — how many of the anchors are distractors (`created_from ==
    "synthetic"`), since anchor ranking is *the* measured quantity;
  - **map pollution** — distractor share of the final map (anchors + expansion).
- **Realism sanity check** per N: similarity distribution (max + quartiles) of
  brief↔distractor scores vs brief↔non-expected-seed scores. If distractors do not reach
  the real-noise band (≈ 0.25–0.40), the bench prints a warning that the noise is too
  easy and the verdict is not trustworthy.
- **Automatic verdict** printed at the end of a sweep, criterion from §1:
  `HOLDS` — no per-case regression at N=2000 vs N=0 and mean recall drop ≤ 10 pts;
  `SWAP EMBEDDER (multilingual-e5)` otherwise, listing exactly which expected nodes died
  in which scenarios.

The bench stays out of CI (real model), like today.

## 6. Tests (hermetic, FakeEmbedder / pure YAML)

- Multi-dir loading: merged graph loads fail-fast; sampled subsets at several N values
  satisfy PART_OF cardinality and topology.
- Sampling determinism: same N → same node set, twice.
- Pool integrity (data tests over the real committed pool): every node/edge has
  `created_from: synthetic`; no edge references a seed id; ids unique across seed + pool;
  full pool loads with zero errors; each shard's parent-before-feature ordering holds.
- `created_from: synthetic` accepted by the schema (ADR 0002 regression test).

## 7. Docs & aftermath

- **ADR 0002** — add `synthetic` to `CREATED_FROM_PATTERN` (one paragraph: provenance
  label for generated stress-test data, never produced by the runtime).
- After the first full sweep: record numbers + verdict in `docs/known-limits.md` (L4) and
  update `docs/BUILD-ORDER.md` (lot 0 done → next lot, or embedder swap inserted).
- The pool is demo-invisible by construction (separate dir); no UI work.

## Out of scope (explicit)

- Realistic-volume validation (messy real-world structure) — stays coupled to
  ecosystem-foundry, after W4.
- Embedder swap itself — only triggered by the verdict, executed as its own small step.
- Any retrieval constant tuning in reaction to the bench (L1 doctrine: precision is the
  W3 challenge layer's job).
