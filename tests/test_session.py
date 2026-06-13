import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService
from core.retrieval import config
from core.llm.provider import MockProvider
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.runtime.questions import WEAK_QUESTION
from core.runtime.session import ScopingSession, SessionState


def make_service() -> GraphService:
    nodes = [
        System(
            id="sys-canal", name="Canal mobile", description="Canal client mobile.",
            owner_team="T", domains=["banque-en-ligne"],
        ),
        System(
            id="sys-moteur", name="Moteur central",
            description="Traitement central des opérations.",
            owner_team="T", domains=["monetique"],
        ),
        System(
            id="sys-terminal", name="Terminal magasin", description="Acceptation en magasin.",
            owner_team="T", domains=["tpe-acceptation"],
        ),
        Constraint(
            id="con-regle", title="Règle PCI", statement="Cloisonnement réseau requis.",
            source="PCI DSS", severity="high", domains=["monetique"],
        ),
    ]
    edges = [
        Edge(source_id="sys-canal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-terminal", target_id="sys-moteur", type=EdgeType.DEPENDS_ON),
        Edge(source_id="con-regle", target_id="sys-moteur", type=EdgeType.CONSTRAINS),
    ]
    return GraphService({n.id: n for n in nodes}, edges)


def make_session(fragments: list[str]) -> ScopingSession:
    service = make_service()
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return ScopingSession(service, index)


def test_describe_moves_to_mapping_and_asks_pivot_questions() -> None:
    session = make_session(["canal"])
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.state is SessionState.MAPPING
    # strongest expansion-only foreign-domain node is sys-moteur (1 hop, monetique)
    assert turn.question is not None
    assert "monetique" in turn.question


def test_answer_non_excludes_domain_and_loop_converges() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")
    turn = session.handle_message("non")  # monetique out of scope
    kept = set(turn.result.node_ids())
    assert "sys-moteur" not in kept
    assert "con-regle" not in kept
    # next pivot: tpe-acceptation (sys-terminal)
    assert turn.question is not None and "tpe-acceptation" in turn.question
    final = session.handle_message("non")
    # W3: no graph trigger left → the interview flows into EDB gap questions
    assert final.question is not None and "contexte" in final.question
    assert "sys-terminal" not in set(final.result.node_ids())


def test_answer_oui_confirms_domain_and_keeps_nodes() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")
    turn = session.handle_message("oui")
    assert "monetique" in session.brief.domains
    assert "sys-moteur" in set(turn.result.node_ids())


def test_weak_brief_asks_generic_question_first() -> None:
    session = make_session(["canal"])
    turn = session.handle_message("améliorer des choses")  # matches nothing
    assert turn.question == WEAK_QUESTION
    follow_up = session.handle_message("c'est pour le canal mobile")
    assert follow_up.question != WEAK_QUESTION  # T1 never re-fires
    assert {s.node_id for s in follow_up.result.anchors} == {"sys-canal"}


def test_question_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_QUESTIONS", 1)
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")  # question 1 (monetique)
    turn = session.handle_message("non")
    assert turn.question is None  # tpe pivot exists but the cap stops the interview


def test_empty_message_rejected_and_future_states_guarded() -> None:
    session = make_session(["canal"])
    with pytest.raises(ValueError):
        session.handle_message("   ")
    session.handle_message("améliorer notre canal mobile")
    session.state = SessionState.DRAFTING  # W3 handles MAPPING/SCOPING; W4 states stay guarded
    with pytest.raises(NotImplementedError):
        session.handle_message("peu importe")


def test_hedged_answer_is_not_a_confirmation() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")  # pivot monetique pending
    session.handle_message("ni oui ni non")
    assert "monetique" not in session.brief.domains
    assert "monetique" not in session.brief.excluded_domains


def test_session_threads_its_profile_into_retrieve_and_triggers():
    from dataclasses import replace

    from core.retrieval.config import MINILM

    # A fragment that matches sys-canal so retrieval yields anchors under MINILM thresholds.
    BRIEF_MATCHING_FRAGMENT = "canal"

    service = make_service()
    index = VectorIndex(FakeEmbedder([BRIEF_MATCHING_FRAGMENT]))
    index.build(service)

    # tau_weak above any cosine: T1 fires despite a perfect anchor → detect_trigger got the profile
    paranoid = ScopingSession(service, index, profile=replace(MINILM, tau_weak=1.5))
    turn = paranoid.handle_message("améliorer notre canal mobile")
    assert turn.result.anchors  # retrieval still anchored — only the trigger judged it weak
    assert "weak" in paranoid.asked

    # tau_anchor above any cosine: no anchors at all → retrieve got the profile
    blind = ScopingSession(service, index, profile=replace(MINILM, tau_anchor=1.5))
    assert blind.handle_message("améliorer notre canal mobile").result.anchors == []


# -- W3: provider-driven turns, EDB, challenge --------------------------------


def make_challenge_session(provider) -> ScopingSession:
    """Single-system graph: strong anchor, no expansion → no graph trigger fires."""
    nodes = [
        System(id="sys-canal", name="Canal mobile", description="Canal client mobile.",
               owner_team="T", domains=["banque-en-ligne"]),
    ]
    service = GraphService({n.id: n for n in nodes}, [])
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    return ScopingSession(service, index, provider=provider)


def test_full_turn_with_provider_asks_woven_graph_question() -> None:
    # A graph ambiguity (pivot monetique) is present → the runtime offers ONLY graph
    # candidates to the LLM (lever 2: graph ambiguity strictly before EDB gaps); the
    # LLM phrases a woven question.
    # queue: enrich(no additions) · pick_question(valid pivot choice)
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "pivot:monetique",
         "question": "Le périmètre touche-t-il la monétique, vu le moteur d'autorisation ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question.startswith("Le périmètre touche-t-il la monétique")
    assert "pivot:monetique" in session.asked


def test_graph_ambiguity_is_offered_strictly_before_edb_gaps() -> None:
    # The LLM tries to pick an EDB gap, but the runtime only offered graph candidates,
    # so the out-of-pool pick is gated back to the graph candidate's template (lever 2).
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "gap:objectifs", "question": "Question de section ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question is not None
    assert not any(key.startswith("gap:") for key in session.asked)  # graph won


def test_no_silent_turn_when_cap_reached_and_gaps_remain() -> None:
    # Lever 1: past the question cap, a message that asks nothing must still answer.
    session = make_session(["canal"])  # provider=None, template mode
    session.handle_message("améliorer notre canal mobile")  # asks question 1
    session.questions_asked = config.MAX_QUESTIONS  # exhaust the cap
    turn = session.handle_message("quelques précisions libres en plus")
    assert turn.question is None  # cap reached, nothing asked
    assert turn.message is not None  # NEVER a silent turn
    assert "section" in turn.message.lower()


def test_pivot_answer_prose_is_extracted_into_edb_cards() -> None:
    # P1: a rich answer to a GRAPH pivot must still be mined for EDB fields, not discarded
    # (the bug: pivot/tie answers never reached extract_fields).
    # queue: t1 enrich · t1 pick(pivot) · t2 enrich · t2 extract(field) · t2 pick(pivot)
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "pivot:monetique", "question": "Monétique ?"},
        {"additions": []},
        {"entries": [{"section_id": "objectifs", "text": "réduire les appels au CRC"}]},
        {"candidate_key": "pivot:tpe-acceptation", "question": "TPE ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    session.handle_message("améliorer notre canal mobile")  # asks pivot monetique
    turn = session.handle_message(
        "Non, hors monétique ; l'objectif est de réduire les appels au CRC."
    )
    assert any(c.payload.get("section_id") == "objectifs" for c in turn.cards)


def test_challenge_flags_unsourced_numbers_in_statement() -> None:
    # P2: a fabricated figure in the free-prose statement is flagged deterministically.
    provider = MockProvider([
        {"additions": []},
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Environ 30% des cas sont à risque."},
    ])
    session = make_challenge_session(provider)
    session.handle_message("refonte du canal")
    assert "30" in session.statement_flags


def make_multi_pivot_session() -> ScopingSession:
    """Anchor + three foreign-domain systems → three graph pivots (provider=None)."""
    nodes = [
        System(id="sys-anchor", name="Ancre", description="canal ancre central",
               owner_team="T", domains=["da"]),
        System(id="sys-b", name="B", description="systeme b", owner_team="T", domains=["db"]),
        System(id="sys-c", name="C", description="systeme c", owner_team="T", domains=["dc"]),
        System(id="sys-d", name="D", description="systeme d", owner_team="T", domains=["dd"]),
    ]
    edges = [
        Edge(source_id="sys-anchor", target_id="sys-b", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-anchor", target_id="sys-c", type=EdgeType.DEPENDS_ON),
        Edge(source_id="sys-anchor", target_id="sys-d", type=EdgeType.DEPENDS_ON),
    ]
    service = GraphService({n.id: n for n in nodes}, edges)
    index = VectorIndex(FakeEmbedder(["ancre"]))
    index.build(service)
    return ScopingSession(service, index)


def test_graph_questions_interleave_a_discovery_gap() -> None:
    # P3: after two graph pivots in a row, the interview asks a discovery (EDB gap)
    # question even though a pivot still remains — no five-pivots-in-a-row elimination loop.
    session = make_multi_pivot_session()
    session.handle_message("ancre projet")  # q1 (pivot)
    session.handle_message("non")           # q2 (pivot)
    asked_after_2 = set(session.asked)
    assert asked_after_2 and all(k.startswith("pivot:") for k in asked_after_2)
    session.handle_message("non")           # q3 — must be a gap, not the 3rd pivot
    new_key = set(session.asked) - asked_after_2
    assert any(k.startswith("gap:") for k in new_key)


def test_remove_enrichment_does_not_re_enrich() -> None:
    # Lever 3: a chip removal reruns the round (it may ask a fresh question) but must
    # NOT call the LLM for new vocabulary — the user added no words.
    from core.llm.prompts import load_prompt

    enrich_system = load_prompt("enrich_brief")
    provider = MockProvider([
        {"additions": [{"text": "fidélité"}]},                          # turn 1 enrich
        {"candidate_key": "pivot:monetique", "question": "Q monétique ?"},  # turn 1 pick
        {"candidate_key": "pivot:tpe-acceptation", "question": "Q TPE ?"},  # rerun pick
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    session.handle_message("améliorer notre canal mobile")
    session.remove_enrichment(0)
    assert session.brief.enrichments == []
    enrich_calls = [call for call in provider.calls if call[0] == enrich_system]
    assert len(enrich_calls) == 1  # the rerun reused the brief, no second enrichment


def test_no_provider_session_behaves_like_w2_plus_gap_templates() -> None:
    session = make_session(["canal"])  # provider=None
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question is not None  # template (graph trigger or gap hint)
    assert session.challenge_done is False


def _challenge_provider() -> MockProvider:
    # queue: enrich · triage(keep all) · claims(one valid claim + statement)
    return MockProvider([
        {"additions": []},
        {"verdicts": []},  # gate A defaults everything to keep
        {"pulled_justifications": [], "claims": [
            {"kind": "depends_on", "node_ids": ["sys-canal"],
             "target_section": "dependances", "reason": "le canal porte le besoin"}],
         "domains": [], "challenge_statement": "Défi : le gel bloque T3."},
    ])


def test_challenge_runs_when_map_stable_and_fills_ledger_and_edb() -> None:
    provider = _challenge_provider()
    session = make_challenge_session(provider)
    turn = session.handle_message("refonte du canal")
    # both challenge calls must carry the brief — the model judges relevance TO this project
    assert "refonte du canal" in provider.calls[1][1]  # triage user message
    assert "refonte du canal" in provider.calls[2][1]  # claims user message
    assert session.challenge_done is True
    assert session.edb.status("challenge") == "filled"
    pending = session.ledger.pending()
    assert len(pending) == 1 and pending[0].payload["target_section"] == "dependances"
    assert "Défi" in (turn.message or "")


def test_accept_claim_card_writes_edb_section() -> None:
    session = make_challenge_session(_challenge_provider())
    session.handle_message("refonte du canal")
    pid = session.ledger.pending()[0].id
    session.accept_proposal(pid)
    assert session.edb.status("dependances") == "filled"
    assert session.edb.sections["dependances"][0].source == f"claim:{pid}"


def test_challenge_provider_failure_keeps_state_mapping() -> None:
    # queue: enrich ok · triage invalid twice (contract failure)
    provider = MockProvider([{"additions": []}, {"bad": 1}, {"bad": 2}])
    session = make_challenge_session(provider)
    turn = session.handle_message("refonte du canal")
    assert session.challenge_done is False
    assert session.state is SessionState.MAPPING
    assert "réessayez" in (turn.message or "")


def test_restore_node_clears_rejection_and_marks_provenance() -> None:
    session = make_session(["canal"])
    session.rejected_nodes = {"sys-x": "hors sujet"}
    session.restore_node("sys-x")
    assert session.rejected_nodes == {}
    assert "sys-x" in session.restored


def test_remove_enrichment_reruns_the_round() -> None:
    session = make_session(["canal"])
    session.handle_message("améliorer notre canal mobile")
    session.brief.enrichments.append("fidélité")
    turn = session.remove_enrichment(0)
    assert session.brief.enrichments == []
    assert turn.result is not None


def test_tie_answer_matches_whole_domain_tokens_only() -> None:
    from core.runtime.session import _match_domains

    assert _match_domains("plutôt credit-immobilier", ("credit", "credit-immobilier")) == [
        "credit-immobilier"
    ]
    assert _match_domains("le credit, clairement", ("credit", "credit-immobilier")) == ["credit"]
    assert _match_domains("les deux", ("credit", "monetique")) == []
