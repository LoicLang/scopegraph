"""Retrieval & MAPPING knobs (W2 design spec §3).

Calibrated with scripts/retrieval-eval against the eval cases — never by intuition.

Calibration findings (2026-06-11, docs/known-limits.md L1): real MiniLM anchor sims sit in
0.30-0.56 and a 2-hop expansion lands near anchor·DECAY² ≈ 0.216 — raising TAU_KEEP above
~0.21 kills the eval-case-1 TPE chain. The sweep found NO threshold setting that buys
precision without losing documented traps. Retrieval is recall-first by design; precision
is the W3 challenge layer's job. Re-run ./scripts/retrieval-eval per-case before touching
any value here.
"""

EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

TOP_N = 20  # semantic candidates pulled from the vector index
TOP_K = 8  # max anchors
ALPHA = 0.15  # score boost per shared domain between brief and node
TAU_ANCHOR = 0.35  # min boosted score to count as an anchor
TAU_KEEP = 0.20  # min score for an expanded node to be kept
TAU_WEAK = 0.45  # best anchor below this → T1 (vague brief)
TAU_NOISE = 0.25  # semantic sim below this → node counts as expansion-only (T3)
DELTA = 0.15  # relative margin: top-2 domain scores closer than this → T2
DOMAIN_FRACTION = 0.5  # derived domains = candidate score ≥ fraction · top score
MAX_HOPS = 2  # expansion radius from anchors
DECAY = 0.7  # expanded score = anchor score · DECAY^hops
MAX_QUESTIONS = 5  # hard cap of questions per session
