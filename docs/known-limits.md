---
summary: measured limits of the W2 retrieval + MAPPING loop, with evidence and planned resolution
read_when:
  - designing W3 (the challenge layer is the answer to most of these)
  - interpreting retrieval-eval / retrieval-smoke numbers
  - tempted to "fix" retrieval precision by tuning thresholds
---

# Known limits (measured 2026-06-11, end of W2)

Source of every number: `./scripts/retrieval-eval` (11 fictional scoping scenarios, real
MiniLM, ground truth hand-derived from the seed's DEPENDS_ON/CONSTRAINS/SUPERSEDES edges).
Re-run the bench after any change and update this file.

## L1 — Retrieval precision is structurally low, and thresholds cannot buy it back

**Evidence.** At W2 constants: mean recall 89 %, mean map 44.5/72 nodes, mean precision
**13 %**. The threshold sweep shows no good operating point:

| grid | recall | map | precision | what dies |
|---|---|---|---|---|
| baseline W2 (0.35/0.20/K8) | 89 % | 44.5 | 13 % | — |
| tight+ (0.40/0.28/K6) | 72 % | 23.5 | 19 % | **the TPE 2-hop chain (eval case 1)** |
| tight++ (0.45/0.32/K5) | 70 % | 18.7 | 23 % | idem + cash-back freeze chain |
| aggressive (0.48/0.38/K4) | 52 % | 8.3 | 40 % | half the documented traps |

**Root cause.** MiniLM similarities live in a narrow band (anchors ≈ 0.30–0.56, noise
≈ 0.25–0.40): relevant and irrelevant scores overlap. A 2-hop expanded node lands at
anchor·DECAY² ≈ 0.44·0.49 ≈ **0.216** — barely above TAU_KEEP=0.20. Any tightening that
removes noise also removes the product's founding trap.

**Resolution.** Precision is **by design the job of the W3 CHALLENGING layer** (the LLM
reads the over-complete subgraph and keeps only what it can justify, under the grounding
gate). Retrieval stays a recall-first net; constants stay as they are. Secondary lever if
W3 proves insufficient: a stronger embedder (multilingual-e5, bge-m3 — see the no-reranker
decision in the W2 spec). Do NOT tune thresholds for precision.

## L2 — Vocabulary bridge: user words vs graph words

**Evidence.** S6 « Refondre le parcours d'entrée en relation 100 % digital » → **0/7
critical nodes** single-turn: MiniLM does not connect "entrée en relation" to
"création de client / dossier KYC". After one generic T1 answer naming those words, recall
recovers to 5/7 — the loop's safety net works, but it costs a turn and depends on the
user volunteering the right vocabulary.

**Resolution.** W3: LLM brief enrichment *before* retrieval (proposes synonyms/business
objects as gated, visible brief additions — never a hidden query rewrite). Cheap data-side
mitigation: enrich seed descriptions/aliases with common business synonyms.

## L3 — Pivot questions are mechanically chosen, often beside the point

**Evidence.** The pivot picks the first unknown-domain expansion-only node by score. S9
(self-service card limits, real blocker = `dec-gel-evolutions-monetique`) asked about
DSP2/SCA instead; S1/S4/S7 asked about incidental neighboring domains.

**Resolution.** The runtime keeps deciding *whether/what topic space* to ask (hard rule 1);
W3's LLM judges *which* candidate matters and phrases it with stakes. Deterministic
fallback idea worth testing: pick the unknown domain with the largest expansion mass
instead of the single highest-scored node.

## L4 — At 72 nodes, retrieval is not yet empirically necessary (scale validity)

**Statement of the limit (raised by Loïc, correct).** The whole graph fits in one LLM
context window. A baseline that dumps all 72 nodes into the prompt and lets the model
judge would likely match the retrieval pipeline today — so W2's eval numbers do not prove
the retrieval architecture, only its mechanics. Retrieval+expansion is an **architecture
bet on scale** (real ecosystems: thousands of nodes), not an empirically forced choice at
seed size.

**What is actually size-biased vs not** (refined 2026-06-11 evening): the expansion
mechanics, the L2/L3 findings, and the vs-naive-prompt comparison hold at any size. The
genuinely unknown quantity is **anchor ranking under distractor pressure** — at 72 nodes
the right anchors reach TOP_N almost by default; with thousands of plausible distractors
and MiniLM's narrow similarity band, nobody knows.

**Resolution.**
- The W4 eval gains a third arm: (a) naive prompt, no graph · (a') **full-graph-in-context**
  LLM · (b) scopegraph. At 72 nodes (a') is expected to be competitive — the honest claims
  against it are determinism, grounding/citations, write-back, and the scale trajectory.
- **W3 lot 0 — distractor stress bench** (decided 2026-06-11, see BUILD-ORDER): keep the
  seed as the untouched truth island, generate 500–2000 plausible distractor nodes
  (`created_from: synthetic`, never in the demo), re-run the 11 scenarios. This measures
  the size-biased quantity directly, without circular ground truth (a fully synthetic
  graph — generated nodes AND edges AND truth — would be a worse test than the small
  honest one: the generator decides where the buried dependencies are, then we verify we
  find them). Recall collapse → swap embedder (multilingual-e5) before W3 builds on it.
- *Realistic*-volume validation (messy real structure, not plausible noise) still comes
  from ecosystem-foundry output, after W4. Hand-growing the demo seed stays rejected:
  fictional-entities rule makes large hand-curation a project of its own, and volume
  production is foundry's job.

**MEASURED (2026-06-12, W3 lot 0 — `./scripts/retrieval-eval --distractor-sweep`,
spec `2026-06-11-distractor-stress-bench-design.md`).** Verdict: **SWAP EMBEDDER**.

| N distractors | recall | map | precision | anchor intrusion | map pollution |
|---|---|---|---|---|---|
| 0 | 89 % | 44.5 | 13 % | — | — |
| 500 | 72 % | 62.2 | 8 % | 5.5/8 | 65 % |
| 1000 | 60 % | 71.6 | 5 % | 6.2/8 | 75 % |
| 2000 | **54 %** | 69.5 | 5 % | **6.6/8** | 81 % |

- Realism check passes at every N (distractor sims med 0.27–0.30 vs seed-noise med
  0.31, same band, no "too easy" warning): the pressure is honest, the verdict valid.
- Per-case criterion fires hard: 6/11 scenarios lose documented trap nodes at N=2000
  (S3 cash-back loses the monetique freeze AND `con-pci-dss`; S8 loses the whole IP
  chain incl. `sys-passerelle-ip`). At N=100 already (smoke), S3 was 0/6 with 7/8
  distractor anchors.
- Mechanism confirmed: with TOP_N=20 / TOP_K=8, plausible same-domain distractors
  crowd the candidate list and steal anchor slots; expansion then starts from the
  wrong nodes, so the buried chains are never reached. The L1 "narrow similarity
  band" is the root cause at scale, exactly as hypothesized.
- Note: the pool deliberately contains near-twins of seed components (e.g. a second
  fictional authorization engine) — that is what a real ecosystem at scale looks
  like, and the test is honest because ground-truth nodes remain uniquely identified.
- **Interpretation refinement (2026-06-12, raised by Loïc, anchor inspection at
  N=2000).** The stolen anchors are NOT all junk — three distinct phenomena:
  (a) *legitimate substitution*: S3's thieves are a fictional cashback engine + its
  refonte project + its 500 € cap — in the merged universe, surfacing them would be
  correct scoping. Seed-only ground truth counts them as noise, so **mean recall
  understates real performance**; treat the 89→54 % drop as a lower bound.
  (b) *genuine trap death*: the governance chains (`dec-gel-evolutions-monetique`,
  `con-pci-dss`, carence 48h, double validation) have no functional substitutes and
  simply vanish — the product's core promise fails at scale. This is the real signal,
  and the per-case verdict criterion (already chosen for L5 reasons) captures exactly
  it, so the SWAP verdict stands unchanged.
  (c) *homonym noise*: S2 loses support anchors to "Référentiel des Bénéficiaires
  Effectifs" (LCB-FT concept) on a payee-beneficiary brief — same words, different
  business object; dense text similarity cannot disambiguate. Lexical/hybrid signals
  are the targeted fix for this class.
- **Action (spec's recorded escalation): swap the embedder to multilingual-e5 and
  re-run this sweep BEFORE building W3 lots 1–4.** Constants stay untouched until the
  new embedder's sweep is read (L1 doctrine still applies). Candidate levers beyond
  the swap, in test order: scale TOP_N with graph size (20 candidates = 28 % of a
  72-node graph but 1 % of 2072 — recall-side capacity, not precision tuning), hybrid
  BM25 + dense for the homonym class, reranker last (W2 spec's recorded no-go unless
  forced).

**MEASURED (2026-06-12, W3 lot 0bis — spec `2026-06-12-embedder-swap-design.md`,
grid log `/tmp` session artifact, summary in BUILD-ORDER).** Outcome: **e5-base
REJECTED at the N=0 gate · Qwen3-Embedding-0.6B adopted (DEFAULT_PROFILE).**

- **e5-base never reached the grid**: its similarity band is ~7x narrower than
  MiniLM's (whole graph in 0.73–0.86, top–median spread 0.026–0.069), and its
  *ranking* fails outright — on the cash-back brief, `dec-gel-evolutions-monetique`
  ranks 72/72 (dead last). Anchor-ranking failures, not thresholds: the single
  allowed calibration iteration changed nothing. Profile kept in config for
  reproducibility.
- **Qwen3-0.6B (instruction-aware query side) passes the N=0 gate as a strict
  per-case superset of MiniLM**: mean 95 % vs 89 %, S3 6/6 (MiniLM 5/6), S6
  vocabulary bridge 3/7 (MiniLM 0/7), smaller maps (39.7 vs 44.5), precision 17 %
  vs 13 %. The task instruction measurably fixes e5's failure mode (S5:
  `con-ai-act` rank 1 vs 17).
- **2×2 grid (minilm/qwen3 × TOP_N fixed/scaled), per-cell criterion**: every cell
  fails the strict criterion, but the curves differ in kind — MiniLM 89→54 % still
  falling at N=2000; **qwen3 95→75→69→68 %, converging** (1 pt between N=1000 and
  N=2000). Realism check valid everywhere.
- **TOP_N scaling is a proven single-turn no-op** (fixed and scaled cells are
  byte-identical per case, both embedders): with no confirmed domains there is no
  boost, so anchors = top-8 of the raw ranking regardless of candidate-list size.
  The lever only matters multi-turn, where ALPHA can promote same-domain
  candidates — measure it there (multi-turn polluted sweep, recorded follow-up).
- **Thief annotation (spec §5, mandatory on failure — read 2026-06-12)**: qwen3's
  residual deaths are NOT embedder weakness. (a) *Legitimate substitution
  dominates*: S6's thieves include `proj-dref-onboarding-digital-v2` — literally
  the same project as the brief; S3's are the fictional cashback engine + its
  500 € cap; S1's the "paiement fractionné en caisse" project (a real scope
  collision); S7's the Fraudar near-twin. In the merged universe these are
  correct scoping answers — real recall sits well above 68 %. (b) *Genuine
  deaths concentrate on deep seed governance chains* (PCI-DSS + monetique freeze
  on S3, RGPD/traçabilité on S5, credit/KYC chain on S1): **anchor saturation**
  — 8 anchor slots cannot hold both a legitimate twin cluster and the seed
  cluster — plus 2-hop depth. Targets: the W3 challenge layer (justification
  pressure), the multi-turn recovery net, and a possible anchor-capacity (TOP_K)
  chantier. (c) *The homonym class is closed*: S2 holds 8/8 at N=2000 under
  qwen3 — the BM25-hybrid escalation loses its motivating case.

## L5 — Methodology traps in our own bench

- **Aggregate recall hides critical-case death**: an 84 % average looked fine while the
  TPE chain (the demo case) was at 56 %. The bench now prints per-case missing nodes;
  judge per-case, not on means.
- Ground truth is hand-derived and partially subjective (which nodes are "critical" per
  scenario); treat absolute numbers as indicative, deltas as meaningful.
- The hermetic suite's FakeEmbedder produces exact ties real embeddings never produce
  (origin of the type-priority tie-break, W2 spec §3) — quality conclusions only ever
  come from the real-model bench, never from the hermetic tests.
- **Distractor-recall design bias (noted 2026-06-12, raised by Loïc — status:
  CONFIRMED by the lot-0bis annotation, 2026-06-12 evening).** Generating plausible
  same-domain distractors statistically guarantees that some are *genuinely
  relevant* to the eval briefs (extreme case: the monetique shard invented a
  fictional cashback ecosystem while an eval case is cash-back — its nodes are
  correct scoping answers, counted as misses). So the polluted-sweep recall is
  systematically biased LOW; only the per-case trap-death criterion is immune.
  The qwen3 autopsy annotation (L4) made the bias concrete: substitution dominates
  the residual misses (an onboarding brief losing nodes to a fictional *onboarding
  project* is the bench punishing a correct answer). Read polluted-sweep recalls
  as lower bounds, decisions only ever from the per-case criterion + annotation.
- **A 2×2 grid arm can be a no-op by construction**: the TOP_N-scaled arm produced
  byte-identical results because the single-turn bench has no confirmed domains,
  hence no boost, hence anchors = top-8 of the raw ranking at any list size. Check
  a lever's activation conditions against the harness BEFORE burning a grid row
  on it (the lever is real, but only the multi-turn bench can see it).

## L6 — Map readability (UI debt, W3 polish list)

44-node maps are unreadable (Loïc, first session). Anchor/expanded contrast too subtle ·
`cose` layout instead of the viewer's fcose template · orphan expanded nodes possible
after a domain exclusion (path through a dropped node) · click detail shows raw node ids ·
template questions expose domain slugs (« paiement-instantane ») instead of French labels.
Most of this dissolves when W3's challenge layer shrinks the displayed set to justified
nodes; the rest is cosmetic fixes alongside W3.
