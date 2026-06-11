from core.graph.models import System
from core.graph.service import GraphService
from core.runtime.questions import WEAK_QUESTION, render_question
from core.runtime.triggers import DomainTieTrigger, PivotTrigger, WeakBriefTrigger


def make_service() -> GraphService:
    node = System(
        id="sys-logiciel-tpe",
        name="Logiciel d'acceptation TPE",
        description="Acceptation en magasin.",
        owner_team="Monétique",
        domains=["tpe-acceptation"],
    )
    return GraphService({node.id: node}, [])


def test_weak_template() -> None:
    assert render_question(WeakBriefTrigger(), make_service()) == WEAK_QUESTION
    assert "préciser" in WEAK_QUESTION


def test_tie_template() -> None:
    question = render_question(
        DomainTieTrigger(domain_a="credit", domain_b="monetique"), make_service()
    )
    assert question == "Le projet relève-t-il plutôt de « credit » ou de « monetique » ?"


def test_pivot_template_uses_node_label() -> None:
    question = render_question(
        PivotTrigger(domain="tpe-acceptation", node_id="sys-logiciel-tpe"), make_service()
    )
    assert question == (
        "Le périmètre inclut-il « tpe-acceptation » ? "
        "(Logiciel d'acceptation TPE serait alors concerné)"
    )
