---
summary: validated W3 design — LLM providers (official SDKs), EDB template as the conversation engine, fluid graph-woven interview, two-phase challenge with grounding gate + governance pull, end-to-end challenge bench
read_when:
  - implementing any W3 lot (core/llm, EDB template, conversation orchestrator, CHALLENGING, challenge bench)
  - questioning a W3 design decision taken on 2026-06-12
  - interpreting challenge-bench numbers or the grounding-gate contract
---

# Week 3 — LLM layer (providers + EDB conversation + challenge) — Design Spec

Date: 2026-06-12
Status: validated in brainstorming session (this doc is the build contract for W3)
Upstream: MVP spec §2-3/§5/§6 (states, dossier sections, LLM contract, error handling) ·
known-limits **L1/L2/L3/L6** (the limits this chantier answers) and **L4-residual**
(anchor saturation on deep governance chains, measured 2026-06-12 — the pull in §5 is
its direct answer) · BUILD-ORDER W3 lots 1-4 · AGENTS.md hard rules 1/2/4/6.

**The product experience this spec builds (north star for every lot):** the user
describes a need and then simply talks to someone who *knows the company*. No
graph-question block, no linear form: one fluid conversation in which every question
is justified by something — a graph ambiguity or a missing section of the **EDB**
(expression de besoin, the project's first framing document) — and graph knowledge is
woven INTO the EDB questions. The EDB builds itself visibly while they talk. That
woven, grounded conversation IS the challenge.

---

## 1. Decisions taken (closing this brainstorm)

| Topic | Decision | Rationale |
|---|---|---|
| Scope | **One spec, five lots** (providers · EDB template + conversation orchestrator · CHALLENGING · bench · demo), executed in order, each demo-able. | The open points are coupled (the challenge schema dictates the provider contract; the EDB template frames the challenge prompts; the orchestrator consumes both). |
| SDKs | **Official SDKs**: `mistralai` (Mistral, demo default) and `openai` (DeepSeek's documented client — dev/bench workhorse). `MockProvider` for CI. SDK imports confined to `core/llm/`. | Provider-maintained transport (auth, backoff, typed errors); follows API evolutions; the FDE-Mistral narrative reads better on the official SDK. Content-level retry stays OURS (transport vs content retries are complementary). Rejected: raw httpx (re-writing tested plumbing), litellm (heavy abstraction for 2 providers). |
| EDB as conversation engine | **A versioned EDB template is runtime state**: 12 sections with owners and fill status; the conversation is driven by it (decided 2026-06-12 evening, Loïc: the user must feel they are talking to someone who knows the company, never filling a form). | The document format is the LLM's thinking frame from the first turn — W3 ends with a partially filled, coherent EDB instead of floating claims to re-map in W4. Completeness becomes checkable ("2 sections manquantes") instead of hoped-for. |
| Conversation shape | **One mixed question pool, one question per turn**: graph-ambiguity triggers (T1/T2/T3, unchanged, priority) ∪ missing-EDB-section gaps. Graph knowledge is woven into EDB questions. Free-text answers can fill several sections at once via gated extraction. The state machine survives internally (hard rule 1) but is invisible UX. | Kills the "bloc graphe puis questionnaire linéaire" failure mode explicitly rejected by Loïc. The pivot questions (T3) ARE perimeter questions — the two pools were always one. |
| Challenge shape | **Filter + deterministic governance pull, two-message flow** (§5). Claims carry their target EDB section. LLM tool-use graph navigation: **parked** (recorded idea, not W3). | A pure filter cannot resurrect what retrieval never brought — the measured L4 residual is exactly that. Two messages so resurrected governance gets a real justification and a place in the challenge text. Claims land as conversation cards when the map stabilizes, not as an end-of-flow wall. |
| Enrichment gating | **Auto-applied, visible, revocable** chips ("ajouté par l'IA"); removal re-runs retrieval. | Zero friction, total transparency, user control preserved. |
| Validation granularity | **Two tiers**: map pruning as a bloc (rejects in a collapsible, restorable panel); claims and extracted EDB-field updates one-by-one (accept/édit/reject — they are the substance of the document and of W4 write-back); domains as chips. | ~40 keep/reject micro-decisions is the L6 fatigue; per-claim consent is what `verified: true` presumes. |
| Measurement | **Full end-to-end challenge bench with a real LLM** (Loïc's call): 11 scenarios × N=0/2000, DeepSeek default, temperature 0, model version recorded, disk cache keyed (scenario, N, provider, model, prompt-hash). Per-stage recall: raw retrieval → post-pull → post-LLM-keeps. | Measures the actual product; the per-stage split keeps mechanism attribution (lot-0bis lesson: an unmeasured lever can be a silent no-op). Out of CI. |
| W3/W4 boundary | W3 ends with the EDB **existing, visibly filling, structurally complete-checkable**. W4: final rendering/export (.md), write-back, three-arm eval. | Protects W3 size; rendering is cheap once fields are structured. |

## 2. The EDB template (v1 — `core/dossier/template.py`)

Sections, frozen field ids, owner mix (sources: standard French expression-de-besoins
+ note-de-cadrage structures, merged 2026-06-12; links in the brainstorm log):

| id | Section (FR) | Filled by |
|---|---|---|
| `contexte` | Contexte & raison d'être | user + graph (node refs) |
| `besoin` | Expression du besoin | user, challenged by graph (overlaps) |
| `utilisateurs` | Utilisateurs & parties prenantes (+ sponsor) | user + graph |
| `objectifs` | Objectifs & critères de réussite | user |
| `perimetre` | Périmètre in / hors périmètre | user + graph (T3 pivots land here) |
| `exigences` | Exigences (fonctionnelles / non-fonctionnelles) | user + graph (inherited constraints → NF) |
| `dependances` | Dépendances & systèmes impactés | graph (validated claims) |
| `contraintes` | Contraintes héritées | graph (validated claims) |
| `risques` | Risques initiaux | graph + user |
| `jalons` | Jalons / échéance cible | user + graph (dated decisions) |
| `challenge` | Challenge & arbitrages ouverts | LLM (challenge statement + open items) |
| `carte` | Context Map | runtime |

Each section holds: status (`empty | partial | filled`), entries (each with source:
`user | claim:<id> | llm`, text FR, node refs where applicable), and a one-line FR
prompt-hint used by the orchestrator. The template is versioned (`EDB_TEMPLATE_V1`);
the session serializes its EDB state. Deterministic completeness check =
runtime code, no LLM.

## 3. Lot 1 — `core/llm/`

- **Protocol**: `LLMProvider.complete_json(system: str, user: str) -> dict`,
  temperature 0 everywhere.
- **Implementations**: `MistralProvider` (SDK `mistralai`, default
  `mistral-small-latest`) · `DeepSeekProvider` (SDK `openai`, DeepSeek base_url,
  default `deepseek-chat`) · `MockProvider` (FIFO scripted responses + call log).
- **JSON contract** (MVP §6): shared helper — parse; on invalid JSON/schema, ONE
  retry with the schema restated; then a clean French user-facing error. Transport
  retries belong to the SDKs, content retries to us.
- **Config**: `SCOPEGRAPH_LLM_PROVIDER`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`
  via env/`.env` (gitignored). Provider down → clear message, resumable session.
- **Prompts**: externalized `prompts/*.txt`, written in French: `enrich_brief.txt`,
  `pick_question.txt`, `extract_fields.txt`, `challenge_triage.txt`,
  `challenge_claims.txt`.

## 4. Lot 2 — Conversation orchestrator (answers L2, L3, and the form-feeling)

Runs every turn, deterministic skeleton (hard rule 1):

1. **Enrichment** (pre-retrieval): one `enrich_brief` call proposes ≤4 additions
   (synonyms/business objects); auto-applied to the retrieval query only, rendered
   as removable chips, logged in the brief. Failure → skip, discreet notice, never
   blocking.
2. **Retrieval re-runs** (free) → map updates.
3. **Field extraction**: one `extract_fields` call reads the user's last free-text
   message and proposes EDB entries (`{section_id, text, node_refs?}` list). Gate:
   section ids must exist; entries land as *pending* cards the user accepts/edits/
   rejects (same ledger pattern as claims). The user talks freely; the document
   catches what they said.
4. **Question selection**: the runtime builds ONE candidate pool —
   graph-ambiguity candidates (T1/T2/T3, precedence and asked-log unchanged,
   priority over gaps) ∪ EDB gap candidates (empty/partial sections, template
   order). One `pick_question` call receives the pool with graph context per
   candidate and returns `{candidate_id, question_fr}` — the question must weave
   the graph into the section ("Pour le périmètre : l'acceptation en magasin passe
   par les TPE, gelés jusqu'à fin T3 — in ou out ?"). Gate: candidate_id must be
   in the pool, else template fallback. W2 templates remain the permanent fallback
   (provider down, invalid JSON twice). Per-trigger LLM roles: T3 = real selection
   among ALL qualifying pivots (the L3 fix); T2 = rephrase the two tied domains
   with French labels; T1 = rephrase "précisez" with the brief's words.
5. **Question cap** per session unchanged; when the pool is empty (no ambiguity,
   EDB filled), the conversation naturally lands on the challenge summary and W4's
   exit.

UX consequence: there is no visible phase boundary anywhere — questions about the
business and questions about the graph interleave by pertinence.

## 5. Lot 3 — CHALLENGING (the claims moment, woven not walled)

Trigger: the map stabilizes (no graph-ambiguity trigger fires — the W2 exit
condition). The state machine moves MAPPING → CHALLENGING internally; the
conversation just continues.

1. **Message 1 — triage**: brief + Q&A + over-complete subgraph (per node: id,
   type, title, description, domains; edges; expansion provenance) →
   `{"verdicts": [{"node_id", "verdict": "keep|reject", "reason"}]}`. **Gate A**:
   verdicts on unknown ids dropped + surfaced; missing nodes default to keep
   (recall-first: the LLM must argue to remove).
2. **Governance pull (runtime, deterministic — the L4-residual answer)**: from the
   kept set, 1 hop along CONSTRAINS/SUPERSEDES + adjacent `decision`/`risk` nodes,
   excluding rejected nodes, capped `PULL_CAP = 10` (structural constant);
   provenance carried ("ramené via sys-moteur-autorisation ← CONSTRAINS").
   Hermetically testable, no LLM.
3. **Message 2 — challenge**: stabilized map (keeps + pulled) →

```json
{
  "pulled_justifications": [{"node_id": "...", "reason": "français"}],
  "claims": [{"kind": "depends_on|constraint_applies|risk|overlap",
               "node_ids": ["..."], "target_section": "dependances|contraintes|risques|perimetre|jalons",
               "reason": "français"}],
  "domains": ["slug"],
  "challenge_statement": "français — le défi argumenté"
}
```

   **Gate B**: claim node_ids ∈ stabilized map; `kind` compatible with TOPOLOGY
   between the cited node types (overlap/risk cite without implying an edge);
   `target_section` must be one of the claim-writable sections — exactly the enum
   above (`dependances`, `contraintes`, `risques`, `perimetre`, `jalons`); domains
   filtered against the vocabulary; unjustified pulled nodes keep their structural
   label. Every
   rejection rendered with its reason — never silent (hard rule 2).
4. **Claims as conversation cards**: each accepted claim writes its entry into its
   target EDB section (source `claim:<id>`); the challenge_statement lands in the
   `challenge` section and as an assistant message. The conversation then resumes
   on remaining EDB gaps (§4.4) — no wall, no phase screen.
5. **Parked**: LLM tool-use navigation (`neighbors(node)` during challenge) —
   revisit after W4 if the pull proves too rigid.

## 6. UI (extends the W2 page)

Three panes now: chat · Context Map · **EDB en construction** (the 12 sections,
filling live, completeness badge "2 sections manquantes"). Plus: enrichment chips
on the brief · "Rejetés (N)" collapsible restorable panel on the map · claim and
extracted-field cards inline in the chat (accepter / éditer / refuser) · domain
chips · a distinct strip for gate-rejected LLM output (demo feature). Map shrink
animation at challenge time answers L6.

## 7. Lot 4 — Challenge bench (the W3 measurement)

New script `scripts/challenge-eval` (real models, out of CI): scenario ground truth
factored into one shared importable module (single source with `retrieval-eval`).
For each of the 11 scenarios × N ∈ {0, 2000}: retrieval (DEFAULT_PROFILE) → full
two-message challenge with a real provider (default DeepSeek, temperature 0,
`--provider mistral` available). Reports per scenario and mean: recall at three
stages — **raw retrieval → post-pull → post-LLM-keeps** — final-map size and
precision, per-case trap criterion, autopsy including the new failure class
(expected nodes the LLM itself rejected). Disk cache under `.bench-cache/`
(gitignored) keyed (scenario, N, provider, model, prompt-hash); model name+version
in the output header. Exploratory first run (no pre-committed gate): the pull must
recover governance traps at N=2000, the post-LLM map must hold recall while
shrinking (L1). Numbers land in known-limits L4/L1 + BUILD-ORDER.

## 8. Lot 5 — Demo script (W3 exit)

Scripted run (clean seed, Mistral): cash-back brief → enrichment chips → map
refines → a woven question (graph context + perimeter section) → free answer that
fills two EDB sections at once (extraction cards) → challenge: map shrinks with
reasons, **the monetique freeze pulled back, justified, challenged in the
statement**, claims accepted → EDB panel showing graph sections filled, user
sections progressing, completeness badge. The "talking to someone who knows the
company" feeling is the demo's success criterion (north star).

## 9. Testing & error handling

- Hermetic (hard rule 4): gates A/B, pull traversal/cap/provenance, EDB template
  state machine (statuses, entry sources, completeness), orchestrator pool
  building + precedence + fallbacks, extraction gating, ledger transitions,
  JSON-retry helper — all with MockProvider scripted responses. No network, no
  keys, no downloads.
- Error handling: MVP §6 verbatim. Enrichment/extraction failures never block a
  turn; question selection falls back to templates; challenge failure → clean
  French error, session resumable.
- `ruff` clean; language split (hard rule 6): prompts and all LLM-facing output
  French, code English.

## Out of scope (explicit)

- EDB rendering/export (.md) and DRAFTING/VALIDATED states — W4, on the filled
  template.
- Write-back, three-arm eval run — W4.
- LLM tool-use graph navigation (parked, §5.5).
- Multi-turn polluted sweep & anchor-capacity (TOP_K) chantier — recorded
  follow-ups.
- Streaming, conversation memory beyond brief+EDB, retrieval constant changes.
