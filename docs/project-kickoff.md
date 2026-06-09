---
summary: founding contract — positioning, pivot from MAS, graph schema v1, MVP scope, roadmap
read_when:
  - questioning product positioning or scope
  - touching the graph schema or the domain vocabulary
  - starting a new MVP week or writing an ADR
---

# scopegraph — Project Kickoff

> **One-liner:** An AI scoping runtime for projects that don't exist in isolation. scopegraph grounds a new project idea in the existing ecosystem — systems, past projects, decisions, constraints — surfaces dependencies and risks, and produces a context-aware scoping dossier.

**Target context: banking IT.** The reference environment is the IT division of a retail bank, where applications are deeply interdependent: a card-payment (monétique) project influences or constrains POS-terminal (TPE) software, mobile banking, fraud scoring, regulatory reporting — and they must all carry the *same* inherited constraints (PSD2/DSP2, LCB-FT/AML, PCI DSS, internal standards). Nobody scopes that propagation explicitly today; it surfaces late, as incidents or rework. scopegraph's job is to make this cross-domain propagation visible **at scoping time**. The domain knowledge comes from first-hand experience as AI referent in a French banking IT group; all seed entities are **fictional and anonymized** (never real internal systems — banking secrecy and NDA apply).

**Key phrase:** *scopegraph helps scope a new project by understanding the project ecosystem it belongs to.*

This document is the single source of truth for starting the project. It captures the full design discussion (positioning, architecture, schema, MVP scope, roadmap). Read it entirely before writing any code.

---

## 1. Why this project exists (the pivot — material for ADR 0000)

scopegraph is the successor of a private project called **MAS** ("multi-agent system"), which turned fuzzy business needs into structured project proposals (EDB / SPEC / BACKLOG artifacts, Confluence integration, propose/validate/apply governance).

The problem: MAS overlapped with an existing public project, **use-case-assistant** (vague business AI idea → structured intake form). Seen from outside, MAS looked like "use-case-assistant with more complexity" — a better spec-filling assistant. The complexity wasn't justified by a visibly different promise.

The realization: in a real enterprise, **a project never arrives alone.** It is tied to legacy systems, past projects, prior decisions, known risks, data dependencies, owning teams, internal standards, and parallel initiatives. Classic scoping assistants ask "what's your goal, who are the users?" — they scope the project *as if it were isolated*. That's the actual gap.

The pivot: stop selling "an assistant that fills a better spec." Sell **context-aware project scoping for non-independent projects.** The flow is no longer `conversation → documents` but:

```
new need → existing ecosystem graph → links / dependencies / risks → contextualized scoping
```

Naming: the project was renamed from MAS to **scopegraph** because "multi-agent system" described yesterday's implementation, not today's promise. The old repo stays private as `mas-legacy`. The pivot story must be told in the README ("Why this project exists") and in `docs/adr/0000-pivot-from-mas.md`.

**Portfolio narrative (for the README and applications):**
`use-case-assistant` captures the need → `scopegraph` scopes it within everything that already exists → (later) `ecosystem-foundry` builds the ecosystem graph from documents. Three links, zero redundancy.

---

## 2. The two-project architecture

The original temptation was one monolith that both *builds* the ecosystem graph from documents and *uses* it for scoping. We deliberately split it into two projects that never talk to each other directly. **Their only contact point is the graph schema (the contract).**

| | **Project A — scopegraph (this repo)** | **Project B — ecosystem-foundry (later, separate repo)** |
|---|---|---|
| Nature | Product | Applied-research lab |
| Input | Fuzzy project idea (conversation) | Corpus of unstructured docs |
| Core | Hybrid retrieval + grounded reasoning + challenge | Entity extraction + resolution + adversarial edge verification |
| Output | Context Map + scoping dossier | Graph (schema v1) + eval report (precision/recall, cost/doc) |
| Graph source | Hand-seeded (15–25 entities) + **write-back** from each validated scoping | Generated from documents |
| Success metric | Quality of scoping vs. a naive LLM prompt | Precision/recall of entities and edges vs. a hand-labeled gold graph |

Why the split is right:
- It decouples **product risk** from **research risk**. Ingestion is by far the riskiest part; it must not block the demo.
- Each project has its own success criterion.
- It mirrors a proven pattern from TaupIA: curated graph on one side, separate enrichment pipeline with adversarial verification on the other (TaupIA ADR 0001).
- B's integration is trivial by construction: its output respects the schema A already consumes.

**Build order: A first, strictly.** The hand-seeded graph is enough for a demo in weeks. B alone shows nothing to a non-technical reviewer.

---

## 3. Core principles (non-negotiable)

1. **LLM proposes, runtime decides.** All state transitions go through a deterministic runtime authority. The LLM reasons; it never directly mutates the source of truth. (Pattern ported from MAS and fitMAS.)
2. **Mandatory grounding.** Every dependency, risk, or link the LLM claims MUST cite a node ID from the graph. The runtime rejects ungrounded claims. This is the anti-hallucination mechanism: the LLM will otherwise "find" plausible-but-false dependencies.
3. **Human validation.** Propose → validate → apply for every significant step (links accepted into the dossier, write-back into the graph).
4. **Schema is frozen as v1.** Any schema evolution requires an ADR. Schema drift would silently break the contract with Project B.
5. **Readable MVP.** The whole product must be explainable in five lines: *I describe a project. scopegraph finds the existing context. It shows the links. It challenges the need. It generates a contextualized scoping dossier.*

---

## 4. Graph schema v1 (the contract)

### Node types (5)

| Type | Purpose | Key fields |
|---|---|---|
| `System` | Existing software / data source | `id`, `name`, `aliases[]`, `description`, `owner_team`, `data_quality_notes`, `known_risks[]` |
| `Project` | Past or ongoing project | `id`, `name`, `aliases[]`, `description`, `status` (done/ongoing/cancelled), `owner_team`, `outcomes`, `known_risks[]` |
| `Decision` | A past decision that constrains the future | `id`, `title`, `statement`, `rationale`, `date`, `decided_by`, `still_active` (bool) |
| `Constraint` | Standard, regulation, policy, technical limit | `id`, `title`, `statement`, `source` (e.g., internal standard, EU AI Act), `severity` |
| `Risk` | Known risk attached to the ecosystem | `id`, `title`, `statement`, `likelihood`, `impact`, `mitigations[]` |

All nodes share: `id` (stable, human-readable slug like `sys-autorisation-carte`), `domains[]` (see below), `tags[]`, `created_from` (seed | scoping:<dossier_id> | ingestion:<doc_id>).

### Domains: the controlled vocabulary (banking IT)

`domains[]` is the field that materializes the "same theme / same feature" linking. It is a **controlled vocabulary** (documented in ADR 0001, extensible only via ADR), not free tags. Initial vocabulary, v1:

```
monetique            # card payments: authorization, clearing, card lifecycle
tpe-acceptation      # POS terminals & merchant acceptance
paiement-instantane  # instant payment / SEPA Inst rails
dsp2-open-banking    # PSD2, SCA, APIs, TPP access
lcb-ft               # AML/CFT, fraud scoring, sanctions screening
credit               # consumer & mortgage credit
banque-en-ligne      # web & mobile banking front ends
referentiel-client   # customer master data, KYC
editique-reporting   # statements, regulatory reporting
socle-si             # shared infrastructure, core banking, standards
```

Retrieval uses domain overlap as a **boost and a traversal bridge**: a new "fractional payment in the mobile app" idea shares `monetique` + `banque-en-ligne` with existing nodes, which pulls in the TPE acceptance system (via `monetique`) even when textual similarity is low. This — not free-text similarity — is how the monétique→TPE propagation gets caught. Constraints carry domains too, so a `Constraint` tagged `monetique` automatically becomes a candidate inherited constraint for *any* new project touching that domain.

The fields `data_quality_notes` and `known_risks` are **load-bearing**: they are what feeds the "challenge" step. A node that is only a `description` cannot generate a meaningful challenge.

### Edge types (5)

| Type | Meaning | Example |
|---|---|---|
| `DEPENDS_ON` | A needs B to function / be true | new assistant DEPENDS_ON incident taxonomy |
| `PRODUCED` | Project produced a system / decision | cleanup project PRODUCED dedup decision |
| `CONSTRAINS` | Constraint or decision limits a project/system | "exclude Safety topics" CONSTRAINS incident assistant |
| `SUPERSEDES` | Newer decision/system replaces older | Decision-2024 SUPERSEDES Decision-2021 |
| `RELATES_TO` | Weak generic link (last resort, must carry a `note`) | dashboard RELATES_TO incident assistant |

Every edge: `source_id`, `target_id`, `type`, `note`, `evidence` (node field or doc reference), `created_from`, `verified` (bool).

### Storage

Plain files first: one YAML per node in `graph/nodes/`, edges in `graph/edges.yaml`. Human-diffable, git-friendly, trivially loadable. No database for the MVP. An in-memory graph service loads everything at startup (same philosophy as TaupIA: for a small fixed graph, in-memory JSON beats a vector DB in speed and transparency — though scopegraph *does* add embeddings for the fuzzy-input side, see §5).

---

## 5. MVP scope — Project A (target: ~3–4 weeks of evenings)

### The workflow (the product in 6 steps)

```
1. User describes a fuzzy project idea (conversation).
2. scopegraph searches the ecosystem graph.
3. It retrieves related systems / projects / decisions / constraints.
4. It identifies dependencies, risks, overlaps, inherited constraints — every claim grounded in a node ID.
5. It challenges the need ("this project should not be scoped as a simple AI assistant; it depends first on…").
6. It produces a contextualized scoping dossier + Context Map. On validation, write-back into the graph.
```

### Components

1. **Seed data** (week 1, the most important and least technical work): 15–25 realistic **fictional banking-IT entities** spanning at least 4 domains so cross-domain links exist by construction. Suggested spine:
   - `System`: card authorization engine, TPE acceptance software, mobile banking app, instant-payment gateway, fraud-scoring engine, customer master data (KYC), core banking ledger.
   - `Project` (past/ongoing): SCA/DSP2 compliance program (done), TPE fleet software migration (ongoing), instant-payment launch (done), fraud-model refresh (done), incident-deduplication cleanup (done).
   - `Decision`: "all new payment flows must reuse the SCA orchestration built by the DSP2 program", "fraud scoring is the single decision point for payment risk — no parallel scoring", "TPE software updates are quarterly, no out-of-band releases".
   - `Constraint`: PCI DSS scope rules, LCB-FT screening mandatory on new payment rails, internal API standard, EU AI Act risk-classification for AI components.
   - `Risk`: stale KYC data quality, TPE fleet fragmentation (old firmware versions), instant-payment limits bypass scenarios.

   Include deliberate traps for later: aliases of the same system ("MONAUT" vs "moteur d'autorisation"), contradictory decisions, a superseded decision, and at least one **cross-domain propagation chain** (e.g., a `monetique` constraint that must reach a `tpe-acceptation` project through 2 hops). Seeding by hand is not cheating — it demonstrates the data schema (same approach as TaupIA's curated question base). The README states it plainly: *"the ecosystem registry is seeded; ingestion from documents is the roadmap (see ecosystem-foundry)."* All entities fictional; never mirror real internal systems.

2. **Hybrid retrieval** (week 2): semantic search over node descriptions (ChromaDB + a small embedding model, e.g. all-MiniLM-L6-v2 — already proven in MAS-Lite) **plus** domain-overlap boosting **plus** 1–2 hop graph traversal from the hits. Pure cosine similarity misses transitive and thematic links: "BNPL in the mobile app" must surface the TPE acceptance system even at near-zero textual similarity, because they share the `monetique` domain and a 2-hop path through the authorization engine. The domain bridge + traversal is the technically interesting piece.

3. **Reasoning chain + grounding gate** (week 3): LLM proposes links/risks/challenges over the retrieved subgraph; runtime validates that every claim cites an existing node ID; ungrounded claims are rejected or flagged. Propose/validate/apply for user acceptance.

4. **Context Map + dossier + write-back** (week 4):
   - **Context Map** (the flagship feature): a structural view of `New project → related systems / past projects / decisions / constraints / dependencies / risks / overlaps / missing evidence / scope implications`. Mermaid generation is enough for the MVP (d3/React later). Without this feature scopegraph looks over-engineered; with it, the complexity is legitimate.
   - **Scoping dossier**: Markdown export.
   - **Write-back**: on validation, the scoped project becomes a `Project` node, its decisions become `Decision` nodes, its links become edges (all `created_from: scoping:<id>`, `verified: true` because human-validated). This solves cold start through usage: the second scoping is richer than the first.

### Demo scenario (script it, week 4)

Input: *"We want to add a 'pay in 3 installments' option (BNPL) to the mobile banking app."*

A naive assistant asks: goal? users? available data? expected gains? — and scopes it as an isolated mobile feature.

scopegraph instead retrieves from the seed graph and grounds every claim in node IDs:
- the card authorization engine (`monetique`) and the decision *"all new payment flows must reuse the SCA orchestration from the DSP2 program"* → inherited dependency, not optional;
- the fraud-scoring engine and the decision *"single decision point for payment risk"* → the BNPL eligibility check cannot ship its own parallel scoring;
- the `credit` domain → installment payment is legally a credit product, pulling in credit-domain constraints the mobile team never thinks about;
- the TPE acceptance software (`tpe-acceptation`, 2 hops away via `monetique`) → if BNPL must also work in-store later, the quarterly-release decision on TPE software becomes a hard scheduling constraint;
- known risk: stale KYC data quality → eligibility decisions on stale data.

Then it challenges:

> *"This should not be scoped as a mobile feature. It is a credit product riding on the monétique stack: it inherits SCA orchestration, the single fraud-scoring decision point, credit-domain regulation, and — if in-store acceptance is in scope — the TPE quarterly release constraint. Scope and owners must reflect that."*

This is the moment the difference with a generic assistant becomes undeniable — and it is immediately legible to anyone who has worked in banking IT.

**The killer demo move:** scope a second project right after, and show that it "sees" the first one through write-back.

### Evaluation (plan from day 1)

For a frontier-lab dossier, prepare ~5 test cases where a naive well-written GPT/Claude prompt misses a critical dependency that scopegraph retrieves (because the dependency is 2 hops away or hidden in a decision node). Document them in `docs/eval/`. This eval rigor is what distinguishes a side project from deployment-engineer work.

### Explicitly OUT of scope for the MVP

DOCX generation · Confluence backend · release snapshots · full EDB → audit → SPEC → ready-for-dev workflow · rich dashboards · multi-agent orchestration · visible policy zoo. (All of these existed in MAS v1 and made it illegible. They may return later, serving the new promise.)

---

## 6. What to port from mas-legacy (surgically, not wholesale)

Keep the **patterns and knowledge**, rewrite the code clean:
- propose / validate / apply governance flow
- runtime-authority logic (deterministic state transitions)
- structured source-of-truth handling
- test utilities / hermetic test approach (mock LLM, no API key needed — same standard as TaupIA's 78 tests and use-case-assistant)

Do NOT port: Confluence integration, artifact-generation pipelines (EDB/SPEC/BACKLOG), the multi-agent layout, the 16-tool/5-family toolbox as-is.

---

## 7. Suggested stack & conventions

- **Python 3.12**, FastAPI backend, Pydantic v2 (consistency with TaupIA / use-case-assistant).
- LLM behind a thin provider layer (Protocol-based, like TaupIA's `LLMProvider`) — **include a Mistral provider** (career relevance) plus at least one other.
- ChromaDB for embeddings of node descriptions; graph itself in memory from YAML files.
- Frontend: minimal. CLI or a single-page Alpine.js/FastAPI UI like use-case-assistant is fine for the MVP. Mermaid for the Context Map.
- Externalized prompts (`prompts/*.txt`), hermetic pytest suite, CI from day 1, ADRs in `docs/adr/` (start with `0000-pivot-from-mas.md` and `0001-graph-schema-v1.md`).
- README in English, written early and treated as a deliverable: positioning, the pivot story, the 6-step workflow, the demo scenario, the honest "seeded registry / ingestion is roadmap" statement, and a roadmap section pointing to ecosystem-foundry.

---

## 8. Roadmap after the MVP

1. **ecosystem-foundry (Project B, separate repo, ~2–3 weeks):** one document type only (decision records / Confluence-style project pages), 20–30 **synthetic banking-IT docs** with deliberate traps (system aliases like "MONAUT"/"moteur d'autorisation", contradictory decisions, implicit cross-domain references). Pipeline: grounded entity extraction → entity resolution → **adversarial edge verification** (transpose TaupIA ADR 0001 from maths to enterprise). Deliverable = the **eval report**: entity & edge precision/recall vs. a hand-labeled gold graph, cost per document, failure-case analysis. The pipeline's output conforms to schema v1 (including `domains[]`), so plugging it into scopegraph is trivial.
2. Richer Context Map (interactive d3/React).
3. Re-introduce artifact generation (dossier → structured EDB/SPEC) only once the core promise is solid.

---

## 9. Career context (so priorities stay straight)

- Applications to AI deployment / FDE roles (Mistral, Anthropic, OpenAI) go out **this weekend** — the MVP must NOT block them. The profile line and CV present scopegraph as: *"currently reworking my scoping assistant into scopegraph, an ecosystem-aware scoping runtime — design public, MVP in progress."*
- Velocity matters more than completeness: being able to say "since my application, I shipped the schema + first grounded scoping" in an interview is the goal.
- The pivot story itself (better-intake-form → non-isolated-project scoping) is interview material; keep it crisp in ADR 0000.

---

## 10. First session with Claude Code — task list

1. Init repo `scopegraph`: structure (`core/`, `graph/`, `prompts/`, `tests/`, `docs/adr/`), pyproject/requirements, CI skeleton, pre-commit.
2. Write `docs/adr/0000-pivot-from-mas.md` (the story in §1) and `docs/adr/0001-graph-schema-v1.md` (§4).
3. Implement schema v1 as Pydantic models + YAML loader + in-memory graph service (load, get_node, neighbors, k-hop traversal) with unit tests.
4. Create the seed dataset: 15–25 nodes + edges, banking/logistics flavor, with the deliberate traps listed in §5.1.
5. Draft README v1 with the new positioning.

Then, in order: hybrid retrieval → grounding gate → challenge prompts → Context Map → dossier export → write-back.
