---
summary: short source of truth for the current state and the immediate next chantier
read_when:
  - starting a work session
  - checking what to do next
  - re-scoping before coding
---

# Build order

## Current state (2026-06-12, end of session 3)

- **W3 main lot DONE — LLM layer + EDB conversation + two-phase challenge**
  (branch `w3-llm-edb`, executed inline via executing-plans from
  `docs/plans/2026-06-12-week3-llm-edb.md`; spec
  `docs/specs/2026-06-12-week3-llm-challenge-design.md`):
  - `core/llm/`: LLMProvider Protocol + MockProvider, JSON contract (one
    schema-reminder retry, clean French error), prompt loader (`prompts/*.txt`,
    all French), Mistral + DeepSeek providers (official SDKs, lazy, `llm` extra),
    env factory (`SCOPEGRAPH_LLM_PROVIDER`).
  - `core/dossier/template.py`: EDB v1 — 12 frozen sections, owners, entry
    sources, binary completeness (the `partial` status is deferred to W4's
    renderer, noted in the plan).
  - `core/runtime/`: ledger (propose/validate, accept-with-edit) · mixed
    candidate pool (all qualifying pivots + EDB gaps, asked-log unified,
    profile-threaded) · per-turn LLM steps (enrichment chips ≤4 revocable,
    gated field extraction, pool-gated question pick — template fallback
    everywhere) · challenge mechanics (gate A triage with keep-by-default,
    deterministic governance pull cap 10, gate B claims, French subgraph
    renderings shared with the bench) · session orchestration (EDB-driven
    turns, two-message challenge, ledger application, restore/chip-removal).
  - `web/`: full session payload (edb, cards, rejected, gate_rejections,
    pulled, missing_sections) + proposal/enrichment/restore endpoints; 3-pane
    UI (chat+cards+chips · map+rejected panel+pulled styling · live EDB).
  - `scripts/challenge-eval`: end-to-end real-LLM bench (per-stage recall
    raw→keeps→+pull, lost_by_llm autopsy, disk cache in `.bench-cache/`,
    `--provider deepseek|mistral --n 0 2000`). Scenario ground truth moved to
    `core/benchdata/scenarios.py` (single source with retrieval-eval).
  - 200 hermetic tests, ruff clean. `provider=None` degrades to W2 behavior +
    gap questions (asserted in tests).
  - **NOT done (hard stop honored): the real-LLM bench run and the live Mistral
    demo — they need API keys and Loïc's go. Bench numbers land in known-limits
    L1/L4 in a follow-up session.**

## Previous state (2026-06-12, end of session 2)

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

## Next chantier — L7 triage levers, then the demo

The W3 bench ran 2026-06-12 (keys provided; deepseek-v4-flash, sweep N=0+2000).
Numbers and analysis recorded in known-limits **L1 (precision 13→53 %, map 11.5),
L4 (N=2000 end-to-end), L5 (the bench caught a missing-brief bug in the challenge
calls on day one), and the new L7** (triage rejects governance with plausible
"non spécifique" arguments; pull can't recover an explicit rejection). Remaining:
1. ~~L7 levers~~ DONE (2026-06-12 evening): prompt-only fix, +10–18 recall points on
   all three models (deepseek 90 %, mistral 91 %, grok 86 % final recall at N=0);
   S3 passes 6/6 everywhere; structural lever closed as unnecessary. Grok provider
   added (`grok-4.3`); model ids verified online (deepseek-v4-flash, mistral-small-
   latest→Small 4). All in known-limits L7.
2. ~~Conversation reliability levers 1–3~~ DONE (2026-06-13, from a live Mistral
   cadrage session — see below). 
3. The scripted Mistral demo: `docs/demo-w3.md` (cash-back walkthrough).
4. Merge decision on `w3-llm-edb`.

**Conversation levers 1–3 (2026-06-13, from a real cash-back cadrage session driven
through the live Mistral app).** Three reliability fixes, all measured live + hermetic:
- L1 *no silent turn*: past the question cap with EDB gaps remaining, a message
  acknowledged nothing — now always answers with what's left.
- L2 *graph-ambiguity-first*: the LLM could detour to a generic EDB-gap question
  while a graph pivot was pending (the live session opened on « quel problème
  métier ? » instead of a woven SI question). The runtime now offers ONLY graph
  candidates when present; live re-test opens on graph questions (passerelle IP →
  monétique → socle).
- L3 *chip proliferation*: 16 enrichment chips with near-duplicates in 6 turns →
  normalized dedup (case + trailing plural) + global cap 8 + no re-enrich on
  chip-removal reruns. Live re-test: bounded at 8, no exact dups.
- L4 *claim factual fidelity* DONE (2026-06-13): `node_provenance()` attaches each
  claim's cited nodes' authoritative seed text to the card, the UI renders it under
  the claim, and the claims prompt forbids transforming facts/dates (« à compter du
  15 janvier 2026 » → « jusqu'en 2026 ») — live: all 14 claims of a cash-back session
  carried their sources. Deterministic for claims; the free-prose challenge statement
  stays prompt-only (best-effort, no structured citations).
- Still open (observed in the same session, NOT yet done): LLM interpretation of
  pivot/tie answers (still W2 yes/no token parsing — « uniquement en magasin »
  confirms/excludes nothing), and a `conversation-eval` harness (scripted personas →
  full session → EDB completion / graph-vs-gap question ratio / claim-fidelity
  metrics) to make these levers measurable instead of eyeballed.

## Week 3 original scope notes (superseded by the spec above — kept for history)

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
