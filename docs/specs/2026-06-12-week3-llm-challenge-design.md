---
summary: validated W3 design — LLM providers (official SDKs), two-phase CHALLENGING with grounding gate + deterministic governance pull, brief enrichment, LLM question selection, end-to-end challenge bench
read_when:
  - implementing any W3 lot (core/llm, CHALLENGING, enrichment, questions, challenge bench)
  - questioning a W3 design decision taken on 2026-06-12
  - interpreting challenge-bench numbers or the grounding-gate contract
---

# Week 3 — LLM layer (providers + challenge + enrichment + questions) — Design Spec

Date: 2026-06-12
Status: validated in brainstorming session (this doc is the build contract for W3)
Upstream: MVP spec §2-3/§6 (states, LLM contract, error handling) · known-limits
**L1/L2/L3/L6** (the limits this chantier answers) and **L4-residual** (anchor
saturation on deep governance chains, measured 2026-06-12 — the pull in §4 is its
direct answer) · BUILD-ORDER W3 lots 1-4 · AGENTS.md hard rules 1/2/4/6.

W3 is where retrieval quality becomes judgeable: the recall-first net (qwen3, 95 %
at N=0, 68 % converging under 2000 distractors) now meets the layer that turns an
over-complete map into a justified, cited, challengeable scoping. Every LLM output
crosses a deterministic gate; the LLM never mutates state (hard rule 1).

---

## 1. Decisions taken (closing this brainstorm)

| Topic | Decision | Rationale |
|---|---|---|
| Scope | **One spec, five lots** (providers · CHALLENGING · enrichment · questions · bench+demo), executed in order, each demo-able. | The open points are coupled (the challenge schema dictates the provider contract; enrichment reuses the chip/ledger UI patterns). Two specs would cite each other in circles. |
| SDKs | **Official SDKs**: `mistralai` (Mistral, demo default) and `openai` (DeepSeek's documented client — dev/bench workhorse). `MockProvider` for CI. SDK imports confined to `core/llm/` (AGENTS.md rule). | Provider-maintained transport (auth, timeouts, backoff, typed errors); follows API evolutions; the FDE-Mistral narrative reads better on the official SDK. Content-level retry stays OURS (transport vs content retries are complementary, not conflicting). Rejected: raw httpx (re-writing tested plumbing), litellm (heavy third-party abstraction for 2 providers). |
| Challenge shape | **Filter + deterministic governance pull, two-message flow** (§4). LLM tool-use graph navigation: **parked** (recorded idea, not W3 — costly round-trips, less deterministic demo, brushes hard rule 1). | A pure filter cannot resurrect what retrieval never brought — and the measured L4 residual is exactly that (governance chains losing their anchors to twin clusters at N=2000 while staying 1 hop from surviving nodes). The pull is bounded, deterministic, provenance-carrying, hermetically testable. Two messages so the resurrected governance gets a real justification and a place in the challenge text (one message would bolt it on silently after the LLM spoke). Cost: +1 API call (~cents) + 2-3 s. |
| Enrichment gating | **Auto-applied, visible, revocable**: proposed additions go straight into the retrieval query AND render as "ajouté par l'IA" chips; one click removes the addition and re-runs retrieval. | Zero friction (retrieval is free), total transparency (never a hidden rewrite — MVP wording), revocation preserves user control. Rejected: pre-validation (a click per turn for vocabulary, not claims), routing through the challenge ledger (a search synonym is not an assertion about the ecosystem). |
| Validation granularity | **Two tiers.** Map pruning applies as a bloc: the map switches to the justified set; rejects stay visible in a collapsible panel with their reason, each restorable by click. **Claims** (links, inherited constraints, risks) go one-by-one through the propose/validate ledger. Proposed `domains[]` render as accept/reject chips. | ~40 keep/reject micro-decisions per session is the L6 fatigue all over again; claims are the substance of W4 write-back (`verified: true` presumes real per-claim human validation), so they keep item-level consent. |
| Measurement | **Full end-to-end challenge bench with a real LLM** (Loïc's call, over the no-LLM pull-only bench): 11 scenarios × N=0/2000, DeepSeek default, temperature 0, model version recorded, disk cache keyed (scenario, N, provider, prompt-hash) so re-runs only pay for what changed. Output reports recall **per stage** — raw retrieval → post-pull → post-LLM-keeps — plus final-map precision and the per-case trap criterion + thief autopsy (inherited). | Measures the actual product, not a proxy; the per-stage split keeps mechanism attribution inside the real bench (lot-0bis lesson: an unmeasured lever can be a silent no-op). Cost control via DeepSeek + cache. Out of CI like every real-model bench. |
| Demo | Scripted cash-back case end-to-end (§8). | The buried monetique freeze coming back WITH its challenge sentence is the product's founding argument. |

## 2. Lot 1 — `core/llm/`

- **Protocol**: `LLMProvider` with one method — `complete_json(system: str, user: str) -> dict`. Temperature 0 everywhere (bench reproducibility, demo stability).
- **Implementations**: `MistralProvider` (SDK `mistralai`, default `mistral-small-latest`, demo) · `DeepSeekProvider` (SDK `openai`, base_url DeepSeek, default `deepseek-chat`, dev + bench) · `MockProvider` (FIFO queue of scripted dict responses + call log; a test touching a real provider is a bug — hard rule 4).
- **JSON contract** (MVP §6): shared helper around the Protocol — parse; on invalid JSON or schema mismatch, ONE retry with the schema restated; then a clean French user-facing error. Transport retries (429, network) belong to the SDKs; content retries to us.
- **Config**: provider choice + model + keys via env (`SCOPEGRAPH_LLM_PROVIDER`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`), `.env` gitignored. Provider down → clear message, session state lives in the runtime, resumable (MVP §6).
- **Prompts**: externalized in `prompts/*.txt` (doctrine), written in French (their output is French product text), named per use: `challenge_triage.txt`, `challenge_claims.txt`, `enrich_brief.txt`, `pick_question.txt`.

## 3. Schemas (the provider-facing contracts)

Phase-1 triage output:

```json
{"verdicts": [{"node_id": "...", "verdict": "keep|reject", "reason": "français, 1 phrase"}]}
```

Phase-2 challenge output:

```json
{
  "pulled_justifications": [{"node_id": "...", "reason": "français"}],
  "claims": [{"kind": "depends_on|constraint_applies|risk|overlap",
               "node_ids": ["..."], "reason": "français"}],
  "domains": ["slug", "..."],
  "challenge_statement": "français, le défi argumenté"
}
```

Enrichment output: `{"additions": [{"text": "...", "kind": "synonym|business_object"}]}` (≤4 per turn).
Question-selection output: `{"node_id"|"domain": "...", "question": "français avec l'enjeu"}`.

## 4. Lot 2 — CHALLENGING (runtime + UI)

1. **Transition**: MAPPING → CHALLENGING automatically when the loop stabilizes (no
   trigger fires, or question cap reached) — the W2 exit condition, now with a next
   state. UI affordance to reopen MAPPING (a brief edit reopens it anyway).
2. **Message 1 — triage**: brief + Q&A + the over-complete subgraph (per node: id,
   type, title, description, domains; plus the edge list among submitted nodes and
   expansion provenance) → phase-1 verdicts. **Gate A**: any verdict whose node_id
   is not in the submitted set is dropped and surfaced; missing nodes default to
   keep (recall-first: the LLM must argue to remove, never silently lose).
3. **Governance pull (runtime, deterministic — the L4-residual answer)**: from the
   kept set, 1 hop along **CONSTRAINS and SUPERSEDES edges, plus adjacent
   `decision`/`risk` nodes**, excluding rejected nodes; capped at `PULL_CAP = 10`
   (constant in `core/retrieval/config.py`, structural); each pulled node carries
   provenance ("ramené via sys-moteur-autorisation ← CONSTRAINS"). Pure graph
   traversal: hermetically testable, no LLM.
4. **Message 2 — challenge**: stabilized map (keeps + pulled) → phase-2 output.
   **Gate B**: every claim's node_ids must exist in the stabilized map; `kind`
   must map to an edge type legal per TOPOLOGY between the cited node types
   (overlap/risk claims cite nodes without implying an edge); `domains` filtered
   against the controlled vocabulary; pulled nodes lacking a justification keep
   the structural provenance label. Every rejection is rendered in the UI with its
   reason — never silent (hard rule 2).
5. **Ledger**: claims land as pending proposals; the user accepts/rejects each.
   Accepted claims + accepted domains + the kept map are the CHALLENGING output
   (and the substance of W4 write-back). The ledger is runtime state, serialized
   with the session.
6. **UI** (extends the W2 page): map animates to the justified set · "Rejetés (N)"
   collapsible panel, reason shown, "restaurer" per node · claims as cards with
   accepter/refuser · domain chips · the challenge statement rendered as the
   assistant's message. Gate rejections appear in a distinct "réclamations de
   l'IA rejetées par le runtime" strip — it is a demo feature.
7. **Parked (recorded, not built)**: LLM tool-use navigation (`neighbors(node)` on
   demand during the challenge) — revisit after W4 if the pull proves too rigid.

## 5. Lot 3 — Brief enrichment (answers L2)

Before each retrieval run (initial brief + every answer), one `enrich_brief` call
proposes ≤4 additions (synonyms, business objects — e.g. « entrée en relation » →
« création de client », « dossier KYC »). Additions are appended to the retrieval
query text only (the user's own words stay untouched), rendered as removable chips,
and logged in the brief (`enrichments[]`, serialized). Removing a chip re-runs
retrieval without it. Provider down or invalid JSON twice → skip enrichment for the
turn, discreet UI notice, never blocking (enrichment is sugar, not a dependency).

## 6. Lot 4 — LLM question selection (answers L3 + the L6 slug exposure)

The runtime keeps deciding WHETHER to ask (T1/T2/T3 triggers, precedence, asked-log,
cap — all unchanged). What the LLM adds depends on the trigger:

- **T3 (pivot)** — the real L3 fix: the runtime collects ALL qualifying pivot
  candidates (every expansion-only node in an unknown domain, grouped by domain
  with their expansion mass) instead of taking the first by score; one
  `pick_question` call chooses the candidate that matters and phrases the question
  with the stakes ("Le gel des évolutions monétiques est actif jusqu'à fin T3 —
  ce projet doit-il aboutir avant ?").
- **T2 (domain tie)** — candidates are exactly the two tied domains; the LLM only
  rephrases with French labels and what distinguishes them (no selection needed).
- **T1 (weak brief)** — no candidates; the LLM only rephrases the "précisez"
  template using the brief's own words.

The W2 templates remain the permanent fallback (provider down, invalid JSON twice,
or — gated — the LLM picks an id outside the candidate list).

## 7. Lot 5a — Challenge bench (the W3 measurement)

New script `scripts/challenge-eval` (real models, out of CI):

- Scenario ground truth factored out of `retrieval-eval` into a shared importable
  module (single source for both benches).
- For each of the 11 scenarios × N ∈ {0, 2000}: run retrieval (DEFAULT_PROFILE),
  then the full two-message challenge with a real provider (default DeepSeek,
  temperature 0; `--provider mistral` available).
- Reports per scenario and mean: recall of expected nodes at three stages — **raw
  retrieval → post-pull → post-LLM-keeps** — plus final-map size and precision, and
  the per-case trap criterion with the thief/reject autopsy (which expected nodes
  did the LLM itself reject — a new failure class worth watching).
- **Disk cache** keyed (scenario, N, provider, model, prompt-hash) under
  `.bench-cache/` (gitignored): a re-run after a prompt edit only re-pays the
  affected calls. Model name + version logged in the output header.
- Success reading (not a pre-committed gate this time — exploratory first run):
  the pull must recover governance traps at N=2000 (the L4 residual), and the
  post-LLM map must hold recall while shrinking (precision is W3's whole point —
  L1). Numbers land in known-limits L4/L1 and BUILD-ORDER, as always.

## 8. Lot 5b — Demo script (W3 exit)

Scripted run (clean 72-node seed, Mistral): cash-back brief → enrichment chips
appear → map refines → one LLM-phrased trigger question with stakes → CHALLENGING:
map shrinks with reasons, rejected panel, **the monetique freeze pulled back with
its justification and challenged in the statement**, claims accepted via ledger →
challenge statement rendered. This is the W3 "more convincing demo" increment
(north star).

## 9. Testing & error handling

- Hermetic suite (hard rule 4): gates A/B, pull traversal + cap + provenance,
  ledger transitions, enrichment chip lifecycle, question fallback, JSON-retry
  helper, state transitions — all with MockProvider scripted responses.
  FakeEmbedder unchanged. No network, no keys, no model downloads.
- Error handling: MVP §6 verbatim (one schema-reminder retry → clean French error;
  provider down → resumable session; ungrounded → visible rejection).
- `ruff` clean; French/English split per hard rule 6 (prompts and all LLM-facing
  output text French; code English).

## Out of scope (explicit)

- SCOPING / DRAFTING / VALIDATED states (W4: dossier, write-back, eval run).
- LLM tool-use graph navigation (parked, §4.7).
- Multi-turn polluted sweep & anchor-capacity (TOP_K) chantier — recorded
  follow-ups, naturally re-measured once the challenge layer exists.
- Streaming, conversation memory beyond the brief, any retrieval constant change.
