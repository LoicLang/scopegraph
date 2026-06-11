import pytest

from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService
from core.retrieval import config
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
    assert final.question is None  # no trigger left → map stable
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
    session.state = SessionState.CHALLENGING
    with pytest.raises(NotImplementedError):
        session.handle_message("peu importe")
