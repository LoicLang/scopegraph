---
summary: validated W3-lot-0bis design — MiniLM→e5 swap + scaled TOP_N behind per-embedder profiles, judged by a 2×2 distractor-sweep grid with a per-trap autopsy
read_when:
  - implementing the embedder swap, RetrievalProfile, or the bench grid flags
  - calibrating the e5 profile (TAU_*, DECAY) from retrieval-smoke output
  - interpreting the 2×2 grid verdict or deciding the BM25 escalation
---

# Embedder swap + TOP_N scaling (W3 lot 0bis) — Design Spec

Date: 2026-06-12
Status: validated in brainstorming session (this doc is the build contract for W3 lot 0bis)
Upstream: known-limits **L4** (distractor bench verdict: SWAP EMBEDDER) · distractor bench
spec `2026-06-11-distractor-stress-bench-design.md` (the sweep harness this reuses) · W2
spec (recorded escalation: multilingual-e5; recorded no-go: reranker unless forced) ·
BUILD-ORDER W3 lot 0.

The distractor bench measured MiniLM losing 6/11 trap cases at N=2000 (recall 89 % → 54 %,
anchor intrusion 6.6/8). Mechanism confirmed: plausible same-domain distractors crowd the
TOP_N=20 candidate list and steal anchor slots; expansion then starts from the wrong nodes.
Two levers attack that mechanism directly — a retrieval-trained embedder and a candidate
list that scales with graph size. This chantier is **one measurement**: both levers, a 2×2
grid, the same pre-committed per-case criterion. W3 lots 1–4 stay blocked until the grid
is read.

---

## 1. Decisions taken (closing this brainstorm)

| Topic | Decision | Rationale |
|---|---|---|
| Target model | **`intfloat/multilingual-e5-base`** (~278M params, dim 768). | Best quality/cost ratio for a repeated local bench. Escalate to e5-large only if traps still die (cheap: it is one profile entry away). Decided over: e5-small (a barely-passing verdict would not tell variant ceiling from family ceiling), e5-large (slower bench, only if forced), base+large grid (+50 % bench time for a question we may never need answered). |
| Constants under two embedders | **Per-embedder `RetrievalProfile`** (frozen dataclass in `config.py`). MiniLM keeps its current values verbatim; e5 gets its own, read from `retrieval-smoke` BEFORE the polluted sweep. | The 2×2 grid must compare each embedder at its own honest operating point — e5 similarities live in a different band (~0.7–0.95 vs MiniLM 0.30–0.56), so shared constants would make one arm absurd. Decided over: overwrite-in-place (kills the MiniLM arm), score normalization (a magic layer over the scorer, against clarity-over-cleverness). |
| TOP_N scaling rule (the "scaled" arm) | **Coverage parity: `TOP_N = max(20, ceil(0.28 · |V|))`** → 581 at 2072 nodes. | Reproduces exactly the candidate-coverage ratio W2 was calibrated at, so the arm cleanly isolates "did relative coverage matter?". Recall-side capacity, not precision tuning (TOP_K=8 still caps anchors; L1 doctrine intact). The long-term production rule (sqrt, cap…) is chosen AFTER reading both arms, not here. Decided over: sqrt rule (~110 candidates risks under-dosing the lever against 6.6/8 intrusion), fixed 100 (arbitrary, says nothing about the scale trajectory). |
| BM25 / reranker escalation | **Out of scope — separate decision after the grid is read.** The bench prints a per-trap autopsy (§5) so that decision takes minutes, not a re-investigation. | The hybrid fix's design depends on WHICH thief class survives e5: homonyms (class c) → lexical+dense rank fusion on the query; governance-chain death via near-twins (class b) → BM25 is useless (twins share vocabulary), the lever is elsewhere. Same pattern that just worked for lot 0: pre-committed criterion, measure, then decide with data. Reranker stays the W2 recorded no-go unless forced. |
| Multi-turn polluted sweep | **Out of scope — noted in BUILD-ORDER as a conditional follow-up.** | It measures a different quantity (the MAPPING loop's recovery net — a product argument, not the embedder GO/NO-GO) and needs a harness that does not exist (simulated user answers: canned-per-scenario or LLM — the latter is circular before W3 lot 1). Not on W3's critical path either way the verdict goes. |
| Exit contract | Best cell passes → flip `EMBED_MODEL` default to e5-base + scaled TOP_N becomes the default policy, update L4 + BUILD-ORDER, unblock lots 1–4. Any trap death in the best cell → stop, run the thief relevance annotation (§5), THEN the separate escalation brainstorm with both the autopsy and the annotation in hand. | One chantier = one measurement, one verdict, one docs commit. The annotation distinguishes embedder weakness from anchor saturation — two failures with opposite fixes (§5). |

## 2. Embedder — asymmetric Protocol

e5 models are trained with asymmetric prefixes: `query: ` on the search text, `passage: `
on the indexed documents. The asymmetry lands exactly on the two existing embed call
sites, so it belongs in the Protocol:

- `Embedder` Protocol replaces `embed(texts)` with **`embed_queries(texts)`** and
  **`embed_passages(texts)`**.
- `SentenceTransformersEmbedder` takes its prefixes from the active profile (MiniLM:
  both empty, e5: `query: ` / `passage: `). Prefix application is a pure function
  (testable without a model download). No model-specific detail leaks outside
  `core/retrieval` (AGENTS.md Protocol rule).
- `FakeEmbedder` implements both methods identically — hermetic tests keep their
  semantics.
- `VectorIndex.build()` → `embed_passages`; `VectorIndex.query()` → `embed_queries`.
- Index staleness: `embedder_id()` already folds `model_name` into the fingerprint —
  a model swap rebuilds the persistent index with no further work.

## 3. Constants — `RetrievalProfile`

`core/retrieval/config.py` gains a frozen dataclass holding everything that depends on
the similarity band, plus the model identity:

- `model_name`, `query_prefix`, `passage_prefix`
- `TAU_ANCHOR`, `TAU_KEEP`, `TAU_WEAK`, `TAU_NOISE`, `ALPHA`, `DELTA`,
  `DOMAIN_FRACTION`, `DECAY`
- TOP_N policy: `top_n_policy: "fixed" | "coverage"`, `top_n_fixed = 20`,
  `top_n_fraction = 0.28`, `top_n_floor = 20`; effective value
  `max(top_n_floor, ceil(top_n_fraction · |V|))` under `coverage`.

Two named profiles: **`minilm`** (current values verbatim — frozen for known-limits
reproducibility) and **`e5-base`** (TAU/DECAY values are calibration outputs, set in
step §4.ii — the profile ships with the smoke-derived values, never invented ones).
`DEFAULT_PROFILE` is module-level; the exit contract (§1) is what flips it.

Structural knobs stay module constants: `TOP_K`, `MAX_HOPS`, `MAX_QUESTIONS`.

`retrieve(..., profile=DEFAULT_PROFILE)` reads every band-dependent knob from the
profile. `ScoredNode.expansion_only` gets its threshold injected at construction time
(the property stops reading module globals).

Calibration warning recorded now: e5's band has a high floor (~0.7), so multiplicative
DECAY collapses 2-hop scores below the noise floor (0.85 · 0.7² ≈ 0.42 < floor). The e5
profile may need a gentler DECAY or a subtractive decay form — decided by reading the
smoke output, documented in the profile, never by intuition.

## 4. Calibration procedure (strict order, L1 doctrine)

i. Implementation + hermetic tests green (no real model involved).
ii. `retrieval-smoke` with e5 at N=0 → read the real similarity distribution (anchor
    band vs noise band) → set e5 TAU_* by **band transposition** — same recall-first
    operating logic as W2, NOT precision tuning. Resolve the DECAY form here (§3).
iii. Run the 11 scenarios at N=0 with e5: every documented trap node that MiniLM finds
    at N=0 must still be found, and mean recall must not drop more than 5 pts vs
    MiniLM's 89 %. A failure here stops the chantier (the swap is wrong, not the
    noise).
iv. Only then, the 2×2 grid (§5).

## 5. Bench — grid flags + per-trap autopsy

`retrieval-eval` gains, composable with the existing `--distractors N` /
`--distractor-sweep`:

- `--embedder {minilm,e5}` — selects the profile (default: `DEFAULT_PROFILE`).
- `--top-n {fixed,scaled}` — selects the TOP_N policy (default: the profile's).
- `--grid` — runs the four cells (MiniLM/e5 × fixed/scaled) as full sweeps and prints
  a final comparison table (per cell: recall curve, anchor intrusion, map pollution,
  realism check, dead traps per case).

**Anchor autopsy** (new sweep output, the data the BM25 decision needs): for every
scenario that loses expected nodes at N=2000 vs N=0 in a cell, print the dead expected
nodes AND the thief lineup — each intruding anchor with id, title, domains, semantic
sim, plus a mechanical flag: `same-domain` (shares ≥1 domain with a dead node — near-twin
material, classes a/b) vs `cross-domain` (homonym material, class c). The a-vs-b call
(legitimate substitution vs genuine trap death) stays human — the lineup is what makes
that reading a 10-minute job instead of a re-run with instrumentation.

**Thief relevance annotation (mandatory on a failing verdict, before any escalation
decision).** Hand-annotate the thieves of the failing cases on the sweep logs (L5
option a, ~1 h): is each intruding anchor *genuinely relevant* to the brief in the
merged universe? Two opposite diagnoses follow:

- Thieves mostly irrelevant → embedder/lexical weakness is confirmed; the escalation
  brainstorm (BM25-class levers) proceeds as planned, and the annotation says which
  thief class dominates.
- Thieves mostly relevant → **anchor saturation**: the merged graph legitimately
  contains more relevant nodes than TOP_K=8 anchor slots can hold, and no embedder
  fixes that. The follow-up brainstorm is then about anchor capacity and selection
  (TOP_K rethink, near-twin dedup/clustering, letting the challenge layer arbitrate a
  larger anchor set) — NOT about lexical signals. Record the corrected recall in L5
  (closing its "no action decided" note).

Realism sanity check unchanged and still gating: an invalid check voids the cell's
verdict. The bench stays out of CI (real model), like today.

## 6. Verdict criterion (pre-committed, read per cell)

Unchanged from the distractor spec §1, applied within each cell: at N=2000, every
scenario keeps all expected nodes it found at N=0 **in that same cell**, AND mean recall
drops ≤ 10 pts from that cell's N=0. Any documented trap death fails the cell. The L5
distractor-recall bias (legitimate substitutions counted as misses) is neutral here:
the per-case criterion only looks at trap nodes.

## 7. Tests (hermetic, FakeEmbedder / no model download)

- Protocol: both methods on `FakeEmbedder` and `SentenceTransformersEmbedder`
  (the latter's prefix application tested via the pure function, not the model).
- e5 prefixing: `query: ` / `passage: ` applied; MiniLM profile applies none.
- TOP_N scaling formula: 72 → 20, 2072 → 581, floor respected.
- Profile selection + MiniLM value non-regression (current constants frozen by test).
- `expansion_only` with injected threshold.
- Existing 127 tests migrate mechanically to the new Protocol signature.

## 8. Docs & aftermath

- After the grid: update `docs/known-limits.md` L4 (2×2 table + verdict + autopsy
  summary), `docs/BUILD-ORDER.md` (lot 0bis done → lots 1–4 unblocked, or BM25
  brainstorm next), re-evaluate L5 (if traps survive e5, the biased mean stops
  mattering for any decision).
- No ADR: no schema change.

## Out of scope (explicit)

- BM25 / rank fusion / reranker — separate decision after the grid, fed by the autopsy.
- Multi-turn polluted sweep — conditional follow-up, noted in BUILD-ORDER.
- Any retuning of the MiniLM profile (frozen for reproducibility).
- Production TOP_N rule beyond the bench (chosen after reading both arms).
- UI work.
