"""Per-turn LLM steps (W3 spec §4). Every step degrades deterministically:
no provider, or a failed JSON contract, never blocks a turn (hard rule: the
templates and the gates are the product's floor, the LLM is the polish)."""

from core.dossier.template import EdbState
from core.graph.service import GraphService
from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import LLMProvider
from core.runtime.brief import ProjectBrief
from core.runtime.pool import Candidate
from core.runtime.questions import gap_question, render_question

MAX_ENRICHMENTS_PER_TURN = 4
MAX_TOTAL_ENRICHMENTS = 8  # global cap — keeps the chip row readable (UI debt L6)


def _norm_enrichment(text: str) -> str:
    """Loose dedup key: case-fold, collapse whitespace, drop a trailing plural -s.

    Catches « Partenaire commercial »/« partenaire commercial » and « remise »/
    « remises ». Irregular French plurals (-aux) are out of scope — accepted limit."""
    return " ".join(text.casefold().split()).rstrip("s")


def enrich_brief(provider: LLMProvider | None, brief: ProjectBrief) -> None:
    """Adds revocable vocabulary chips to the retrieval query (spec §4.1).

    Bounded: ≤MAX_ENRICHMENTS_PER_TURN per call, ≤MAX_TOTAL_ENRICHMENTS overall,
    deduplicated on a normalized key (lever 3 — observed chip proliferation)."""
    if provider is None:
        return
    try:
        out = complete_with_retry(
            provider, load_prompt("enrich_brief"), brief.text(),
            required_keys=("additions",),
        )
    except JsonContractError:
        return  # enrichment is sugar — never blocking, the UI shows a discreet notice
    seen = {_norm_enrichment(chip) for chip in brief.enrichments}
    for addition in out["additions"][:MAX_ENRICHMENTS_PER_TURN]:
        if len(brief.enrichments) >= MAX_TOTAL_ENRICHMENTS:
            break
        text = str(addition.get("text", "")).strip()
        key = _norm_enrichment(text)
        if text and key not in seen:
            brief.enrichments.append(text)
            seen.add(key)


def extract_fields(
    provider: LLMProvider | None, answer: str, edb: EdbState
) -> tuple[list[dict], list[str]]:
    """Proposes EDB entries from a free answer; returns (gated entries, dropped ids)."""
    if provider is None:
        return [], []
    allowed = set(edb.sections)
    system = load_prompt("extract_fields").replace("{sections}", ", ".join(sorted(allowed)))
    try:
        out = complete_with_retry(provider, system, answer, required_keys=("entries",))
    except JsonContractError:
        return [], []
    entries, dropped = [], []
    for raw in out["entries"]:
        section_id = raw.get("section_id", "")
        if section_id in allowed and raw.get("text"):
            entries.append({"section_id": section_id, "text": raw["text"],
                            "node_refs": list(raw.get("node_refs", []))})
        else:
            dropped.append(section_id)
    return entries, dropped


def interpret_pivot_answer(
    provider: LLMProvider | None, question: str, answer: str, domain: str
) -> str | None:
    """LLM verdict on a pivot answer: 'confirm' | 'exclude' | 'unclear', or None to
    fall back to deterministic yes/no parsing (no provider, failure, or junk verdict).
    The LLM judges meaning ('uniquement en magasin' = confirm); the runtime still owns
    the domain and the effect (#1 — hard rule 1)."""
    if provider is None:
        return None
    system = load_prompt("interpret_pivot").replace("{domain}", domain)
    user = f"Question posée : {question}\nRéponse de l'utilisateur : {answer}"
    try:
        out = complete_with_retry(provider, system, user, required_keys=("verdict",))
    except JsonContractError:
        return None
    verdict = str(out.get("verdict", ""))
    return verdict if verdict in ("confirm", "exclude", "unclear") else None


def interpret_tie_answer(
    provider: LLMProvider | None, question: str, answer: str, domains: tuple[str, ...]
) -> list[str] | None:
    """LLM selection among the two tie domains, gated to the offered pair; None to fall
    back to deterministic token matching."""
    if provider is None:
        return None
    system = load_prompt("interpret_tie").replace("{domains}", " / ".join(domains))
    user = f"Question posée : {question}\nRéponse de l'utilisateur : {answer}"
    try:
        out = complete_with_retry(provider, system, user, required_keys=("selected",))
    except JsonContractError:
        return None
    return [str(d) for d in out.get("selected", []) if str(d) in domains]


def _template_question(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        return gap_question(candidate.section_id)
    return render_question(candidate.trigger, service)


def _candidate_context(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        return f"[{candidate.key}] section EDB manquante — piste : {gap_question(candidate.section_id)}"
    return f"[{candidate.key}] ambiguïté graphe ({candidate.kind}) — gabarit : {_template_question(candidate, service)}"


def pick_question(
    provider: LLMProvider | None,
    pool: list[Candidate],
    service: GraphService | None,
) -> tuple[Candidate, str]:
    """LLM choice gated to the pool; templates are the permanent fallback (spec §4.4)."""
    assert pool, "pick_question requires a non-empty pool"
    fallback = (pool[0], _template_question(pool[0], service))
    if provider is None:
        return fallback
    user = "\n".join(_candidate_context(c, service) for c in pool)
    try:
        out = complete_with_retry(
            provider, load_prompt("pick_question"), user,
            required_keys=("candidate_key", "question"),
        )
    except JsonContractError:
        return fallback
    by_key = {c.key: c for c in pool}
    candidate = by_key.get(str(out["candidate_key"]))
    question = str(out["question"]).strip()
    if candidate is None or not question:
        return fallback  # gated: an id outside the pool is an LLM error, not a crash
    return candidate, question
