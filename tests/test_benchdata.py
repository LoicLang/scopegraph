from core.benchdata.metrics import conversation_metrics
from core.benchdata.scenarios import SCENARIOS
from core.graph.models import Constraint, Edge, EdgeType, System
from core.graph.service import GraphService
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.runtime.session import ScopingSession


def test_scenarios_shape():
    assert len(SCENARIOS) == 11
    names = [s[0] for s in SCENARIOS]
    assert len(set(names)) == 11
    assert all(s[2] for s in SCENARIOS)


def test_conversation_metrics_reads_a_driven_session():
    nodes = [
        System(id="sys-canal", name="Canal", description="Canal client mobile.",
               owner_team="T", domains=["banque-en-ligne"]),
        Constraint(id="con-x", title="Règle", statement="Contrainte.", source="PCI",
                   severity="high", domains=["monetique"]),
    ]
    edges = [Edge(source_id="con-x", target_id="sys-canal", type=EdgeType.CONSTRAINS)]
    service = GraphService({n.id: n for n in nodes}, edges)
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)  # template mode
    session.handle_message("améliorer notre canal mobile")  # asks a question
    m = conversation_metrics(session, {"sys-canal"})
    assert 0.0 <= m["edb_completion"] <= 1.0
    assert m["graph_questions"] + m["gap_questions"] == len(session.asked)
    assert m["expected_recall"] == 1.0  # sys-canal is in the map
    assert isinstance(m["statement_flags"], list)
