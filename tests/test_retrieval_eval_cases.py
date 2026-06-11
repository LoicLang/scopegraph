from pathlib import Path

from core.graph.models import EdgeType
from core.graph.service import GraphService
from core.retrieval.embedder import FakeEmbedder
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import retrieve

SEED = Path(__file__).resolve().parent.parent / "graph"


def seed_retrieve(fragments: list[str], brief: str):
    service = GraphService.from_dir(SEED)
    index = VectorIndex(FakeEmbedder(fragments))
    index.build(service)
    return retrieve(brief, service, index), service


def test_eval_case_1_bnpl_reaches_tpe_in_two_hops() -> None:
    """BNPL mobile (eval case 1): sys-logiciel-tpe has no textual link to the brief —
    only the chain sys-app-mobile → DEPENDS_ON → sys-moteur-autorisation ← DEPENDS_ON ←
    sys-logiciel-tpe can surface it."""
    result, _ = seed_retrieve(
        ["application mobile", "crédit"],
        "Ajouter une option de paiement en 3 fois dans l'application mobile (crédit conso).",
    )
    assert result.anchors[0].node_id == "sys-app-mobile"  # matches both fragments

    by_id = {s.node_id: s for s in result.expanded}
    assert "sys-logiciel-tpe" in by_id, "the 2-hop monétique chain must surface the TPE"
    tpe = by_id["sys-logiciel-tpe"]
    assert tpe.anchor_id == "sys-app-mobile"
    assert len(tpe.path) == 2
    assert all(edge.type is EdgeType.DEPENDS_ON for edge in tpe.path)
    touched = {edge.source_id for edge in tpe.path} | {edge.target_id for edge in tpe.path}
    assert "sys-moteur-autorisation" in touched
    assert tpe.expansion_only  # zero similarity: pure structure — the naive-LLM trap


def test_eval_case_2_beneficiary_context_surfaces() -> None:
    """Bénéficiaires entreprise (eval case 2): the shared rules and the cancelled
    project must be in the retrieved context (anchored or expanded)."""
    result, _ = seed_retrieve(
        ["bénéficiaire"],
        "Permettre aux clients entreprise de créer des bénéficiaires depuis leur portail.",
    )
    ids = set(result.node_ids())
    for expected in (
        "con-carence-beneficiaire-48h",
        "con-sca-ajout-beneficiaire",
        "con-verif-sanctions-creation",
        "dec-ecriture-via-api-benef",
        "proj-refonte-parcours-beneficiaire",
    ):
        assert expected in ids, f"{expected} missing from retrieved context"
