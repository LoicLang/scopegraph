---
summary: validated W2 design — embeddings + hybrid scorer, deterministic MAPPING loop with template questions, first web screens
read_when:
  - implementing any W2 component (core/retrieval, core/runtime MAPPING, web)
  - questioning a design decision taken on 2026-06-10
  - wondering why the MAPPING loop has no LLM (or no agent)
---

# Week 2 — Retrieval, MAPPING loop, first web screens — Design Spec

Date: 2026-06-10
Status: validated in brainstorming session (this doc is the build contract for W2)
Upstream: MVP spec §2–§4, §8 (`2026-06-09-scopegraph-mvp-design.md`) · BUILD-ORDER W2 lots ·
graph-viz design (`2026-06-10-graph-viz-design.md`) for the Context Map payload seam.

W2 turns the static, traversable graph (W1) into the product's core promise: *describe a
project, scopegraph finds the existing context*. It is the chantier that makes eval cases 1
and 2 winnable — the 2-hop BNPL→TPE chain and the beneficiary constraint inheritance become
unit tests of the scorer.

---

## 1. Decisions taken (closing this brainstorm)

| Topic | Decision | Rationale |
|---|---|---|
| MAPPING questions without LLM | **Deterministic template questions**, assembled from graph content (which is already French). W3 adds LLM *rephrasing* on top; the template remains the permanent fallback. | The hard part is *what* to ask, and the trigger already knows it (typed payload: pivot node, conflicting domains). Templates are grounded by construction (can only cite existing nodes), hermetically testable, demo-able without any provider. Trigger logic — whether and what to ask — is runtime-owned forever (hard rule 1). |
| No agent in the loop | The pipeline is deterministic; **no LLM ever controls the flow** (decides when to search, when to ask). | Retrieval is in-memory and effectively free → always search first; the scores *are* the vagueness detector ("too broad for the graph" = best hit below threshold, observed, not predicted). An agent loop would break demo reproducibility, hermetic tests, and the product's differentiator vs naive-LLM scoping. If field usage demands more, the principled extension is widening what the LLM can *propose as brief enrichment* (gated, visible) — never handing it control flow. |
| Semantic query | **The query is the `ProjectBrief`** — a structured, accumulating object (description + Q/A + domains) — never the last message nor raw chat history. | A detail given at any turn permanently weighs in retrieval (nothing falls out of a window). Raw history would add noise (politeness, the assistant's own questions); the brief is curated by the runtime, visible, and replayable. |
| Out-of-graph signals | W2 does **nothing** about brief fragments no node covers (e.g. "payable in crypto") — assumed. W3's CHALLENGING LLM flags such white zones, labeled as ungrounded, in the dossier's "arbitrages ouverts". | A threshold detects a globally vague brief, not an isolated uncovered fragment. Graph finds what the *ecosystem* knows; the LLM (W3) challenges with what the *world* knows; the runtime keeps the two labeled apart. Demo examples stay on-graph. |
| No reranker | No cross-encoder rerank stage. | The corpus is 72 nodes: the semantic pass already scores *all* of it — there is no candidate-generation/precision split to fix. Stages (2) and (4) of the scorer *are* the rerank, with signals a generic cross-encoder lacks (domains, edges); the hard cases (TPE) have zero textual relevance, which a cross-encoder would rank even lower. If `retrieval-smoke` shows poor rankings, first escalation = a stronger embedder (multilingual-e5, bge-m3); a cross-encoder would slot between scorer stages (2) and (3) without touching anything else. |
| Choice A — embedded text per node | **A1: `name + aliases + description`** concatenated into one document per node. | Aliases are seed trap #1 (MONAUT ↔ « moteur d'autorisation ») — putting them in the embedded document solves it at the root. |
| Choice B — pivot trigger | **B1: derived definition, no schema change** — pivot = node reached *only* by expansion whose domains don't intersect the brief's domains (see §4). | Schema v1 is frozen (ADR required for any field). B1 gives a slightly stiff but correct question. **B2** (optional `scope_hint` field on nodes + mini-ADR + seed touch-up) is the recorded upgrade path if B1's phrasing proves too poor at the demo. |
| Choice C — map refresh | **C1: the `POST /message` response carries the map payload**; the front re-renders on receipt. No SSE/WebSocket. | The map only changes after a user message — push infrastructure is YAGNI. |

## 2. Embeddings & indexing (`core/retrieval/`)

- **`Embedder` Protocol**: `embed(texts: list[str]) -> list[list[float]]`.
  - `SentenceTransformersEmbedder` — `paraphrase-multilingual-MiniLM-L12-v2`, local. The
    `sentence_transformers` import lives in this module only (repo rule: no SDK import
    outside `core/llm/` and `core/retrieval/`) and is lazy: importing `core.retrieval`
    must not load PyTorch.
  - `FakeEmbedder` — deterministic, test-rigged: tests register `text fragment → vector`
    mappings, unknown texts get a stable hash-derived vector. CI never downloads a model.
- **ChromaDB**, persisted locally (`.chroma/`, gitignored). One collection; one document per
  node = `name + aliases + description` (A1); node id = Chroma id; `domains` and `type`
  stored as metadata.
- **Staleness**: a content hash of `graph/nodes/*.yaml` + `graph/edges.yaml` is stored
  alongside the index; on startup, hash mismatch → full re-index (72 nodes: cheap), match →
  reuse. Tests use an ephemeral in-memory Chroma client.

## 3. Hybrid scorer (`core/retrieval/`)

Single entry point, e.g. `retrieve(brief: ProjectBrief) -> RetrievalResult`:

```
(1) semantic   top-N over Chroma, query = brief.text()        score = cosine sim
(2) boost      score += ALPHA · |node.domains ∩ brief.domains|
(3) anchors    top-K nodes with boosted score ≥ TAU_ANCHOR
(4) expansion  GraphService.k_hop(≤ 2 hops) from anchors only
               expanded score = anchor score · DECAY^hops, keep if ≥ TAU_KEEP
               provenance = full edge path (k_hop already provides it)
```

- A node reached both semantically and by expansion keeps the max score and **both reasons**.
- Every result node carries its reason: `semantic(sim=0.62)` and/or
  `expanded(via sys-moteur-autorisation → DEPENDS_ON)`. Reasons feed the Context Map
  (W2) and the LLM context (W3) — noise stays visible and explainable.
- **Brief domains in W2** are derived deterministically: candidate domain score = sum of
  anchor scores carrying that domain; `brief.domains` = every domain whose candidate score
  ≥ `DOMAIN_FRACTION` · top candidate score (multi-domain projects are the norm — BNPL is
  credit + monétique + canal mobile). Top-2 within `DELTA` of each other → trigger T2 (§4)
  instead of guessing. User answers always override the derivation. (W3: the LLM may *propose* domains,
  gated against the vocabulary.)
- All knobs (`N`, `K`, `ALPHA`, `DECAY`, `TAU_*`, `DELTA`, `DOMAIN_FRACTION`,
  `MAX_QUESTIONS`) are named constants in
  one config module, calibrated with `scripts/retrieval-smoke` (§6) against eval cases —
  never tuned by intuition.

Expansion is the load-bearing wall: semantic search only needs to find the **anchors** (what
the user literally names — guaranteed findable by construction); everything else relevant is
relevant *because* it is edge-connected to an anchor. A relevant node with no edge path to
anything the project touches is a graph-curation gap, which no retrieval mechanism (agent
included) could find.

## 4. MAPPING loop (`core/runtime/`)

- **`ProjectBrief`** (Pydantic): `description`, `qa: list[QA]`, `domains: list[str]`,
  `excluded_domains: list[str]`. `brief.text()` concatenates description + answers for
  embedding.
- **`ScopingSession`**: the full state enum from the MVP spec
  (`DESCRIBING → MAPPING → CHALLENGING → SCOPING → DRAFTING → VALIDATED`) is declared now;
  only `DESCRIBING` and `MAPPING` transitions are implemented in W2 — the rest raise a
  clear "not implemented until W3/W4". Final architecture in place, later weeks fill states.
- **Triggers** — evaluated in order after each retrieval run, **one question per round**,
  hard cap `MAX_QUESTIONS` per session:

| # | Trigger (deterministic) | Template (French, assembled from graph content) | Resolution |
|---|---|---|---|
| T1 | best anchor score < `TAU_WEAK` | « Votre description est courte — pouvez-vous préciser le canal concerné et l'objet métier manipulé ? » | Fires at most once per session. |
| T2 | top-2 candidate domain scores within `DELTA` | « Le projet relève-t-il plutôt de {domaine_a} ou de {domaine_b} ? » | Answer sets `brief.domains`. |
| T3 (pivot) | a node reached **only** by expansion (semantic sim < `TAU_NOISE`) whose domains ∩ brief.domains = ∅ | « Le périmètre inclut-il {domaine} ? ({node.name} serait alors concerné) » | Yes → domain added to `brief.domains`; no → domain added to `excluded_domains`, its expansion-only nodes drop off the map. One question per *domain*, not per node. |

- **Convergence**: T1 fires once; each T2/T3 answer strictly resolves its own condition
  (domain set / domain included-or-excluded, never re-asked); `MAX_QUESTIONS` is the
  backstop. Loop exits when no trigger fires → map stable → session waits at end of
  MAPPING (W3 will take over with CHALLENGING).
- Every answer is appended to `brief.qa`, so it also enriches the semantic query on the
  next run — the loop converts hops into anchors (a confirmed pivot domain becomes direct
  text in the brief).

## 5. Web (`web/`)

- **FastAPI** + one Alpine.js page (French UI): chat pane (left) + live Context Map pane
  (right).
- Endpoints: `GET /` (the page) · `POST /api/session` → `{session_id, state}` ·
  `POST /api/session/{id}/message` with `{text}` → `{state, question | null, map, brief}`
  (C1: the map payload rides the response).
- Sessions in an in-memory dict — no persistence across restarts (MVP out-of-scope list).
- The map pane reuses `core/viz/payload.py` and the Cytoscape template from the graph
  viewer, extended with retrieval data: anchors highlighted, expanded nodes styled by
  provenance, score shown on hover. This is exactly the seam the graph-viz spec planned for.
- Errors: empty message → 422 · unknown session → 404 · graph load failure → fail fast at
  startup (existing loader behavior).

## 6. Testing

Hermetic pytest suite (no key, no network, no model download), consistent with W1:

- Indexing: document composition (A1), staleness hash (re-index on change, reuse on match).
- Scorer with rigged `FakeEmbedder`: domain boost arithmetic · anchors threshold ·
  expansion with provenance and decay · merge of semantic+expanded reasons.
- **Eval cases 1 and 2, mechanical form**: rig the embedder so the brief anchors on
  `sys-app-mobile`/credit nodes → assert `sys-logiciel-tpe` (+ `dec-releases-tpe-trimestrielles`)
  surfaces with a 2-hop provenance path; same pattern for the beneficiary inheritance chain
  (constraints via `obj-beneficiaire`).
- Triggers: one scenario per trigger + precedence order + cap + convergence (a scripted
  Q/A sequence ends with no trigger firing).
- Web: FastAPI `TestClient` round-trip (create session → describe → answer → stable map).
- **Assumed limit**: real MiniLM semantic quality is not hermetically testable. A local
  script `scripts/retrieval-smoke` (not in CI) runs the real embedder over the 6 eval
  briefs and prints rankings — it is the calibration bench for the §3 constants.

## 7. Out of scope (W2)

Everything LLM (providers, CHALLENGING and beyond, propose/validate ledger, grounding
gate), dossier, write-back, out-of-graph signal detection (decided above: W3), session
persistence, SSE/push, auth.

## 8. Execution

Branch `w2-retrieval-web` · lots in order 1→4 (embeddings, scorer, MAPPING, web), strict
TDD · implementation plan in `docs/plans/` (subagent-driven, like W1) · BUILD-ORDER updated
at session end.
