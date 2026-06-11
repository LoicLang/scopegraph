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

**Resolution.**
- The W4 eval gains a third arm: (a) naive prompt, no graph · (a') **full-graph-in-context**
  LLM · (b) scopegraph. At 72 nodes (a') is expected to be competitive — the honest claims
  against it are determinism, grounding/citations, write-back, and the scale trajectory.
- Real-scale validation is deferred to ecosystem-foundry volume (or a disposable synthetic
  stress graph of 300–500 nodes, generated, never hand-curated, kept out of the demo).
  Hand-growing the demo seed is explicitly rejected: fictional-entities rule makes large
  hand-curation a project of its own, and volume production is foundry's job.

## L5 — Methodology traps in our own bench

- **Aggregate recall hides critical-case death**: an 84 % average looked fine while the
  TPE chain (the demo case) was at 56 %. The bench now prints per-case missing nodes;
  judge per-case, not on means.
- Ground truth is hand-derived and partially subjective (which nodes are "critical" per
  scenario); treat absolute numbers as indicative, deltas as meaningful.
- The hermetic suite's FakeEmbedder produces exact ties real embeddings never produce
  (origin of the type-priority tie-break, W2 spec §3) — quality conclusions only ever
  come from the real-model bench, never from the hermetic tests.

## L6 — Map readability (UI debt, W3 polish list)

44-node maps are unreadable (Loïc, first session). Anchor/expanded contrast too subtle ·
`cose` layout instead of the viewer's fcose template · orphan expanded nodes possible
after a domain exclusion (path through a dropped node) · click detail shows raw node ids ·
template questions expose domain slugs (« paiement-instantane ») instead of French labels.
Most of this dissolves when W3's challenge layer shrinks the displayed set to justified
nodes; the rest is cosmetic fixes alongside W3.
