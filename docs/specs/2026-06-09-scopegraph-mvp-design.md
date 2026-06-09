---
summary: validated MVP design — decisions closing the kickoff's open points, architecture, scoping loop, milestones
read_when:
  - implementing any MVP component
  - questioning a design decision taken on 2026-06-09
---

# scopegraph MVP — Design Spec

Date: 2026-06-09
Status: validated in brainstorming session (this doc is the build contract for the MVP)
Upstream: [docs/project-kickoff.md](../project-kickoff.md) — positioning, pivot story, graph schema v1, MVP scope. This spec does not repeat the kickoff; it records the decisions taken on the points the kickoff left open, and the resulting concrete design.

---

## 1. Decisions taken (closing the kickoff's open points)

| Topic | Decision | Rationale |
|---|---|---|
| Languages | **French**: all graph seed content (descriptions, decisions, risks), app UI, agent questions, challenge, generated dossier, demo script, eval cases. **English**: code (names, comments, docstrings), README, ADRs, repo docs. | Authentic French-banking demo (and a clean "French demo on a French model" narrative); repo stays legible to international reviewers. The README states this split explicitly as a design choice. |
| Interface | Minimal web UI from the start: FastAPI + a single Alpine.js page. Chat pane + live Context Map pane (Mermaid re-rendered as the session progresses) + propose/validate controls. | The propose/validate/apply flow and the live-refining map are inherently visual; demo legibility is the success criterion. Same pattern as use-case-assistant. |
| LLM providers | `LLMProvider` Protocol with three implementations: **Mistral (default, demo)**, **DeepSeek (dev workhorse, cheap iteration)**, **Mock (hermetic tests)**. Switch via env/config. | Career narrative requires Mistral; DeepSeek gives near-free iteration; the Protocol proves provider-agnosticism. Model capability is not critical: retrieval does the hard work, the LLM reasons over a pre-retrieved subgraph. |
| Embeddings | Local `sentence-transformers` model **`paraphrase-multilingual-MiniLM-L12-v2`** behind an `Embedder` Protocol; `FakeEmbedder` for tests. ChromaDB as vector store, persisted locally, re-indexed when YAML files change. | Corpus is ~25 French descriptions: multilingual is a requirement, local means zero cost/key/latency. CI never downloads PyTorch (FakeEmbedder only). |
| Conversation shape | One-shot initial description, then **iterative retrieval**: retrieval re-runs on every brief update (it is in-memory and effectively free). The runtime detects ambiguity deterministically and triggers targeted clarifying questions. | A single sentence is often enough to seed domains and a first map, but under-determined inputs (vague idea, scope-dependent pivots like in-store acceptance) need discriminating questions. Iterative retrieval handles both without a degraded mode. |
| Dossier content | The dossier combines **what the graph knows** (grounded ecosystem context) and **what only the user knows** (objectives, sponsor, scope, deadline), collected through graph-informed scoping questions. | A scoping dossier without the business side is an impact analysis, not a cadrage. |

## 2. Architecture

No database. At startup: load `graph/nodes/*.yaml` + `graph/edges.yaml` into an in-memory graph; index node descriptions into ChromaDB.

```
core/
  graph/       Pydantic models (schema v1, frozen — ADR 0001), YAML loader,
               GraphService: get_node, neighbors, k_hop, validate-on-load
  retrieval/   Embedder Protocol (+ SentenceTransformers & Fake impls),
               hybrid scorer (semantic + domain overlap boost), 1–2 hop traversal expansion
  llm/         LLMProvider Protocol; MistralProvider, DeepSeekProvider, MockProvider;
               JSON-output contract with one schema-reminder retry
  runtime/     The deterministic authority: ScopingSession state machine, ProjectBrief,
               ambiguity detection, grounding gate, propose/validate/apply ledger
  scoping/     challenge generation, graph-informed scoping questions, dossier renderer
               (Markdown, French), Context Map renderer (Mermaid)
web/           FastAPI routes + the single Alpine.js page (French UI)
prompts/       externalized prompt templates (English instructions, French output mandated,
               domain-vocabulary glossary included)
graph/         the seed data (YAML, French content) — also the write-back target
```

## 3. The scoping loop (core/runtime)

A session holds a living `ProjectBrief` (title, description, accumulated answers, proposed domains) and moves through a deterministic state machine:

```
DESCRIBING → MAPPING → CHALLENGING → SCOPING → DRAFTING → VALIDATED
```

1. **DESCRIBING**: user pastes a free-text idea (one sentence is fine).
2. **MAPPING** (iterative): retrieval runs immediately → preliminary Context Map. The runtime detects ambiguity with simple deterministic thresholds (v1: domain candidate scores too close; best semantic hit too weak; a pivot node whose inclusion depends on an unstated scope point). Each trigger → the LLM formulates one discriminating question (e.g. "in-store acceptance in scope?"). Each answer enriches the brief → retrieval re-runs → the map visibly refines. Loop exits when no trigger fires.
3. **CHALLENGING**: over the stable retrieved subgraph, the LLM proposes links, inherited constraints, risks, overlaps — **every claim must cite an existing node ID or it is rejected by the grounding gate** (rejections are surfaced in the UI, not silent). The LLM also proposes the new project's `domains[]`, gated against the controlled vocabulary. User accepts/rejects each proposal (propose → validate → apply ledger). Then the challenge statement is generated.
4. **SCOPING**: graph-informed scoping questions (scope arbitrations implied by accepted constraints) + the classic business side (objectives, sponsor, in/out scope, deadline). Answers become firm dossier lines.
5. **DRAFTING**: dossier rendered; user reviews.
6. **VALIDATED**: write-back — the project becomes a `Project` node, accepted links become edges, all `created_from: scoping:<dossier_id>`, `verified: true` (human-validated). Output = new YAML files, git-diffable.

The LLM never mutates state; it only returns proposals that the runtime validates and applies.

## 4. Retrieval (core/retrieval)

Hybrid score per node = semantic similarity (query = current brief text) **+ domain-overlap boost** (shared `domains[]` between proposed brief domains and node domains) → take top-K, then **expand 1–2 hops** through edges (expansion carries provenance: "included via `sys-moteur-autorisation` → `CONSTRAINS`"). The kickoff's canonical case is a unit test: "BNPL in the mobile app" must surface the TPE acceptance system (near-zero textual similarity, 2 hops via `monetique`).

## 5. Dossier (French, Markdown)

Sections: Contexte écosystème (grounded, node refs) · Objectifs & sponsor · Périmètre in/out · Dépendances acceptées · Contraintes héritées · Risques · Challenge & arbitrages ouverts · Context Map (Mermaid). Export = one `.md` file per dossier.

## 6. Error handling

- Ungrounded claim → rejected, flagged visibly in the UI (it is a demo feature, not a silent failure).
- Unparsable LLM output → one retry with the schema restated, then a clean user-facing error.
- Provider down → clear message; session state lives in the runtime, so the session resumes.
- Graph YAML invalid at load → fail fast at startup with the offending file/field.

## 7. Testing & eval

Hermetic pytest suite (no API key, no network, no model download): MockProvider with scripted responses + FakeEmbedder with deterministic vectors. Covered: schema validation & loader, GraphService traversal, hybrid scorer (incl. the BNPL→TPE 2-hop case), ambiguity triggers, grounding gate (accepts grounded / rejects ungrounded), state machine transitions, write-back round-trip (write then reload). CI (already in place) runs ruff + pytest on push.

Eval: ~5 documented cases in `docs/eval/` (French) where a well-written naive LLM prompt misses a dependency that scopegraph retrieves (2 hops away or buried in a Decision node). Drafted in week 1, run in week 4.

## 8. Milestones (~4 weeks of evenings)

- **W1**: ADR 0000 (pivot) + ADR 0001 (schema v1) · Pydantic models + loader + GraphService + tests · seed data 15–25 French nodes across ≥4 domains with the kickoff's deliberate traps (aliases MONAUT/« moteur d'autorisation », contradictory + superseded decisions, one 2-hop cross-domain chain) · README v1 · eval cases drafted.
- **W2**: Embedder + Chroma indexing · hybrid scorer + traversal · iterative MAPPING loop · first web screens (chat + map).
- **W3**: LLM providers (Mistral, DeepSeek, Mock) · grounding gate · propose/validate/apply · challenge + scoping questions.
- **W4**: dossier renderer · Context Map polish · write-back · scripted demo (BNPL, then a second scoping that sees the first) · eval run.

## 9. Out of scope (MVP)

Everything §5 of the kickoff excludes (DOCX, Confluence, dashboards, multi-agent…), plus: authentication, multi-user sessions, session persistence across restarts, d3/React map, document ingestion (ecosystem-foundry's job).

## 10. Parked ideas (noted, not committed)

Graph-governance safeguards identified during design review — cheap to add if the MVP lands early, otherwise roadmap material alongside ecosystem-foundry (which is the structural answer to graph maintenance: periodic re-ingestion refreshes node status and edges; see kickoff §2 and §8):

- **Write-back dedup guard**: before creating the `Project` node, similarity check against existing nodes → warn "looks like `proj-x` (87%) — create anyway / merge?".
- **`scopegraph lint`**: a command listing graph-rot signals — `ongoing` projects untouched for N months, orphan nodes, unresolved contradictory decisions, unverified edges.
- A short "graph governance" ADR freezing the boundary: scopegraph curates at scoping time; lifecycle/refresh belongs to ingestion (Project B).
