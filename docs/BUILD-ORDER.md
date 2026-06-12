---
summary: short source of truth for the current state and the immediate next chantier
read_when:
  - starting a work session
  - checking what to do next
  - re-scoping before coding
---

# Build order

## Current state (2026-06-12, end of session 2)

- **W3 lot 0bis DONE — embedder swap: e5-base rejected, Qwen3-Embedding-0.6B
  adopted as DEFAULT_PROFILE** (branch `w3-embedder-swap`, ready to merge; spec
  `docs/specs/2026-06-12-embedder-swap-design.md`, plan archived to
  `docs/archive/2026-06-12-embedder-swap.md`, subagent-driven + inline
  calibration; full numbers + thief annotation in known-limits **L4**, methodology
  lessons in **L5**):
  - Code: asymmetric Embedder Protocol (query/passage prefixes inside the
    embedder), per-embedder `RetrievalProfile` (MiniLM frozen + regression-locked,
    e5 kept for reproducibility of its rejection, qwen3 instruction-aware +
    macOS ST kwargs), profile threaded through retrieve/triggers/session, bench
    flags `--embedder`/`--top-n`/`--grid` + per-trap anchor autopsy, smoke prints
    the full-graph raw band. 147 hermetic tests, ruff clean.
  - Measured: e5-base failed the N=0 gate (ranking, not thresholds — cash-back
    brief ranks the monetique freeze 72/72). Qwen3 passed it as a strict per-case
    superset of MiniLM (95 % vs 89 %), then on the 2×2 grid degrades 95→68 % at
    N=2000 with a **converging** curve (MiniLM: 89→54 %, still falling). No cell
    passes the strict per-cell criterion; the thief annotation shows the qwen3
    residual is legitimate substitution (bench bias, L5) + **anchor saturation**
    on deep governance chains — an anchor-capacity/challenge-layer problem, not
    an embedder problem. Homonym class (S2) closed by qwen3 → the BM25-hybrid
    escalation loses its motivating case. TOP_N scaling proved a single-turn
    no-op (L5) — its real test is the multi-turn polluted sweep.
  - Recorded follow-ups (not blockers): multi-turn polluted sweep (measures the
    MAPPING recovery net + the real TOP_N effect) · anchor-capacity rethink
    (TOP_K vs twin clusters) — both naturally re-measured after the challenge
    layer exists.

- **W3 lot 0 DONE — distractor stress bench, verdict: SWAP EMBEDDER** (branch
  `w3-distractor-bench`, subagent-driven from `docs/archive/2026-06-11-distractor-stress-bench.md`,
  spec `docs/specs/2026-06-11-distractor-stress-bench-design.md`):
  - ADR 0002 (`created_from: synthetic`) · `core/graph/distractors.py` (pool loader:
    synthetic-only, pool-closed edges, topology-checked) · `GraphService.from_dirs`
    (deterministic prefix sampling) · `retrieval-eval --distractors N` /
    `--distractor-sweep` (anchor intrusion, map pollution, realism check, automatic
    verdict) · 2000-node committed pool in `graph-distractors/` (10 fictional domain
    shards + 148 inter-domain edges, agent-generated per spec §3, never in the demo).
  - 127 hermetic tests, ruff clean.
  - **Measured (known-limits L4): recall 89 % → 54 % at N=2000, mean anchor intrusion
    6.6/8, realism check valid. MiniLM's narrow band does not survive scale; the
    pre-committed criterion fires.**

- Repo bootstrapped: structure, pyproject, CI (ruff + pytest, green), pre-commit.
- Founding docs: `docs/project-kickoff.md` (its §4 schema superseded), MVP design spec
  `docs/specs/2026-06-09-scopegraph-mvp-design.md`, fine-grain schema spec
  `docs/specs/2026-06-10-graph-schema-fine-grain-design.md`.
- **W1 foundations DONE** (branch `w1-foundations`, executed via subagent-driven-development
  from `docs/plans/2026-06-10-week1-foundations.md`):
  - ADR 0000 (pivot) + ADR 0001 (schema v1 frozen: 7 node types, 7 edge types, topology
    matrix, domains as ecosystem data).
  - `core/graph/`: Pydantic models + TOPOLOGY, fail-fast loader (vocabulary, topology,
    PART_OF cardinality, cancelled-project rules), GraphService (`get_node`, `neighbors`,
    `k_hop` with path provenance). 37 hermetic tests, ruff clean.
  - Seed: 72 fictional French banking-IT nodes (9 systems, 24 features, 6 business objects,
    7 projects, 8 decisions, 12 constraints, 6 risks), 100 edges, 7 deliberate traps — each
    trap has an integration test in `tests/test_seed.py`.
  - README v1 · 6 eval cases drafted in `docs/eval/cases.md`.
- **Graph viewer** (2026-06-10): `./scripts/graph-viz` generates an interactive standalone
  Cytoscape view of the graph (filters, search incl. aliases, highlight mode). Built on
  `core/viz/payload.py` — the data seam the W2 web Context Map pane and the W4 scoping
  highlight will reuse. Spec: `docs/specs/2026-06-10-graph-viz-design.md` (amends the MVP
  spec: Context Map medium = interactive viewer; Mermaid deferred to the dossier export).

- **W2 retrieval + MAPPING + first screens DONE** (2026-06-11, branch `w2-retrieval-web`,
  subagent-driven from `docs/plans/2026-06-11-week2-retrieval-mapping-web.md`; spec:
  `docs/specs/2026-06-10-week2-retrieval-mapping-web-design.md`):
  - `core/retrieval/`: Embedder Protocol (SentenceTransformers lazy via the `embeddings`
    extra + FakeEmbedder), Chroma cosine index with fingerprint staleness, hybrid scorer
    (semantic + domain boost + 1–2 hop expansion with edge-path provenance, deterministic
    type-priority tie-break). Eval cases 1–2 are unit tests: the TPE 2-hop trap passes.
  - `core/runtime/`: ProjectBrief (the accumulating query), triggers T1/T2/T3 with
    asked-log + precedence, French template questions, ScopingSession (6-state enum,
    DESCRIBING→MAPPING active, question cap, guaranteed convergence; hedge answers
    never confirm a domain).
  - `web/`: FastAPI session endpoints (map payload rides the message response) + one
    Alpine/Cytoscape page (chat + live Context Map, anchors vs expanded styling) on the
    extended `core/viz/payload.py` seam (`only` + `annotations`).
  - `scripts/retrieval-smoke`: real-model calibration bench over the 6 eval briefs (not
    in CI — constants in `core/retrieval/config.py` are tuned by reading its output).
  - 102 hermetic tests, ruff clean. Run the app: `pip install -e ".[embeddings]"` then
    `uvicorn --factory web.app:create_app --reload`.

## Next chantier — Week 3 (LLM providers + grounding + challenge)

W3 is where retrieval quality becomes judgeable: W2's layer-2 bench (2026-06-11,
`./scripts/retrieval-eval`, findings in `docs/known-limits.md`) showed a recall-first net
(89 % recall, 13 % precision, no threshold fix possible) — **the challenge layer IS the
precision stage**. Scope, ordered by measured impact:

0. **DONE (2026-06-12) — embedder swap: Qwen3-0.6B adopted** (see Current state;
   e5 rejected at the gate, TOP_N scaling a single-turn no-op, BM25 escalation
   dropped with the homonym class). Lots 1-4 are unblocked.
1. `LLMProvider` Protocol + Mistral (default) / DeepSeek (dev) / Mock (hermetic), JSON
   contract with one schema-reminder retry (MVP spec §2).
2. **CHALLENGING + grounding gate + propose/validate ledger** — the LLM reads the
   over-complete retrieved subgraph, keeps only what it can justify, every claim cites a
   node ID or is visibly rejected. Answers known-limits **L1** (precision) and shrinks the
   map to a readable, justified set (**L6**).
3. **LLM brief enrichment before retrieval** (gated, visible brief additions — never a
   hidden query rewrite). Answers **L2** (vocabulary bridge: S6 went 0/7 → 5/7 only after
   a lucky user answer).
4. **LLM question selection + rephrasing** over the deterministic triggers (templates stay
   the permanent fallback). Answers **L3** (pivots beside the point) and the slug-exposing
   phrasing.
5. **Eval run preparation**: the three-arm protocol is now in `docs/eval/cases.md` —
   naive (a) vs full-graph-in-context (a′) vs scopegraph (b). Arm (a′) is the honest
   baseline at 72 nodes (known-limits **L4**: retrieval is a scale bet, not yet an
   empirical necessity — full eval run stays W4).

Brainstorm/plan first — no W3 spec exists yet. Open points for the brainstorm: SDK choice
(raw HTTP vs mistralai client) inside `core/llm/` only · how brief enrichments are
displayed/validated in the UI · challenge output schema and its grounding-gate contract ·
what the W3 demo must show end-to-end.

## Scale milestone (split, 2026-06-11 discussion)

The noise-robustness half is DONE (distractor bench 2026-06-12, re-run post-swap with
qwen3 the same day — both curves in known-limits L4). The *realistic-volume* half (messy
real-world graph structure, not plausible noise) still needs ecosystem-foundry output;
couple that final validation to the foundry kickoff, after W4. Hand-growing the demo
seed stays rejected (fictional-entities rule, curation cost, artificial coherence).

## Later

W4 dossier + Context Map polish + write-back + scripted demo + eval run. See MVP spec §8.

W4 note (decided in session, 2026-06-10): write-back needs a small TOPOLOGY-extension ADR —
allow `Project → DEPENDS_ON → System` and `Project → OPERATES_ON → BusinessObject` so an
in-flight project can express what it touches (collision detection). New `Feature` nodes are
NOT created at scoping write-back (intention ≠ reality); they enter the graph at delivery,
via `PRODUCED` (see fine-grain spec §6).
