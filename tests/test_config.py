"""RetrievalProfile: frozen MiniLM values (known-limits reproducibility) + TOP_N policy."""

from core.retrieval.config import DEFAULT_PROFILE, E5_BASE, MINILM, PROFILES


def test_minilm_profile_is_frozen_to_w2_values():
    # Regression lock: these are the 2026-06-11 calibrated constants (known-limits L1).
    assert MINILM.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
    assert (MINILM.tau_anchor, MINILM.tau_keep) == (0.35, 0.20)
    assert (MINILM.tau_weak, MINILM.tau_noise) == (0.45, 0.25)
    assert (MINILM.alpha, MINILM.delta) == (0.15, 0.15)
    assert (MINILM.domain_fraction, MINILM.decay) == (0.5, 0.7)
    assert MINILM.query_prefix == "" and MINILM.passage_prefix == ""
    assert MINILM.top_n_policy == "fixed"


def test_e5_profile_carries_asymmetric_prefixes():
    assert E5_BASE.model_name == "intfloat/multilingual-e5-base"
    assert E5_BASE.query_prefix == "query: "
    assert E5_BASE.passage_prefix == "passage: "


def test_top_n_fixed_ignores_graph_size():
    assert MINILM.top_n(72) == 20
    assert MINILM.top_n(2072) == 20


def test_top_n_coverage_scales_with_floor():
    from dataclasses import replace

    scaled = replace(MINILM, top_n_policy="coverage")
    assert scaled.top_n(72) == 21  # ceil(0.28 * 72)
    assert scaled.top_n(2072) == 581  # ceil(0.28 * 2072)
    assert scaled.top_n(100) == 28  # exact product must not overshoot via float noise
    assert scaled.top_n(10) == 20  # floor wins on small graphs


def test_registry_and_default():
    assert PROFILES == {"minilm": MINILM, "e5": E5_BASE}
    assert DEFAULT_PROFILE is MINILM  # flipped only by the exit contract (spec §1)


def test_top_n_unknown_policy_fails_loud():
    import pytest
    from dataclasses import replace

    broken = replace(MINILM, top_n_policy="scale")
    with pytest.raises(ValueError, match="unknown top_n_policy"):
        broken.top_n(72)
