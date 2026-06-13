"""The three per-turn LLM steps, each with a deterministic no-provider fallback."""

from core.dossier.template import EdbState
from core.llm.provider import MockProvider
from core.runtime.brief import ProjectBrief
from core.runtime.llm_steps import (
    MAX_TOTAL_ENRICHMENTS,
    enrich_brief,
    extract_fields,
    interpret_pivot_answer,
    interpret_tie_answer,
    judge_statement_fidelity,
    pick_question,
)
from core.runtime.pool import Candidate
from core.runtime.triggers import WeakBriefTrigger


def test_brief_query_text_appends_enrichments_not_user_text():
    brief = ProjectBrief(description="cash-back commerçants")
    brief.enrichments.append("programme de fidélité")
    assert "fidélité" in brief.query_text()
    assert "fidélité" not in brief.text()


def test_enrich_brief_caps_at_4_and_records():
    brief = ProjectBrief(description="d")
    mock = MockProvider([{"additions": [
        {"text": f"t{i}", "kind": "synonym"} for i in range(6)
    ]}])
    enrich_brief(mock, brief)
    assert brief.enrichments == ["t0", "t1", "t2", "t3"]


def test_enrich_brief_dedups_case_and_trailing_plural():
    brief = ProjectBrief(description="d")
    brief.enrichments.append("partenaire commercial")
    mock = MockProvider([{"additions": [
        {"text": "Partenaire Commercial"},  # case-only duplicate → dropped
        {"text": "remises"},                # new term
        {"text": "Remise"},                 # case + plural duplicate of "remises" → dropped
        {"text": "monétique"},              # new term
    ]}])
    enrich_brief(mock, brief)
    assert brief.enrichments == ["partenaire commercial", "remises", "monétique"]


def test_enrich_brief_respects_global_cap():
    brief = ProjectBrief(description="d")
    brief.enrichments.extend([f"terme{i}" for i in range(MAX_TOTAL_ENRICHMENTS)])
    mock = MockProvider([{"additions": [{"text": "nouveau"}]}])
    enrich_brief(mock, brief)
    assert len(brief.enrichments) == MAX_TOTAL_ENRICHMENTS  # nothing added past the cap


def test_enrich_brief_none_provider_is_a_noop():
    brief = ProjectBrief(description="d")
    enrich_brief(None, brief)
    assert brief.enrichments == []


def test_enrich_brief_swallows_contract_failure():
    brief = ProjectBrief(description="d")
    mock = MockProvider([{"bad": 1}, {"still": 2}])  # fails after retry
    enrich_brief(mock, brief)  # must NOT raise (never blocking)
    assert brief.enrichments == []


def test_extract_fields_gates_unknown_sections():
    mock = MockProvider([{"entries": [
        {"section_id": "objectifs", "text": "réduire le délai"},
        {"section_id": "budget", "text": "x"},  # unknown → dropped
    ]}])
    entries, dropped = extract_fields(mock, "réponse libre", EdbState.new())
    assert [e["section_id"] for e in entries] == ["objectifs"]
    assert dropped == ["budget"]


def test_pick_question_gated_to_pool_with_template_fallback():
    weak = Candidate(kind="weak", key="weak", trigger=WeakBriefTrigger())
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    # LLM picks an id outside the pool → fallback to the first candidate's template
    mock = MockProvider([{"candidate_key": "gap:nope", "question": "Q?"}])
    candidate, question = pick_question(mock, [weak, gap], service=None)
    assert candidate.key == "weak"
    assert "préciser" in question  # W2 WEAK_QUESTION template


def test_pick_question_accepts_a_valid_choice():
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    mock = MockProvider([{"candidate_key": "gap:objectifs",
                          "question": "Quel succès visez-vous, sachant le gel T3 ?"}])
    candidate, question = pick_question(mock, [gap], service=None)
    assert candidate.section_id == "objectifs"
    assert question.startswith("Quel succès")


def test_interpret_pivot_uses_llm_verdict_beyond_yes_no():
    # "uniquement en magasin" carries an implicit confirm the token parser misses.
    provider = MockProvider([{"verdict": "confirm"}])
    out = interpret_pivot_answer(provider, "Les TPE sont-ils concernés ?",
                                 "uniquement en magasin", "tpe-acceptation")
    assert out == "confirm"


def test_interpret_pivot_none_provider_returns_none_for_fallback():
    assert interpret_pivot_answer(None, "q", "oui", "d") is None


def test_interpret_pivot_swallows_contract_failure():
    provider = MockProvider([{"bad": 1}, {"still": 2}])
    assert interpret_pivot_answer(provider, "q", "a", "d") is None


def test_interpret_pivot_gates_unknown_verdict_to_none():
    provider = MockProvider([{"verdict": "peut-être"}])
    assert interpret_pivot_answer(provider, "q", "a", "d") is None


def test_interpret_tie_gates_selection_to_offered_domains():
    provider = MockProvider([{"selected": ["credit", "inexistant"]}])
    out = interpret_tie_answer(provider, "credit ou monetique ?", "plutôt le crédit",
                               ("credit", "monetique"))
    assert out == ["credit"]  # the off-list domain is dropped


def test_interpret_tie_none_provider_returns_none():
    assert interpret_tie_answer(None, "q", "a", ("x", "y")) is None


def test_judge_statement_flags_unfaithful_assertions():
    # #2: the judge catches semantic drift the number guard can't (directional date).
    provider = MockProvider([{"issues": ["Date inversée : « jusqu'au » au lieu de « à compter du »."]}])
    issues = judge_statement_fidelity(
        provider, "Le gel court jusqu'au 15 janvier 2026.",
        ["Le gel s'applique à compter du 15 janvier 2026."],
    )
    assert issues and "inversée" in issues[0]


def test_judge_statement_none_provider_returns_empty():
    assert judge_statement_fidelity(None, "x", ["y"]) == []


def test_judge_statement_swallows_contract_failure():
    provider = MockProvider([{"bad": 1}, {"still": 2}])
    assert judge_statement_fidelity(provider, "x", ["y"]) == []


def test_judge_statement_filters_blank_issues():
    provider = MockProvider([{"issues": ["", "  ", "vrai problème"]}])
    assert judge_statement_fidelity(provider, "x", ["y"]) == ["vrai problème"]


def test_pick_question_none_provider_uses_templates():
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    candidate, question = pick_question(None, [gap], service=None)
    assert candidate.key == "gap:objectifs"
    assert "succès" in question
