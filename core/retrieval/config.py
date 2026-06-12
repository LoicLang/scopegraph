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
    top_n_fraction: float = 0.28  # W2 coverage parity: 20/72 candidates (spec §1)
    top_n_floor: int = 20

    def top_n(self, graph_size: int) -> int:
        """Semantic candidates pulled from the vector index for this graph size."""
        if self.top_n_policy == "fixed":
            return self.top_n_fixed
        return max(self.top_n_floor, math.ceil(self.top_n_fraction * graph_size))


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

# PROVISIONAL thresholds — band-transposition guesses pending §4.ii calibration
# (spec 2026-06-12): replace every value below from retrieval-smoke output, then
# delete this comment. decay is the known trouble spot: on a ~0.7-floor band a
# multiplicative 0.7² collapses 2-hop scores below noise; 0.9 is a stopgap and the
# calibration may impose a different form.
E5_BASE = RetrievalProfile(
    name="e5-base",
    model_name="intfloat/multilingual-e5-base",
    tau_anchor=0.82,
    tau_keep=0.76,
    tau_weak=0.86,
    tau_noise=0.78,
    alpha=0.06,
    delta=0.15,
    domain_fraction=0.5,
    decay=0.9,
    query_prefix="query: ",
    passage_prefix="passage: ",
)

PROFILES: dict[str, RetrievalProfile] = {"minilm": MINILM, "e5": E5_BASE}
DEFAULT_PROFILE = MINILM  # flipped to E5_BASE only by the exit contract (spec §1)

# Structural knobs — band-independent, shared by every profile.
TOP_K = 8  # max anchors
MAX_HOPS = 2  # expansion radius from anchors
MAX_QUESTIONS = 5  # hard cap of questions per session
