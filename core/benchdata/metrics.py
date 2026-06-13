"""Conversation-quality metrics over a driven ScopingSession (conversation-eval).

Pure read-over of the session's end state — no LLM, no I/O. Imported by the harness
and unit-tested hermetically against a template-mode session.
"""

from core.dossier.template import ASKABLE_SECTIONS


def conversation_metrics(session, expected_ids: set[str]) -> dict:
    """End-of-conversation metrics for one scenario run."""
    asked = session.asked
    graph_questions = sum(1 for key in asked if not key.startswith("gap:"))
    gap_questions = sum(1 for key in asked if key.startswith("gap:"))

    filled_askable = sum(1 for sid in ASKABLE_SECTIONS if session.edb.sections[sid])
    edb_completion = filled_askable / len(ASKABLE_SECTIONS)

    claims_valid = sum(1 for p in session.ledger.proposals.values() if p.kind == "claim")
    claims_rejected = sum(1 for r in session.gate_rejections if r.get("kind") == "claim")

    kept_ids: set[str] = set()
    if session.last_result is not None:
        kept_ids = set(session.last_result.node_ids())
    kept_ids |= {p.node_id for p in session.pulled}
    kept_ids -= set(session.rejected_nodes)
    recall = len(expected_ids & kept_ids) / len(expected_ids) if expected_ids else 0.0

    return {
        "challenge_done": session.challenge_done,
        "edb_completion": edb_completion,
        "graph_questions": graph_questions,
        "gap_questions": gap_questions,
        "claims_valid": claims_valid,
        "claims_rejected": claims_rejected,
        "statement_flags": list(session.statement_flags),
        "statement_issues": list(session.statement_issues),
        "expected_recall": recall,
        "map_size": len(kept_ids),
        "confirmed_domains": list(session.brief.domains) if session.brief else [],
        "excluded_domains": list(session.brief.excluded_domains) if session.brief else [],
    }
