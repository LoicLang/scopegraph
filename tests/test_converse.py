"""Conversational scoping: gated/monotone actions, readiness gate, frozen scoping."""

from core.llm.provider import MockProvider
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.runtime.brief import ProjectBrief
from core.runtime.converse import apply_scope_actions, converse_and_scope
from core.runtime.session import ScopingSession, SessionState
from tests.test_session import make_service

# make_service domains: banque-en-ligne (sys-canal), monetique (sys-moteur, con-regle),
# tpe-acceptation (sys-terminal).
UNIVERSE = {"sys-canal", "sys-moteur", "sys-terminal", "con-regle"}


def _apply(actions, brief, service, rejected, universe=UNIVERSE):
    return apply_scope_actions(
        actions, brief=brief, universe=universe, service=service, rejected_nodes=rejected
    )


# --- apply_scope_actions: the gates + monotone domain pruning -------------------

def test_exclude_domain_prunes_its_nodes_from_the_universe():
    service = make_service()
    brief = ProjectBrief(description="x")
    rejected: dict[str, str] = {}
    out = _apply([{"action": "exclure_domaine", "domaine": "monetique", "raison": "hors sujet"}],
                 brief, service, rejected)
    assert out == []
    assert "monetique" in brief.excluded_domains
    assert "sys-moteur" in rejected and "con-regle" in rejected  # both monetique nodes pruned
    assert "sys-canal" not in rejected                            # other domains untouched


def test_domain_match_is_accent_and_case_insensitive():
    service = make_service()
    brief = ProjectBrief(description="x")
    rejected: dict[str, str] = {}
    out = _apply([{"action": "exclure_domaine", "domaine": "Monétique", "raison": "hors sujet"}],
                 brief, service, rejected)
    assert out == [] and brief.excluded_domains == ["monetique"] and "sys-moteur" in rejected


def test_unknown_domain_is_rejected_not_applied():
    service = make_service()
    brief = ProjectBrief(description="x")
    out = _apply([{"action": "exclure_domaine", "domaine": "inexistant", "raison": "r"}],
                 brief, service, {})
    assert brief.excluded_domains == [] and len(out) == 1 and out[0]["raison_rejet"]


def test_action_without_reason_is_rejected():
    service = make_service()
    brief = ProjectBrief(description="x")
    out = _apply([{"action": "exclure_domaine", "domaine": "monetique", "raison": ""}],
                 brief, service, {})
    assert brief.excluded_domains == [] and len(out) == 1


def test_hors_perimetre_gated_to_the_current_map():
    service = make_service()
    rejected: dict[str, str] = {}
    out = _apply(
        [{"action": "hors_perimetre", "node_id": "sys-moteur", "raison": "pas concerné"},
         {"action": "hors_perimetre", "node_id": "sys-absent", "raison": "pas concerné"}],
        ProjectBrief(description="x"), service, rejected,
    )
    assert rejected == {"sys-moteur": "pas concerné"}            # on-map node applied
    assert len(out) == 1 and out[0]["node_id"] == "sys-absent"   # off-map node rejected


def test_unknown_action_is_rejected():
    out = _apply([{"action": "supprimer_graphe"}], ProjectBrief(description="x"),
                 make_service(), {})
    assert len(out) == 1 and "inconnue" in out[0]["raison_rejet"]


# --- converse_and_scope: parsing + fallback ------------------------------------

def test_converse_returns_none_without_provider():
    assert converse_and_scope(None, phase="entrée", brief_text="b", map_text="",
                              known_domains=[], pending_question=None, user_message="x") is None


def test_converse_parses_all_signals():
    mock = MockProvider([{"message": "ok", "pret_a_mapper": True, "perimetre_stable": False,
                          "advance": False, "question": "Q ?", "actions": [{"action": "x"}]}])
    out = converse_and_scope(mock, phase="cadrage", brief_text="b", map_text="m",
                             known_domains=["credit"], pending_question="Q ?", user_message="u")
    assert out.message == "ok" and out.ready_to_map is True and out.advance is False
    assert out.question == "Q ?" and out.actions == [{"action": "x"}]


def test_converse_contract_failure_falls_back_to_none():
    mock = MockProvider([{"foo": 1}, {"bar": 2}])  # no "message" twice → JsonContractError
    assert converse_and_scope(mock, phase="entrée", brief_text="b", map_text="",
                              known_domains=[], pending_question=None, user_message="x") is None


# --- session machine: readiness gate, freeze, owned question, help -------------

def _conv_session(provider):
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    return ScopingSession(service, index, provider=provider, conversational=True)


def test_readiness_gate_then_freeze_then_owned_question_and_help():
    provider = MockProvider([
        {"message": "Décrivez votre projet."},                              # t1 entrée: not ready
        {"message": "Je regarde le SI.", "pret_a_mapper": True},            # t2 entrée: ready
        {"message": "C'est noté.", "question": "Carte ou TPE ?"},          # t2 cadrage: owns Q
        {"message": "Pas de souci, je reformule.", "question": "Carte ou TPE ?",
         "advance": False},                                                 # t3 cadrage: help
    ])
    s = _conv_session(provider)

    t1 = s.handle_message("bonjour")
    assert s.state is SessionState.DESCRIBING and t1.question is None and not s.universe

    t2 = s.handle_message("un programme de cashback sur le canal mobile")
    assert s.state is SessionState.MAPPING and s.universe          # the recall fired and froze
    assert t2.question == "Carte ou TPE ?"                         # the LLM owns the question
    asked = s.questions_asked

    t3 = s.handle_message("aide moi je comprends pas")
    assert t3.message == "Pas de souci, je reformule."
    assert t3.question == "Carte ou TPE ?"                         # same question re-asked
    assert s.questions_asked == asked                             # did NOT advance
