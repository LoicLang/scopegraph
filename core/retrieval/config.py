"""Retrieval & MAPPING knobs, profiled per embedder (W2 spec §3 · W3 lot 0bis spec §3).

Band-dependent values live in a RetrievalProfile: similarity bands differ per embedder
(MiniLM anchors ≈ 0.30-0.56, e5 ≈ 0.7-0.95), so a threshold is only meaningful relative
to a model. Profiles are calibrated by reading scripts/retrieval-smoke and
scripts/retrieval-eval output — never by intuition.

MiniLM findings (2026-06-11, docs/known-limits.md L1): a 2-hop expansion lands near
anchor·decay² ≈ 0.216 — raising tau_keep above ~0.21 kills the eval-case-1 TPE chain.
Retrieval is recall-first by design; precision is the W3 challenge layer's job. The
MiniLM profile is FROZEN for known-limits reproducibility (regression-tested) — never
retune it.
"""

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    model_name: str
    tau_anchor: float  # min boosted score to count as an anchor
    tau_keep: float  # min score for an expanded node to be kept
    tau_weak: float  # best anchor below this → T1 (vague brief)
    tau_noise: float  # semantic sim below this → node counts as expansion-only (T3)
    alpha: float  # score boost per shared domain between brief and node
    delta: float  # relative margin: top-2 domain scores closer than this → T2
    domain_fraction: float  # derived domains = candidate score ≥ fraction · top score
    decay: float  # expanded score = anchor score · decay^hops
    query_prefix: str = ""  # e5-style asymmetric prefixes; empty = symmetric model
    passage_prefix: str = ""
    top_n_policy: Literal["fixed", "coverage"] = "fixed"
    top_n_fixed: int = 20
    top_n_fraction: float = 0.28  # W2 coverage parity ≈ 20/72 candidates (spec §1)
    top_n_floor: int = 20

    def top_n(self, graph_size: int) -> int:
        """Semantic candidates pulled from the vector index for this graph size."""
        if self.top_n_policy == "fixed":
            return self.top_n_fixed
        if self.top_n_policy == "coverage":
            return max(self.top_n_floor, math.ceil(round(self.top_n_fraction * graph_size, 9)))
        raise ValueError(f"unknown top_n_policy: {self.top_n_policy!r}")


MINILM = RetrievalProfile(
    name="minilm",
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
    tau_anchor=0.35,
    tau_keep=0.20,
    tau_weak=0.45,
    tau_noise=0.25,
    alpha=0.15,
    delta=0.15,
    domain_fraction=0.5,
    decay=0.7,
)

# Calibrated 2026-06-12 from retrieval-smoke --embedder e5 (spec §4.ii, band
# transposition from the W2 MiniLM percentiles). The e5 band is ~7x narrower than
# MiniLM's (top-median spread 0.026-0.069 vs 0.18-0.45; whole graph in 0.73-0.86):
# - tau_anchor 0.78 sits under every healthy case's rank-8 sim (0.787-0.819) and
#   above the vague case's q3 (cas-6: 0.771) — same recall-first shape as 0.35/W2.
# - decay stays MULTIPLICATIVE on purpose: the band is nearly constant, so
#   multiplicative ≈ subtractive; 0.98 gives ~0.016/hop, the W2-equivalent fraction
#   (~68% of the top-median spread over 2 hops). No form change needed.
# - tau_weak 0.797 splits the vague brief (cas-6 top 0.794) from the healthy tops
#   (0.800-0.858). KNOWN-FRAGILE: 0.006 of margin — T1 discriminability is
#   intrinsically weak in a compressed band; recorded for known-limits.
# - alpha 0.02 ≈ the same fraction of the usable spread as MiniLM's 0.15.
#
# N=0 GATE VERDICT (2026-06-12, spec §4.iii): FAILED — S1 loses
# dec-releases-tpe-trimestrielles (sys-logiciel-tpe misses the 8th anchor slot by
# 0.001 sim), S3 loses the governance freeze (dec-gel-evolutions-monetique ranks
# 72/72 — e5 does not connect cash-back briefs to the monetique cluster at all),
# S5 loses con-ai-act (rank 17, crowded out of TOP_K). The §4.ii single iteration
# (tau_keep 0.75→0.74, decay 0.98→0.985) changed NOTHING: the misses are anchor-
# RANKING failures, not threshold failures. This profile is kept for reproducibility;
# do NOT flip DEFAULT_PROFILE to it. Next step is a recorded decision (BUILD-ORDER).
E5_BASE = RetrievalProfile(
    name="e5",
    model_name="intfloat/multilingual-e5-base",
    tau_anchor=0.78,
    tau_keep=0.74,
    tau_weak=0.797,
    tau_noise=0.77,
    alpha=0.02,
    delta=0.15,
    domain_fraction=0.5,
    decay=0.985,
    query_prefix="query: ",
    passage_prefix="passage: ",
)

PROFILES: dict[str, RetrievalProfile] = {p.name: p for p in (MINILM, E5_BASE)}
DEFAULT_PROFILE = MINILM  # flipped to E5_BASE only by the exit contract (spec §1)

# Structural knobs — band-independent, shared by every profile.
TOP_K = 8  # max anchors
MAX_HOPS = 2  # expansion radius from anchors
MAX_QUESTIONS = 5  # hard cap of questions per session
