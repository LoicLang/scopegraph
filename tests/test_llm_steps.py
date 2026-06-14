"""The three per-turn LLM steps, each with a deterministic no-provider fallback."""

from core.dossier.template import EdbEntry, EdbState
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


def test_pick_question_receives_project_context():
    weak = Candidate(kind="weak", key="weak", trigger=WeakBriefTrigger())
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    brief = ProjectBrief(
        description="hausse temporaire de plafond carte",
        domains=["monetique"],
        excluded_domains=["paiement-instantane"],
    )
    edb = EdbState.new()
    edb.add_entry("contexte", EdbEntry(source="user", text="voyage à l'étranger"))
    mock = MockProvider([{
        "candidate_key": "gap:objectifs",
        "question": "Quel gain mesurable visez-vous ?",
    }])

    candidate, _question = pick_question(
        mock, [weak, gap], service=None, brief=brief, edb=edb
    )

    assert candidate.key == "gap:objectifs"
    user = mock.calls[0][1]
    assert "hausse temporaire de plafond carte" in user
    assert "voyage à l'étranger" in user
    assert "monetique" in user
    assert "paiement-instantane" in user
    assert "[weak]" in user and "[gap:objectifs]" in user


def test_pick_question_skip_graph_selects_first_offered_gap():
    weak = Candidate(kind="weak", key="weak", trigger=WeakBriefTrigger())
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    mock = MockProvider([{"candidate_key": "skip_graph", "question": ""}])

    candidate, question = pick_question(mock, [weak, gap], service=None)

    assert candidate.key == "gap:objectifs"
    assert "succès" in question


def test_pick_question_skip_graph_without_gap_uses_normal_fallback():
    weak = Candidate(kind="weak", key="weak", trigger=WeakBriefTrigger())
    mock = MockProvider([{"candidate_key": "skip_graph", "question": ""}])

    candidate, question = pick_question(mock, [weak], service=None)

    assert candidate.key == "weak"
    assert "préciser" in question


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


def test_judge_sufficiency_returns_insufficient_set_and_followups():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="améliorer l'expérience"))
    provider = MockProvider([{"verdicts": [
        {"section_id": "objectifs", "sufficient": False,
         "followup_fr": "Quel gain chiffré visez-vous, et à quelle échéance ?"},
    ]}])
    insufficient, followups = judge_section_sufficiency(provider, edb)
    assert insufficient == {"objectifs"}
    assert followups["objectifs"].startswith("Quel gain")


def test_judge_sufficiency_none_provider_is_empty():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="x"))
    assert judge_section_sufficiency(None, edb) == (set(), {})


def test_judge_sufficiency_swallows_contract_failure():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="x"))
    provider = MockProvider([{"bad": 1}, {"still": 2}])
    assert judge_section_sufficiency(provider, edb) == (set(), {})


def test_judge_sufficiency_empty_edb_returns_empty():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    assert judge_section_sufficiency(MockProvider([]), edb) == (set(), {})


def test_extract_fields_remaps_known_section_synonyms():
    # the model emits non-canonical ids seen live (parties_prenantes, carta)
    mock = MockProvider([{"entries": [
        {"section_id": "parties_prenantes", "text": "DSI sponsor"},  # → utilisateurs (writable)
        {"section_id": "carta", "text": "x"},                        # → carte (runtime-owned → dropped)
        {"section_id": "objectifs", "text": "+10% conversion"},
    ]}])
    entries, dropped = extract_fields(mock, "réponse", EdbState.new())
    sids = [e["section_id"] for e in entries]
    # parties_prenantes remaps to utilisateurs → accepted
    assert "utilisateurs" in sids
    assert "parties_prenantes" not in dropped
    # carta remaps to carte (runtime-owned) → dropped under original id
    assert "objectifs" in sids
    assert "carta" in dropped  # dropped under the original raw id, not "carte"


def test_extract_fields_rejects_runtime_and_llm_owned_sections():
    mock = MockProvider([{"entries": [
        {"section_id": "challenge", "text": "x"},
        {"section_id": "carte", "text": "y"},
        {"section_id": "objectifs", "text": "+10%"},
    ]}])
    entries, dropped = extract_fields(mock, "r", EdbState.new())
    sids = [e["section_id"] for e in entries]
    assert sids == ["objectifs"]
    assert "challenge" in dropped and "carte" in dropped


# ---------------------------------------------------------------------------
# Task 8: judge_claim_grounding
# ---------------------------------------------------------------------------

def _service_with_one_node(text: str):
    from core.graph.models import System
    from core.graph.service import GraphService
    return GraphService(
        {"sys-x": System(id="sys-x", name="X", description=text, owner_team="T", domains=["d"])},
        [],
    )


def test_judge_claim_grounding_flags_unsupported_conclusion():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("Gel monétique à compter du 15 janvier 2026.")
    claims = [{"kind": "constraint_applies", "node_ids": ["sys-x"],
               "target_section": "contraintes", "reason": "le gel impose aussi un audit KYC"}]
    provider = MockProvider([{"verdicts": [
        {"index": 0, "grounded": False, "reason_fr": "l'audit KYC n'est pas dans la source"},
    ]}])
    verdicts = judge_claim_grounding(provider, claims, service)
    assert verdicts[0]["grounded"] is False
    assert "KYC" in verdicts[0]["reason_fr"]


def test_judge_claim_grounding_none_provider_passes_all():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    claims = [{"node_ids": ["sys-x"], "reason": "r"}]
    assert judge_claim_grounding(None, claims, service) == [{"grounded": True, "reason_fr": ""}]


def test_judge_claim_grounding_empty_claims_is_empty():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    assert judge_claim_grounding(MockProvider([]), [], service) == []


def test_judge_claim_grounding_swallows_contract_failure():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    claims = [{"node_ids": ["sys-x"], "reason": "r"}]
    provider = MockProvider([{"bad": 1}, {"still": 2}])  # fails after the one retry
    assert judge_claim_grounding(provider, claims, service) == [{"grounded": True, "reason_fr": ""}]


def test_judge_claim_grounding_defaults_missing_verdict_to_grounded():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    claims = [{"node_ids": ["sys-x"], "reason": "a"}, {"node_ids": ["sys-x"], "reason": "b"}]
    provider = MockProvider([{"verdicts": [{"index": 1, "grounded": False, "reason_fr": "non couvert"}]}])
    out = judge_claim_grounding(provider, claims, service)
    assert out[0] == {"grounded": True, "reason_fr": ""}  # missing verdict → default keep
    assert out[1]["grounded"] is False
