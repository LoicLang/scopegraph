---
summary: design for the post-challenge reliability fixes and the richer, precision-driven EDB
read_when:
  - implementing the 2026-06-14 real-user-audit fixes
  - touching post-challenge map coherence, EDB sufficiency, claim grounding, or statement quarantine
status: approved (brainstorm 2026-06-14)
---

# Post-challenge reliability + richer EDB — design

Source: the 2026-06-14 real-user audit (uncached Mistral, BNPL brief) recorded in
`docs/BUILD-ORDER.md`. Five confirmed defects, one spec. Brainstormed and approved
2026-06-14.

## Problem (verified against the code)

| # | Defect | Confirmed mechanism |
|---|---|---|
| 1 | Final map incoherent | `_map_round` rewrites `last_result` every turn ([session.py:216](../../core/runtime/session.py)); `rejected_nodes`/`pulled` are only set inside `_run_challenge`. Post-challenge, a volunteered precision re-runs retrieval → fresh, un-triaged `last_result`, while [app.py](../../web/app.py) subtracts a stale `rejected_nodes`. Excluded nodes (beneficiaries, instant-payment gateway) reappear raw on the graph. |
| 2 | Interview off-topic | Pool offers graph pivots on excluded domains and gap questions on already-shallow sections; relevance is not steered by what is vague vs decisive. |
| 3 | Grounding too permissive | `gate_claims` ([challenge.py:148](../../core/runtime/challenge.py)) checks node existence + section + non-empty reason only. No semantic check that the claim's conclusions are entailed by the cited provenance. 6/13 claims needed manual rejection. |
| 4 | Detected error kept | `statement_issues`/`statement_flags` are computed, then `edb.add_entry("challenge", …)` runs unconditionally ([session.py:267](../../core/runtime/session.py)). The flagged statement enters the EDB anyway. |
| 5 | Extraction fragile | Initial brief is never mined — `DESCRIBING→MAPPING` calls `_map_round(free_text=None)` ([session.py:106](../../core/runtime/session.py)). Extraction emits non-canonical section ids (`carta`, `parties_prenantes`) that the gate rejects, losing stakeholders. |

## Design principles (unchanged invariants)

- **The runtime decides; the LLM proposes within gates and the ledger.** Every new
  LLM step degrades deterministically: `provider=None` (or a failed JSON contract)
  falls back to today's behavior, never blocks a turn.
- **Guaranteed convergence.** The interview always terminates. New precision loops
  are bounded; `MAX_QUESTIONS` stays the hard ceiling.
- **Rejections are never swallowed** — they surface in the rejected/gate panels.

---

## 1. Live but coherent map (#1)

The map stays live (it re-retrieves on every precision), but it never moves against
a decision already made. Exclusions are commitments, not re-erasable suggestions.

- **`rejected_nodes` becomes a session-accumulated exclusion set.** It is no longer
  rebuilt each challenge: challenge rejects and user exclusions are *added* to it and
  it is never silently cleared by a rerun. `restore_node` remains the only removal.
  - Implementation note: keep the existing `dict[str, str]` (id → reason) so the UI
    still shows why a node was excluded; challenge rejects update it rather than
    replacing it.
- **Re-apply on every `SCOPING` round.** A volunteered precision re-runs
  `enrich → retrieve` (the map lives), then the payload subtracts the accumulated
  exclusions + `excluded_domains` — so the beneficiaries / instant-payment gateway
  the user excluded cannot return.
- **`pulled` is recomputed each round** on the current keeps (deterministic, cheap) —
  no stale governance pull.
- **New nodes are flagged, not re-triaged.** A `previously_mapped: set[str]` snapshot
  taken at challenge time lets the payload annotate genuinely new nodes
  (`role`/`provenance` → `"nouveau"`). New in-scope nodes are integrated by default
  (decision (i) — no extra manual triage); the user sees what changed at a glance.

Affected: `session.py` (state fields + `_run_challenge` + `_map_round`),
`web/app.py` `_annotations`/`_session_payload`, the static UI styling for the
`nouveau` annotation.

## 2. EDB sufficiency + challenge-for-numbers (#2, #5)

Root cause: completeness is **binary** — a section is "filled" at one entry and never
revisited ([template.py:79](../../core/dossier/template.py)). Replace presence with
**sufficiency**.

- **`EdbSectionSpec` gains `sufficiency_fr`** — the criterion that makes the section
  precise enough. Examples:
  - `objectifs` → at least one measurable success criterion (a number/target).
  - `jalons` → a dated milestone.
  - `exigences` → quantified volumetry / SLA where relevant.
  - `utilisateurs` → named sponsor **and** end users.
  - `perimetre` → both in- and out-of-scope stated.
  - (Sections where quantification is not meaningful keep a qualitative criterion.)
- **New LLM step `judge_section_sufficiency(provider, edb)`** (`llm_steps.py`),
  batched over the **filled** askable sections in one call →
  `{section_id: {"sufficient": bool, "followup_fr": str}}`. `provider=None` or a
  contract failure → all filled sections treated as sufficient (today's binary
  behavior). Result is computed once per turn.
- **`EdbState`: `missing_sections()` → `incomplete_sections()`.** A section is a gap
  candidate if **empty** OR **judged insufficient**. The empty-section question stays
  `prompt_hint_fr`; the insufficient-section question is the LLM's `followup_fr`
  (targeted: "+X % sur quoi, à quelle échéance ?").
- **Convergence:** each section is re-askable for precision **at most once**. Track a
  per-section `precision_asked: set[str]`; once asked (whatever the answer), the
  section is treated as sufficient for pool purposes. `MAX_QUESTIONS` unchanged.
  `EDB_COMPLETE` now means every askable section is sufficient-or-asked.
- **Extraction (#5):**
  - (a) The **initial brief is mined**: `DESCRIBING→MAPPING` passes the description as
    `free_text` to the first `_map_round`, so `extract_fields` runs on it (the October
    2026 milestone is captured without re-asking).
  - (b) The `extract_fields` prompt receives **id → title pairs** (not just ids) plus a
    strict "use only these ids" instruction; a defensive remap (`parties_prenantes →
    utilisateurs`, `carta → carte`) catches the known synonym slips before the gate.
  - (c) Exclusions are phrased "hors périmètre …" (prompt instruction).

Affected: `template.py` (spec field, `incomplete_sections`), `llm_steps.py`
(`judge_section_sufficiency`, `extract_fields` prompt wiring), `pool.py`
(`build_pool` uses `incomplete_sections` + carries the followup), `session.py`
(first-round brief mining, precision-asked tracking, completeness message),
`prompts/extract_fields.txt`, new `prompts/judge_sufficiency.txt`.

## 3. Clause-complete claim grounding (#3)

`gate_claims` stays pure and syntactic. Add a semantic pass after it.

- **New LLM step `judge_claim_grounding(provider, claims, service)`** (`llm_steps.py`),
  batched over the syntactically-valid claims: for each claim, are **all** its
  conclusions entailed by the cited nodes' provenance text (via `node_provenance`)?
  Returns per-claim `{grounded: bool, reason_fr: str}`.
- **Un-grounded claims are auto-rejected** — moved into `gate_rejections`
  (`kind: "claim"`, with the reason) instead of becoming accepted cards. Target:
  drive the 6/13 manual rejections toward zero.
- `provider=None`/failure → no semantic pass, today's syntactic gate alone (recall-first).

Affected: `session.py` `_run_challenge` (call after `gate_claims`, before card
creation), `llm_steps.py`, new `prompts/judge_claim_grounding.txt`.

## 4. Flagged statement quarantine (#4)

- In `_run_challenge`, after computing `statement_flags` and `statement_issues`:
  - **Clean statement** (both empty) → enters the EDB directly, as today (zero added
    friction).
  - **Flagged statement** (`issues` OR `flags` non-empty) → does **not** auto-enter.
    It becomes a **pending ledger proposal** carrying its alerts; only an accept/edit
    moves it into the EDB `challenge` section. Rejecting it keeps it out.
- A new `Proposal` kind (or a reuse of the field/claim proposal with a `statement`
  marker) carries the statement text + its flags/issues for the card UI.

Affected: `session.py` `_run_challenge`, `core/runtime/ledger.py` (proposal kind),
`web/app.py` `_card_dict` (surface flags/issues on the card), static UI.

## Added LLM cost per turn

- `+1` sufficiency call per turn (batched over filled sections).
- `+1` grounding call **only on the challenge turn** (batched over valid claims).

Both bounded and memoized by `CachingProvider` in the benches.

## Testing

All hermetic via `MockProvider`; `provider=None` degradation asserted at each step
(sufficiency off → binary; grounding off → syntactic gate; statement quarantine still
fires on the deterministic `statement_flags`).

A `conversation-eval` scenario added asserting, end to end:
1. a node excluded during the challenge does **not** reappear on the map after a later
   precision;
2. a vague section is re-asked with a targeted precision question, a precise one is not;
3. a claim whose conclusions exceed its cited provenance is rejected, not carded;
4. a statement with a fidelity issue is **not** auto-stored — it waits in the ledger;
5. the initial brief's milestone is captured without re-asking.

## Out of scope (YAGNI)

- Re-challenge (full re-triage) on precision — option C in the brainstorm; the live
  map + accumulated exclusions cover the reliability need without a second LLM triage.
- Sub-field slot decomposition of EDB sections (option C for the EDB) — the sufficiency
  rubric gets the precision behavior without a schema refactor.
- Any unrelated refactoring of the retrieval or challenge layers.

## Sequencing

1. #1 live-coherent map (highest reliability priority before any demo).
2. #5 extraction + #2 EDB sufficiency (the richer-dossier core).
3. #3 grounding, #4 quarantine (reliability patches, same files).
