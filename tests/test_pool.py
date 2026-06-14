"""One mixed pool per turn: graph-ambiguity candidates (priority) + EDB gaps."""

from core.dossier.template import EdbEntry, EdbState
from core.retrieval.retriever import RetrievalResult, ScoredNode
from core.runtime.brief import ProjectBrief
from core.runtime.pool import build_pool
from core.runtime.questions import gap_question


def _result(anchors=(), expanded=(), domain_scores=None):
    return RetrievalResult(
        anchors=list(anchors), expanded=list(expanded),
        domain_scores=domain_scores or {}, derived_domains=[],
    )


def _anchor(node_id="sys-a", score=0.9):
    return ScoredNode(node_id=node_id, score=score)


def _pivot(node_id, domain, score=0.5):
    return ScoredNode(node_id=node_id, score=score, domains=(domain,),
                      semantic_sim=0.0, anchor_id="sys-a", path=("e",),
                      expansion_only=True)


def test_graph_candidates_outrank_edb_gaps():
    brief = ProjectBrief(description="d")
    edb = EdbState.new()
    result = _result(anchors=[_anchor()],
                     expanded=[_pivot("sys-t", "tpe-acceptation")])
    pool = build_pool(result, brief, set(), edb)
    assert pool[0].kind == "pivot"
    assert any(c.kind == "edb_gap" for c in pool)


def test_all_qualifying_pivots_are_collected_not_just_the_first():
    brief = ProjectBrief(description="d")
    result = _result(anchors=[_anchor()], expanded=[
        _pivot("sys-t", "tpe-acceptation"), _pivot("sys-m", "monetique"),
    ])
    pool = build_pool(result, brief, set(), EdbState.new())
    pivot_domains = [c.domain for c in pool if c.kind == "pivot"]
    assert set(pivot_domains) == {"tpe-acceptation", "monetique"}


def test_asked_log_and_filled_sections_drop_candidates():
    brief = ProjectBrief(description="d")
    edb = EdbState.new()
    edb.add_entry("besoin", EdbEntry(source="user", text="t"))
    result = _result(anchors=[_anchor()],
                     expanded=[_pivot("sys-t", "tpe-acceptation")])
    asked = {"pivot:tpe-acceptation", "gap:objectifs"}
    pool = build_pool(result, brief, asked, edb)
    assert all(c.key != "pivot:tpe-acceptation" for c in pool)
    assert all(c.key != "gap:objectifs" for c in pool)
    assert all(c.key != "gap:besoin" for c in pool)  # filled section → no gap


def test_gap_question_uses_the_template_hint():
    assert "succès" in gap_question("objectifs")


def test_build_pool_re_offers_asked_section_when_insufficient():
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    result = _result()
    brief = ProjectBrief(description="d")
    asked = {"gap:objectifs"}  # already asked once while empty
    pool = build_pool(result, brief, asked, edb, insufficient={"objectifs"},
                      followups={"objectifs": "Chiffrez ?"})
    assert any(c.section_id == "objectifs" and c.followup == "Chiffrez ?" for c in pool)


def test_build_pool_offers_insufficient_filled_section_with_followup():
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    result = _result()
    brief = ProjectBrief(description="d")
    pool = build_pool(result, brief, asked=set(), edb=edb,
                      insufficient={"objectifs"}, followups={"objectifs": "Chiffrez ?"})
    objectifs_candidates = [c for c in pool if c.section_id == "objectifs"]
    assert objectifs_candidates and objectifs_candidates[0].followup == "Chiffrez ?"
