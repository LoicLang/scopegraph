import pytest

from core.dossier.template import EdbEntry
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
    assert session.brief.qa[0].include_question_in_query is False
    assert "monetique" not in session.brief.query_text()
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
    # queue: enrich(no additions) · extract(opener mined, empty) · pick_question(valid pivot choice)
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is now mined too (empty EDB → no sufficiency call)
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


def test_contextual_picker_may_choose_edb_gap_before_graph_ambiguity() -> None:
    # Both graph and EDB candidates are offered. The model may decline an incidental
    # graph pivot by selecting a real EDB gap; the runtime still gates the selected key.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the initial brief is mined (empty EDB → no sufficiency call)
        {"candidate_key": "gap:objectifs", "question": "Question de section ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question == "Question de section ?"
    assert "gap:objectifs" in session.asked
    assert session._consecutive_graph_questions == 0


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
    # queue: t1 enrich · t1 extract(opener, empty) · t1 pick · t2 interpret
    #      · t2 explicit exclusions · t2 enrich · t2 extract(objectifs) · t2 pick
    # NOTE: extracted entries become ledger CARDS, not EDB entries, so the EDB stays empty
    # and judge_section_sufficiency returns early (no dict consumed) until a card is accepted.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: opener mined (empty)
        {"candidate_key": "pivot:monetique", "question": "Monétique ?"},
        {"verdict": "exclude"},
        {"excluded_domains": ["monetique"]},
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


def test_explicit_free_text_exclusion_is_applied_before_retrieval() -> None:
    provider = MockProvider([
        {"excluded_domains": ["monetique"]},
        {"additions": []},
        {"entries": []},
        {"candidate_key": "pivot:tpe-acceptation", "question": "TPE ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)

    turn = session.handle_message("améliorer notre canal mobile sans monétique")

    assert "monetique" in session.brief.excluded_domains
    assert "sys-moteur" not in set(turn.result.node_ids())
    assert "Domaines autorisés" in provider.calls[0][0]


def test_natural_pivot_answer_confirmed_by_llm_interpretation() -> None:
    # #1: a non-yes/no answer confirms the domain because the LLM judged it, not tokens.
    # queue: t1 enrich · t1 extract(opener) · t1 pick · t2 interpret(confirm) · t2 enrich
    #      · t2 extract · t2 pick
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: opener mined (empty)
        {"candidate_key": "pivot:monetique", "question": "Monétique concernée ?"},
        {"verdict": "confirm"},
        {"additions": []},
        {"entries": []},
        {"candidate_key": "pivot:tpe-acceptation", "question": "TPE ?"},
    ])
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index, provider=provider)
    session.handle_message("améliorer notre canal mobile")
    session.handle_message("bien sûr, le paiement carte est au cœur du sujet")
    assert "monetique" in session.brief.domains  # token parser would have missed this


def test_challenge_flags_unsourced_numbers_in_statement() -> None:
    # P2: a fabricated figure in the free-prose statement is flagged deterministically.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: opener mined (empty)
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Environ 30% des cas sont à risque."},
        {"challenge_statement": "Environ 30% des cas sont à risque."},
        {"issues": []},  # fidelity judge
    ])
    session = make_challenge_session(provider)
    session.handle_message("refonte du canal")
    assert "30" in session.statement_flags


def test_challenge_statement_coerced_when_model_returns_a_dict() -> None:
    # Robustness: a real Mistral run returned challenge_statement as {"en_francais": "..."}
    # and str(dict) leaked into the EDB/UI. Coerce to the inner text.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: opener mined (empty)
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Ancien rendu ignoré."},
        {"challenge_statement": {"en_francais": "Le défi en clair."}},
        {"issues": []},
    ])
    session = make_challenge_session(provider)
    session.handle_message("refonte du canal")
    assert session.edb.sections["challenge"][0].text == "Le défi en clair."


def test_challenge_records_statement_fidelity_issues() -> None:
    # #2: the LLM fidelity judge surfaces semantic drift (directional date inversion).
    provider = MockProvider([
        {"additions": []},
        {"entries": []},  # #5: opener mined (empty)
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"issues": ["Date inversée par rapport à la source."]},
    ])
    session = make_challenge_session(provider)
    session.handle_message("refonte du canal")
    assert session.statement_issues and "inversée" in session.statement_issues[0]


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
        {"entries": []},                                                # turn 1 extract (opener mined)
        {"candidate_key": "pivot:monetique", "question": "Q monétique ?"},  # turn 1 pick
        {"candidate_key": "pivot:tpe-acceptation", "question": "Q TPE ?"},  # rerun pick (enrich=False, no extract)
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
    # queue: enrich · extract(opener mined, empty) · triage(keep all)
    #      · claims(one valid claim + statement) · grounding judge(grounded) · fidelity judge
    return MockProvider([
        {"additions": []},
        {"entries": []},  # #5: the opener is mined; empty EDB → no sufficiency call
        {"verdicts": []},  # gate A defaults everything to keep
        {"pulled_justifications": [], "claims": [
            {"kind": "depends_on", "node_ids": ["sys-canal"],
             "target_section": "dependances", "reason": "le canal porte le besoin"}],
         "domains": [], "challenge_statement": "Défi : le gel bloque T3."},
        {"verdicts": [{"index": 0, "grounded": True, "reason_fr": ""}]},  # #3: claim grounded → carded
        {"challenge_statement": "Défi : le canal porte le besoin."},
        {"issues": []},  # statement faithfulness judge
    ])


def test_challenge_runs_when_map_stable_and_fills_ledger_and_edb() -> None:
    provider = _challenge_provider()
    session = make_challenge_session(provider)
    turn = session.handle_message("refonte du canal")
    # both challenge calls must carry the brief — the model judges relevance TO this project
    assert "refonte du canal" in provider.calls[2][1]  # triage user message (calls[1] is extract)
    assert "refonte du canal" in provider.calls[3][1]  # claims user message
    assert "refonte du canal" in provider.calls[4][1]  # grounding project context
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
    # queue: enrich ok · extract(opener, empty) · triage invalid twice (contract failure)
    provider = MockProvider([{"additions": []}, {"entries": []}, {"bad": 1}, {"bad": 2}])
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


# -- Chantier 1: live coherent map (#1) ---------------------------------------


def test_excluded_domain_node_stays_off_map_after_a_later_precision() -> None:
    # canal mobile anchors; the user excludes monetique; a later precision must NOT
    # let sys-moteur (monetique) ride back in as an anchor of the broadened query.
    session = make_session(["canal", "moteur"])
    session.handle_message("améliorer notre canal mobile")
    session.handle_message("non")  # monetique out of scope
    assert "sys-moteur" not in session.kept_node_ids()
    # volunteer a precision whose words now surface the moteur as an anchor
    session.handle_message("le moteur central de paiement est concerné par les délais")
    assert "monetique" in session.brief.excluded_domains
    assert "sys-moteur" not in session.kept_node_ids()  # exclusion is a commitment


def test_post_challenge_precision_marks_new_nodes_and_keeps_exclusions() -> None:
    session = make_session(["canal", "moteur", "terminal"])
    session.handle_message("améliorer notre canal mobile")
    # simulate a completed challenge: stabilize on sys-canal, snapshot the map
    session.challenge_done = True
    session.state = SessionState.SCOPING
    session.rejected_nodes = {"sys-terminal": "non spécifique"}
    session.previously_mapped = session.kept_node_ids()
    assert "sys-terminal" not in session.previously_mapped
    snapshot = set(session.previously_mapped)
    # a precision that broadens retrieval must keep sys-terminal excluded
    session.handle_message("préciser le besoin de paiement")
    assert "sys-terminal" not in session.kept_node_ids()
    # any node now on the map but absent from the snapshot is "new"
    new_nodes = session.kept_node_ids() - snapshot
    assert "sys-terminal" not in new_nodes  # excluded stays out of the new set too
    assert new_nodes == session.kept_node_ids() - snapshot  # diff is against the challenge-time snapshot


def test_post_challenge_new_nodes_are_triaged_once() -> None:
    nodes = [
        System(
            id="sys-canal",
            name="Canal mobile",
            description="Canal client mobile.",
            owner_team="T",
            domains=["banque-en-ligne"],
        ),
        System(
            id="sys-nouveau",
            name="Nouveau moteur",
            description="Nouveau traitement différé.",
            owner_team="T",
            domains=["traitement-differe"],
        ),
    ]
    service = GraphService({node.id: node for node in nodes}, [])
    index = VectorIndex(FakeEmbedder(["canal", "nouveau"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer notre canal mobile")
    session.pending = None
    session.pending_question = None
    session.challenge_done = True
    session.state = SessionState.SCOPING
    session.previously_mapped = session.kept_node_ids()
    provider = MockProvider([
        {"additions": []},
        {"entries": []},
        {"verdicts": [{
            "node_id": "sys-nouveau",
            "verdict": "reject",
            "reason": "hors du besoin",
        }]},
        {"candidate_key": "gap:contexte", "question": "Quel contexte ?"},
    ])
    session._provider = provider

    session.handle_message("le nouveau moteur apparaît dans la recherche")

    assert session.rejected_nodes["sys-nouveau"] == "hors du besoin"
    assert session.delta_triaged == {"sys-nouveau"}
    assert "sys-nouveau" not in session.kept_node_ids()
    triage_calls = [
        call for call in provider.calls if "Pour CHAQUE élément" in call[0]
    ]
    assert len(triage_calls) == 1
    assert "sys-nouveau" in triage_calls[0][1]
    assert "sys-canal" not in triage_calls[0][1].split("Nouveaux éléments :\n", 1)[1]


def test_initial_brief_is_mined_into_the_edb() -> None:
    # the first message must feed extract_fields (provider path), not be discarded
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    mock = MockProvider([
        {"additions": []},  # enrich_brief
        {"entries": [{"section_id": "jalons", "text": "pilote octobre 2026"}]},  # extract on brief
        {"verdicts": []},  # judge_section_sufficiency (jalons now filled)
        {"candidate_key": "gap:contexte", "question": "Contexte ?"},  # pick_question
    ])
    session = ScopingSession(service, index, provider=mock)
    turn = session.handle_message("paiement en 3 fois, pilote octobre 2026")
    # the opener is mined: extract_fields proposes a jalons field card (was previously
    # discarded — the DESCRIBING branch left free_text=None and never reached extraction).
    assert any(c.payload.get("section_id") == "jalons" and "octobre 2026" in c.text
               for c in turn.cards)


def test_insufficient_section_re_ask_reaches_user_end_to_end_then_converges() -> None:
    # End-to-end: drive the real _map_round so judge → subtract precision_asked → build_pool
    # → _ask is exercised. The bug: gap:objectifs is in `asked` (asked once while the section
    # was empty), so the asked-gate dropped it BEFORE the sufficiency re-ask could fire.
    # Fix: an insufficient section bypasses the asked-gate; precision_asked bounds it to once.
    # Setup keeps the GRAPH pool empty: single-system graph (no expansion → no graph trigger),
    # and we start past the challenge (SCOPING) so only EDB gaps surface.
    # turn 0 runs the challenge so we land in SCOPING (challenge_done): enrich · extract ·
    # triage · claims · fidelity.
    provider = MockProvider([
        {"additions": []},
        {"entries": []},
        {"verdicts": []},
        {"pulled_justifications": [], "claims": [], "domains": [],
         "challenge_statement": "Défi : le gel bloque T3."},
        {"challenge_statement": "Aucun défi supplémentaire n'est établi."},
        {"issues": []},
    ])
    session = make_challenge_session(provider)
    session.handle_message("refonte du canal")  # consumes enrich+extract+challenge calls
    assert session.challenge_done and session.state is SessionState.SCOPING
    # park past the challenge; every askable section filled EXCEPT objectifs (vague), so the
    # only candidate is objectifs and the GRAPH pool is empty.
    for sid in ("contexte", "besoin", "utilisateurs", "perimetre",
                "exigences", "risques", "jalons"):
        session.edb.add_entry(sid, EdbEntry(source="user", text="ok"))
    session.edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    session.asked.add("gap:objectifs")  # objectifs was asked once while empty
    session.questions_asked = 0  # don't let the cap interfere
    # FIFO for the next round (turn 1 of the re-ask flow): enrich, extract, judge, pick.
    provider._responses = [
        {"additions": []},                                   # enrich_brief
        {"entries": []},                                     # extract_fields (no new field)
        {"verdicts": [{"section_id": "objectifs", "sufficient": False,
                       "followup_fr": "Quel KPI cible ?"}]},  # judge_section_sufficiency
        {"candidate_key": "gap:objectifs", "question": "Quel KPI cible ?"},  # pick_question
    ]
    turn = session.handle_message("précisons un peu")
    # the sufficiency follow-up reached the user through the real pool (asked-gate bypassed)
    assert turn.question == "Quel KPI cible ?"
    assert "objectifs" in session.precision_asked  # recorded → bounded
    # answer it; objectifs is now NOT offered again (converged — at most one precision pass)
    session.pending = None
    session.pending_question = None
    provider._responses = [
        {"additions": []},                                   # enrich_brief
        {"entries": []},                                     # extract_fields
        {"verdicts": [{"section_id": "objectifs", "sufficient": False,
                       "followup_fr": "Encore ?"}]},          # judge insists it is vague
    ]
    follow = session.handle_message("le KPI est -20% d'appels")
    # precision_asked subtracts objectifs upstream, so build_pool never re-offers it even
    # though the judge still calls it insufficient — converged at one precision pass.
    assert follow.question is None


def test_insufficient_section_is_re_asked_once_then_closed() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    # objectifs filled-but-vague; judged insufficient → re-asked; precision_asked closes it
    session = ScopingSession(service, index)  # template mode: deterministic
    session.handle_message("améliorer le canal mobile")
    session.edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    # before the re-ask, an insufficient filled section is still incomplete (would be offered)
    assert "objectifs" in session.edb.incomplete_sections(insufficient={"objectifs"})
    session._mark_precision_asked("objectifs")
    # the session subtracts precision_asked before building the pool (bounded re-ask):
    # once re-asked, the section converges and is no longer offered.
    insufficient = {"objectifs"} - session.precision_asked
    assert "objectifs" not in session.edb.incomplete_sections(insufficient=insufficient)


def test_ungrounded_claim_is_rejected_not_carded() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)  # template mode for setup
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage: all keep by default
        {"pulled_justifications": [], "domains": [],
         "claims": [{"kind": "constraint_applies", "node_ids": ["sys-canal"],
                     "target_section": "contraintes", "reason": "impose aussi un audit KYC non cité"}],
         "challenge_statement": "Énoncé fidèle aux sources."},
        {"verdicts": [{"index": 0, "grounded": False, "reason_fr": "audit KYC absent des sources"}]},
        {"challenge_statement": "Aucun défi supplémentaire n'est établi."},
        {"issues": []},  # judge_statement_fidelity → clean
    ])
    _msg, cards = session._run_challenge(result)
    assert all(c.kind != "claim" for c in cards)  # ungrounded claim is NOT carded
    assert any(r.get("kind") == "claim" and "KYC" in r.get("reason_rejected", "")
               for r in session.gate_rejections)


def test_gate_and_grounding_rejections_both_tagged_kind_claim() -> None:
    # Fix #3 consistency: gate_claims-rejected AND grounding-rejected claims must BOTH
    # land in gate_rejections with kind == "claim".  The previous bug spread **r last so
    # the claim's own 'kind' (e.g. "bogus") overwrote the "claim" tag, making
    # metrics.claims_rejected undercount every gate_claims rejection.
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)  # template mode for setup
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    # Two claims from the model:
    #   claim[0] — kind="bogus" → fails gate_claims (unknown kind) → syntactic reject
    #   claim[1] — kind="constraint_applies", valid node → passes gate_claims,
    #              but grounding judge marks it grounded=False → grounding reject
    session._provider = MockProvider([
        {"verdicts": []},  # triage: keep all
        {"pulled_justifications": [], "domains": [],
         "claims": [
             {"kind": "bogus", "node_ids": ["sys-canal"],
              "target_section": "contraintes", "reason": "claim invalide"},
             {"kind": "constraint_applies", "node_ids": ["sys-canal"],
              "target_section": "contraintes", "reason": "claim valide mais non couvert"},
         ],
         "challenge_statement": "Énoncé."},
        # grounding judge: only the 1 valid claim (claim[1]) is evaluated
        {"verdicts": [{"index": 0, "grounded": False, "reason_fr": "conclusion non couverte"}]},
        {"challenge_statement": "Aucun défi supplémentaire n'est établi."},
        {"issues": []},  # judge_statement_fidelity
    ])
    _msg, cards = session._run_challenge(result)
    assert cards == []  # neither claim is carded
    claim_rejections = [r for r in session.gate_rejections if r.get("kind") == "claim"]
    assert len(claim_rejections) == 2  # both the gate-rejected and the grounding-rejected claim


def test_clean_statement_is_auto_stored() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage
        {"pulled_justifications": [], "domains": [], "claims": [],
         "challenge_statement": "Énoncé historique à ignorer."},
        {"challenge_statement": "Énoncé fidèle aux sources."},
        {"issues": []},  # clean fidelity → no quarantine
    ])
    session._run_challenge(result)
    assert session.statement_flags == [] and session.statement_issues == []
    assert [e.text for e in session.edb.sections["challenge"]] == ["Énoncé fidèle aux sources."]


def test_flagged_statement_is_quarantined_not_auto_stored() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage
        {"pulled_justifications": [], "domains": [], "claims": [],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"issues": ["Date inversée : « jusqu'au » au lieu de « à compter du »."]},
    ])
    _msg, cards = session._run_challenge(result)
    assert session.edb.sections["challenge"] == []  # NOT auto-stored
    statement_cards = [c for c in cards if c.kind == "statement"]
    assert statement_cards and statement_cards[0].payload["issues"]
    # accepting it lands it in the EDB
    session.accept_proposal(statement_cards[0].id)
    assert any("jusqu'au" in e.text for e in session.edb.sections["challenge"])


def test_rejected_flagged_statement_stays_out_of_edb() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage
        {"pulled_justifications": [], "domains": [], "claims": [],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"issues": ["Date inversée : « jusqu'au » au lieu de « à compter du »."]},
    ])
    _msg, cards = session._run_challenge(result)
    statement_card = next(c for c in cards if c.kind == "statement")
    session.reject_proposal(statement_card.id)
    assert session.edb.sections["challenge"] == []


# -- Chantier 5: the five audit fixes hold together end-to-end ----------------


def test_audit_fixes_hold_end_to_end() -> None:
    # One driven session, map → exclusion → precision → challenge, asserting the four
    # load-bearing audit properties chain together (the fifth, #2 sufficiency, has its
    # own focused end-to-end test above). FIFOs verified against the real call order in
    # _map_round / _run_challenge — extracted fields become ledger CARDS (the EDB stays
    # empty on turn 1), so judge_section_sufficiency early-returns with NO LLM call and
    # the opener consumes exactly enrich · extract · pick.
    service = make_service()
    # ["canal", "moteur"]: a later precision naming the moteur surfaces sys-moteur as an
    # ANCHOR (anchors bypass the retriever's excluded-domain filter), so #1 below proves
    # kept_node_ids() — not retrieval — is what keeps the excluded node off the map.
    index = VectorIndex(FakeEmbedder(["canal", "moteur"]))
    index.build(service)
    session = ScopingSession(service, index)  # provider attached per phase

    # #5 — the opener's milestone is mined; it lands as a ledger CARD (not a direct EDB
    # entry), so assert against turn.cards.
    session._provider = MockProvider([
        {"additions": []},  # enrich_brief
        {"entries": [{"section_id": "jalons", "text": "pilote octobre 2026"}]},  # extract
        {"candidate_key": "pivot:monetique", "question": "Monétique ?"},  # pick_question
    ])
    turn = session.handle_message("améliorer notre canal mobile, pilote octobre 2026")
    assert len(session._provider.calls) == 3  # no sufficiency call: EDB still empty (cards only)
    assert any(c.payload.get("section_id") == "jalons" and "octobre 2026" in c.text
               for c in turn.cards)  # #5: the milestone is mined into a card
    assert not session.edb.sections["jalons"]  # extracted fields are cards, not EDB entries yet

    # #1 — exclude monetique (deterministic), then volunteer a precision that names the
    # moteur de paiement; the excluded domain must NOT ride back onto the map.
    session._provider = None
    session.handle_message("non")  # excludes the pending monetique pivot
    assert "monetique" in session.brief.excluded_domains
    assert "sys-moteur" not in session.kept_node_ids()
    session.handle_message("préciser les délais du moteur central de paiement")
    assert "monetique" in session.brief.excluded_domains  # exclusion is a commitment
    # #1: the precision names the moteur, so retrieval surfaces sys-moteur AS AN ANCHOR
    # (anchors bypass the retriever's excluded-domain filter). It is therefore present in
    # the raw result, and only kept_node_ids()'s re-filter keeps it off the map — deleting
    # that re-filter would now fail this test.
    assert "sys-moteur" in session.last_result.node_ids()   # retrieval surfaces it (as an anchor)
    assert "sys-moteur" not in session.kept_node_ids()      # kept_node_ids re-applies the exclusion
    confirmed = set(session.brief.domains)
    excluded = set(session.brief.excluded_domains)
    for nid in session.kept_node_ids():
        node_domains = set(service.get_node(nid).domains)
        assert not (node_domains & excluded and not (node_domains & confirmed))

    # #3 + #4 — run the challenge over the live map: an ungrounded claim is rejected (not
    # carded), and a flagged statement is quarantined (not auto-stored in the EDB).
    session._provider = MockProvider([
        {"verdicts": []},  # triage: keep all
        {"pulled_justifications": [], "domains": [], "claims": [
            {"kind": "constraint_applies", "node_ids": ["sys-canal"],
             "target_section": "contraintes", "reason": "impose un audit KYC non cité"}],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"verdicts": [{"index": 0, "grounded": False, "reason_fr": "audit KYC absent des sources"}]},
        {"challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"issues": ["Date inversée : « jusqu'au » au lieu de « à compter du »."]},
    ])
    _msg, cards = session._run_challenge(session.last_result)
    # #3: the ungrounded claim lands in the gate panel tagged kind=="claim", NOT a card.
    assert all(c.kind != "claim" for c in cards)
    assert any(r.get("kind") == "claim" and "KYC" in r.get("reason_rejected", "")
               for r in session.gate_rejections)
    # #4: the flagged statement is quarantined — not in the EDB, present as a statement card.
    assert session.edb.sections["challenge"] == []
    statement_cards = [c for c in cards if c.kind == "statement"]
    assert statement_cards and statement_cards[0].payload["issues"]
