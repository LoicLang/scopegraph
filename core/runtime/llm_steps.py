"""Per-turn LLM steps (W3 spec §4). Every step degrades deterministically:
no provider, or a failed JSON contract, never blocks a turn (hard rule: the
templates and the gates are the product's floor, the LLM is the polish)."""

from core.dossier.template import ASKABLE_SECTIONS, EDB_TEMPLATE_V1, EdbState, section_spec
from core.graph.service import GraphService
from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import LLMProvider
from core.runtime.brief import ProjectBrief
from core.runtime.challenge import node_provenance
from core.runtime.pool import Candidate
from core.runtime.questions import gap_question, render_question

MAX_ENRICHMENTS_PER_TURN = 4
MAX_TOTAL_ENRICHMENTS = 8  # global cap — keeps the chip row readable (UI debt L6)

# Non-canonical section ids emitted by some models in the wild → canonical id.
# Applied before the allowed-section gate so live data isn't silently discarded.
_SECTION_SYNONYMS: dict[str, str] = {
    "parties_prenantes": "utilisateurs",
    "parties prenantes": "utilisateurs",
    "carta": "carte",
    "carte_de_contexte": "carte",
    "perimetre_hors": "perimetre",  # the section holds both in- and out-of-scope; the « hors périmètre : » text prefix (from the prompt) carries the distinction
}


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
    allowed = {s.id for s in EDB_TEMPLATE_V1 if s.owner not in ("runtime", "llm")} & set(edb.sections)
    catalogue = ", ".join(f"{s.id} ({s.title_fr})" for s in EDB_TEMPLATE_V1 if s.id in allowed)
    system = load_prompt("extract_fields").replace("{sections}", catalogue)
    try:
        out = complete_with_retry(provider, system, answer, required_keys=("entries",))
    except JsonContractError:
        return [], []
    entries, dropped = [], []
    for raw in out["entries"]:
        raw_id = raw.get("section_id", "")
        section_id = _SECTION_SYNONYMS.get(raw_id, raw_id)
        if section_id in allowed and raw.get("text"):
            entries.append({"section_id": section_id, "text": raw["text"],
                            "node_refs": list(raw.get("node_refs", []))})
        else:
            dropped.append(raw_id)
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


def judge_statement_fidelity(
    provider: LLMProvider | None, statement: str, source_texts: list[str]
) -> list[str]:
    """LLM faithfulness pass over the free-prose challenge statement (#2). Returns FR
    descriptions of assertions that contradict or are unsupported by the sources —
    catching the semantic drift the deterministic number guard cannot (directional
    dates). [] without a provider or on failure (never blocking)."""
    if provider is None:
        return []
    sources = "\n".join(f"- {text}" for text in source_texts)
    user = f"Sources autorisées :\n{sources}\n\nDéfi à vérifier :\n{statement}"
    try:
        out = complete_with_retry(provider, load_prompt("judge_statement"), user,
                                  required_keys=("issues",))
    except JsonContractError:
        return []
    return [str(issue).strip() for issue in out.get("issues", []) if str(issue).strip()]


def judge_section_sufficiency(
    provider: LLMProvider | None, edb: EdbState
) -> tuple[set[str], dict[str, str]]:
    """LLM judge over the FILLED askable sections: which are too vague/imprecise, and a
    targeted follow-up for each. Returns (insufficient_ids, {section_id: followup_fr}).
    (set(), {}) without a provider or on contract failure — binary completeness survives."""
    if provider is None:
        return set(), {}
    filled = [sid for sid in ASKABLE_SECTIONS if edb.sections[sid]]
    if not filled:
        return set(), {}
    blocks = []
    for sid in filled:
        spec = section_spec(sid)
        content = "\n".join(f"- {e.text}" for e in edb.sections[sid])
        blocks.append(f"[{sid}] critère : {spec.sufficiency_fr}\ncontenu : {content}")
    user = "\n\n".join(blocks)
    try:
        out = complete_with_retry(provider, load_prompt("judge_sufficiency"), user,
                                  required_keys=("verdicts",))
    except JsonContractError:
        return set(), {}
    insufficient: set[str] = set()
    followups: dict[str, str] = {}
    for verdict in out.get("verdicts", []):
        sid = str(verdict.get("section_id", ""))
        if sid in filled and verdict.get("sufficient") is False:
            insufficient.add(sid)
            followup = str(verdict.get("followup_fr", "")).strip()
            if followup:
                followups[sid] = followup
    return insufficient, followups


def judge_claim_grounding(
    provider: LLMProvider | None, claims: list[dict], service: GraphService
) -> list[dict]:
    """Per-claim faithfulness: is every conclusion of the claim's reason covered by the
    text of the nodes it cites? Returns a verdict parallel to `claims`:
    [{"grounded": bool, "reason_fr": str}]. All grounded without a provider, on contract
    failure, or for an empty list (recall-first: the syntactic gate stays the floor)."""
    if provider is None or not claims:
        return [{"grounded": True, "reason_fr": ""} for _ in claims]
    blocks = []
    for i, claim in enumerate(claims):
        facts = node_provenance(service, [str(n) for n in claim.get("node_ids", [])])
        sources = "\n".join(f"- [{f['node_id']}] {f['label']} : {f['text']}" for f in facts)
        blocks.append(f"[{i}] affirmation : {claim.get('reason', '')}\nsources citées :\n{sources}")
    user = "\n\n".join(blocks)
    try:
        out = complete_with_retry(provider, load_prompt("judge_claim_grounding"), user,
                                  required_keys=("verdicts",))
    except JsonContractError:
        return [{"grounded": True, "reason_fr": ""} for _ in claims]
    by_index: dict[int, dict] = {}
    for v in out.get("verdicts", []):
        try:
            by_index[int(v["index"])] = v
        except (KeyError, ValueError, TypeError):
            continue
    verdicts = []
    for i in range(len(claims)):
        v = by_index.get(i, {})
        verdicts.append({
            "grounded": v.get("grounded", True) is not False,  # default keep (recall-first)
            "reason_fr": str(v.get("reason_fr", "")).strip(),
        })
    return verdicts


def _template_question(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        # #2: an insufficient filled section carries a targeted precision follow-up; the
        # deterministic gap question is the fallback (empty section or no provider).
        return candidate.followup or gap_question(candidate.section_id)
    return render_question(candidate.trigger, service)


def _candidate_context(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        hint = candidate.followup or gap_question(candidate.section_id)
        return f"[{candidate.key}] section EDB à compléter/préciser — piste : {hint}"
    return f"[{candidate.key}] ambiguïté graphe ({candidate.kind}) — gabarit : {_template_question(candidate, service)}"


def _edb_context(edb: EdbState | None) -> str:
    if edb is None:
        return "(aucun contenu accepté)"
    lines = [
        f"- {section_id}: {' | '.join(entry.text for entry in entries)}"
        for section_id, entries in edb.sections.items()
        if entries
    ]
    return "\n".join(lines) or "(aucun contenu accepté)"


def pick_question(
    provider: LLMProvider | None,
    pool: list[Candidate],
    service: GraphService | None,
    *,
    brief: ProjectBrief | None = None,
    edb: EdbState | None = None,
) -> tuple[Candidate, str]:
    """LLM choice gated to the pool; templates are the permanent fallback (spec §4.4)."""
    assert pool, "pick_question requires a non-empty pool"
    fallback = (pool[0], _template_question(pool[0], service))
    if provider is None:
        return fallback
    project = brief.text() if brief is not None else "(brief non fourni)"
    confirmed = ", ".join(brief.domains) if brief and brief.domains else "(aucun)"
    excluded = (
        ", ".join(brief.excluded_domains)
        if brief and brief.excluded_domains else "(aucun)"
    )
    candidates = "\n".join(_candidate_context(c, service) for c in pool)
    user = (
        f"Brief complet :\n{project}\n\n"
        f"Domaines confirmés : {confirmed}\n"
        f"Domaines exclus : {excluded}\n\n"
        f"EDB acceptée :\n{_edb_context(edb)}\n\n"
        f"Candidates autorisées :\n{candidates}"
    )
    try:
        out = complete_with_retry(
            provider, load_prompt("pick_question"), user,
            required_keys=("candidate_key", "question"),
        )
    except JsonContractError:
        return fallback
    by_key = {c.key: c for c in pool}
    selected_key = str(out["candidate_key"])
    if selected_key == "skip_graph":
        gap = next((candidate for candidate in pool if candidate.kind == "edb_gap"), None)
        return (
            (gap, _template_question(gap, service))
            if gap is not None else fallback
        )
    candidate = by_key.get(selected_key)
    question = str(out["question"]).strip()
    if candidate is None or not question:
        return fallback  # gated: an id outside the pool is an LLM error, not a crash
    return candidate, question
