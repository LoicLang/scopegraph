"""Retrieval & MAPPING knobs (W2 design spec §3).

Calibrated with scripts/retrieval-smoke against the eval cases — never by intuition.
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
