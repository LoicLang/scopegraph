"""ScopingSession: the deterministic state machine (MVP spec §3, W3 spec §4-§5).

W3 turn pipeline: enrich → retrieve → extract → pool → question | challenge | done.
The runtime owns every decision; the LLM proposes within gates and the ledger.
provider=None degrades to W2-template behavior plus EDB gap questions.
"""

import datetime
from dataclasses import dataclass, field
from enum import StrEnum

from core.dossier.template import EdbEntry, EdbState
from core.graph.service import GraphService
from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import LLMProvider
from core.retrieval import config
from core.retrieval.config import DEFAULT_PROFILE, RetrievalProfile
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import RetrievalResult, retrieve
from core.runtime.brief import QA, ProjectBrief
from core.runtime.challenge import (
    PulledNode,
    gate_claims,
    gate_domains,
    gate_triage,
    node_provenance,
    pull_governance,
    render_stabilized,
    render_subgraph,
    statement_fact_flags,
)
from core.runtime.ledger import Ledger, Proposal
from core.runtime.llm_steps import (
    enrich_brief,
    extract_fields,
    interpret_pivot_answer,
    interpret_tie_answer,
    judge_section_sufficiency,
    judge_statement_fidelity,
    pick_question,
)
from core.runtime.pool import Candidate, build_pool
from core.runtime.triggers import DomainTieTrigger, PivotTrigger

CHALLENGE_FAILED_MESSAGE = "Le challenge a échoué (modèle) — réessayez."
EDB_COMPLETE_MESSAGE = "EDB complet — prêt pour la rédaction (W4)"
MAX_CONSECUTIVE_GRAPH_QUESTIONS = 2  # P3: interleave a discovery gap after this many pivots


class SessionState(StrEnum):
    DESCRIBING = "DESCRIBING"
    MAPPING = "MAPPING"
    CHALLENGING = "CHALLENGING"
    SCOPING = "SCOPING"
    DRAFTING = "DRAFTING"
    VALIDATED = "VALIDATED"


@dataclass
class Turn:
    state: SessionState
    question: str | None
    result: RetrievalResult
    # NOTE: brief is the live session object, not a snapshot (fine in W2; revisit for multi-turn history in W3)
    brief: ProjectBrief
    message: str | None = None  # assistant text that is not a question
    cards: list[Proposal] = field(default_factory=list)  # new pending ledger items this turn


class ScopingSession:
    def __init__(
        self,
        service: GraphService,
        index: VectorIndex,
        profile: RetrievalProfile = DEFAULT_PROFILE,
        provider: LLMProvider | None = None,
    ) -> None:
        self._service = service
        self._index = index
        self._profile = profile
        self._provider = provider
        self.state = SessionState.DESCRIBING
        self.brief: ProjectBrief | None = None
        self.asked: set[str] = set()
        self.questions_asked = 0
        self.pending: Candidate | None = None
        self.pending_question: str | None = None
        self.edb = EdbState.new()
        self.ledger = Ledger()
        self.challenge_done = False
        self.rejected_nodes: dict[str, str] = {}  # id → reason, the restorable panel
        self.pulled: list[PulledNode] = []
        self.gate_rejections: list[dict] = []
        self.proposed_domains: list[str] = []
        self.restored: set[str] = set()  # user-restored nodes (provenance for the map)
        self.last_result: RetrievalResult | None = None
        self.statement_flags: list[str] = []  # unsourced numbers in the last challenge statement
        self.statement_issues: list[str] = []  # LLM-judged fidelity issues in the statement
        self.previously_mapped: set[str] = set()  # stabilized map snapshotted once at challenge completion (new-node diff); not updated post-challenge
        self.precision_asked: set[str] = set()  # sections already re-asked for precision (convergence)
        self._consecutive_graph_questions = 0  # P3: interleave discovery gaps

    def handle_message(self, text: str) -> Turn:
        text = text.strip()
        if not text:
            raise ValueError("empty message")
        free_text: str | None = None
        if self.state is SessionState.DESCRIBING:
            self.brief = ProjectBrief(description=text)
            self.state = SessionState.MAPPING
            free_text = text  # #5: mine the initial brief too (jalons/objectifs in the opener)
        elif self.state in (SessionState.MAPPING, SessionState.SCOPING):
            if self.pending is not None:
                self._apply_answer(self.pending, text)  # domain effects (pivot/tie)
                self.pending = None
                self.pending_question = None
                free_text = text  # P1: always mine the prose — extraction is orthogonal
            else:  # detail volunteered after stability: enrich and re-run
                self.brief.qa.append(QA(question="(précision)", answer=text))
                free_text = text
        else:
            raise NotImplementedError(f"state {self.state} arrives with W4")
        return self._map_round(free_text)

    def _apply_answer(self, candidate: Candidate, answer: str) -> None:
        """Records the QA and applies pivot/tie domain effects (the prose is mined for
        EDB fields separately, in _map_round — orthogonal to domain resolution)."""
        assert self.brief is not None
        question = self.pending_question or ""
        self.brief.qa.append(QA(question=question, answer=answer))
        match candidate.trigger:
            case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
                domains = (domain_a, domain_b)
                # #1: the LLM judges which domain the answer retains; tokens are the fallback.
                selected = interpret_tie_answer(self._provider, question, answer, domains)
                if selected is None:
                    selected = _match_domains(answer, domains)
                for domain in selected:
                    if domain not in self.brief.domains:
                        self.brief.domains.append(domain)
                # an answer naming neither domain resolves nothing: the QA text still enriches the brief
            case PivotTrigger(domain=domain):
                # #1: the LLM judges inclusion/exclusion ('uniquement en magasin' = confirm);
                # yes/no token parsing is the deterministic fallback. Recall-first: only a
                # clear negative excludes — 'unclear' is a no-op, never a silent drop.
                verdict = interpret_pivot_answer(self._provider, question, answer, domain)
                if verdict is None:
                    verdict = {True: "confirm", False: "exclude", None: "unclear"}[
                        _parse_yes_no(answer)
                    ]
                if verdict == "confirm" and domain not in self.brief.domains:
                    self.brief.domains.append(domain)
                elif verdict == "exclude" and domain not in self.brief.excluded_domains:
                    self.brief.excluded_domains.append(domain)
                # unclear → the QA text alone enriches the brief; never re-asked

    def _map_round(self, free_text: str | None = None, *, enrich: bool = True) -> Turn:
        assert self.brief is not None
        just_challenged = False
        if enrich:  # skip when the user added no words (e.g. a chip-removal rerun) — lever 3
            enrich_brief(self._provider, self.brief)
        result = retrieve(
            self.brief.query_text(),
            self._service,
            self._index,
            domains=self.brief.domains,
            excluded_domains=self.brief.excluded_domains,
            profile=self._profile,
        )
        cards: list[Proposal] = []
        if free_text is not None:
            entries, dropped = extract_fields(self._provider, free_text, self.edb)
            for entry in entries:
                pid = self.ledger.add(Proposal.field(
                    section_id=entry["section_id"], text=entry["text"],
                    node_refs=entry["node_refs"]))
                cards.append(self.ledger.get(pid))
            self.gate_rejections += [
                {"kind": "field", "section_id": d} for d in dropped
            ]
        if self.challenge_done:
            # the map is live post-challenge: recompute the governance pull on the
            # current retrieval against the accumulated exclusions (deterministic).
            keeps = set(result.node_ids()) - set(self.rejected_nodes)
            self.pulled = pull_governance(self._service, keeps, set(self.rejected_nodes))
            confirmed = set(self.brief.domains) if self.brief else set()
            excluded = set(self.brief.excluded_domains) if self.brief else set()
            self.pulled = [
                p for p in self.pulled
                if not (set(self._service.get_node(p.node_id).domains) & excluded
                        and not (set(self._service.get_node(p.node_id).domains) & confirmed))
            ]
        # #2: LLM sufficiency judge marks filled-but-vague sections so they re-enter the
        # pool with a targeted follow-up. Convergence is split: the `asked` gate stops a
        # section from being asked twice while empty; precision_asked stops an insufficient
        # section from being re-asked more than once. Subtracting precision_asked here is
        # the real bound — build_pool lets an insufficient section bypass the `asked` gate,
        # so this subtraction is what keeps the precision re-ask to one pass per section.
        # Without a provider this is (set(), {}), a no-op.
        insufficient, followups = judge_section_sufficiency(self._provider, self.edb)
        insufficient -= self.precision_asked
        pool = build_pool(result, self.brief, self.asked, self.edb,
                          profile=self._profile, insufficient=insufficient, followups=followups)
        graph_candidates = [c for c in pool if c.kind != "edb_gap"]
        gap_candidates = [c for c in pool if c.kind == "edb_gap"]
        question: str | None = None
        message: str | None = None
        can_ask = self.questions_asked < config.MAX_QUESTIONS
        if graph_candidates and can_ask:
            # lever 2: a graph ambiguity is resolved before any EDB gap (the LLM only
            # picks among graph candidates). P3: but interleave a discovery gap after
            # MAX_CONSECUTIVE_GRAPH_QUESTIONS in a row, so the interview discovers the
            # project instead of looping on "is domain X in scope?".
            if self._consecutive_graph_questions >= MAX_CONSECUTIVE_GRAPH_QUESTIONS and gap_candidates:
                question = self._ask(gap_candidates)
                self._consecutive_graph_questions = 0
            else:
                question = self._ask(graph_candidates)
                self._consecutive_graph_questions += 1
        elif (self.state is SessionState.MAPPING and not self.challenge_done
              and self._provider is not None):
            try:
                self.state = SessionState.CHALLENGING
                message, claim_cards = self._run_challenge(result)
                cards.extend(claim_cards)
                self.state = SessionState.SCOPING
                self._consecutive_graph_questions = 0
                just_challenged = True
            except JsonContractError:
                self.state = SessionState.MAPPING  # next message retries the challenge
                message = CHALLENGE_FAILED_MESSAGE
        elif pool and can_ask:  # EDB gaps only (graph exhausted)
            question = self._ask(pool)
            self._consecutive_graph_questions = 0
        if question is None and message is None:
            # lever 1: never a silent turn — acknowledge and state what remains.
            # incomplete_sections() with no insufficient arg == missing_sections() (no-provider
            # path unchanged); with a provider it is sufficiency-aware.
            missing = self.edb.incomplete_sections()
            message = (
                f"Noté. La phase de questions est close — il reste {len(missing)} "
                "section(s) à compléter, décrivez-les directement et je les classerai."
                if missing else EDB_COMPLETE_MESSAGE
            )
        self.last_result = result
        if just_challenged:
            self.previously_mapped = self.kept_node_ids()
        return Turn(state=self.state, question=question, result=result,
                    brief=self.brief, message=message, cards=cards)

    def kept_node_ids(self) -> set[str]:
        """The nodes currently on the map: retrieval ∪ pulled, minus accumulated
        exclusions and excluded-domain nodes. Retrieval drops excluded domains only in
        the expansion layer (anchors bypass it) — re-apply the rule here so an excluded
        domain can never ride back in as an anchor of a broadened post-challenge query."""
        if self.last_result is None:
            return set()
        confirmed = set(self.brief.domains) if self.brief else set()
        excluded = set(self.brief.excluded_domains) if self.brief else set()
        base = set(self.last_result.node_ids()) | {p.node_id for p in self.pulled}
        base -= set(self.rejected_nodes)
        kept = set()
        for nid in base:
            node_domains = set(self._service.get_node(nid).domains)
            if node_domains & excluded and not (node_domains & confirmed):
                continue  # excluded with no confirmed-domain rescue (mirrors retriever._expand)
            kept.add(nid)
        return kept

    def _mark_precision_asked(self, section_id: str) -> None:
        self.precision_asked.add(section_id)

    def _ask(self, pool: list[Candidate]) -> str:
        candidate, question = pick_question(self._provider, pool, self._service)
        self.asked.add(candidate.key)
        # #2: re-asking a FILLED gap section is a precision follow-up — record it in
        # precision_asked, the bound that stops an insufficient section from re-entering
        # the pool next round (build_pool lets it bypass the `asked` gate, so precision_asked
        # is what makes the re-ask converge). An empty section is a first ask, never
        # precision: gating on the section's truthiness keeps it openable.
        if candidate.kind == "edb_gap" and self.edb.sections.get(candidate.section_id):
            self._mark_precision_asked(candidate.section_id)
        self.questions_asked += 1
        self.pending = candidate
        self.pending_question = question
        return question

    def _run_challenge(self, result: RetrievalResult) -> tuple[str, list[Proposal]]:
        """Two-message challenge (spec §5). Returns (statement, new claim cards)."""
        submitted = {s.node_id for s in [*result.anchors, *result.expanded]}
        # The brief MUST ride along: the model judges relevance TO this project —
        # without it, it hallucinates a project from the map (caught by the bench).
        # Today's date rides along too so deadline phrasing stays current (P2: a run
        # said « pilote avant fin 2025 » in 2026).
        today = datetime.date.today().isoformat()
        brief_header = (f"Date du jour (à n'utiliser que pour situer une échéance relative "
                        f"comme « avant la fin de l'année », jamais pour inventer une date) : "
                        f"{today}.\nBrief du projet :\n{self.brief.text()}\n\n")
        triage_user = brief_header + "Carte brute :\n" + render_subgraph(result, self._service)
        out1 = complete_with_retry(self._provider, load_prompt("challenge_triage"),
                                   triage_user, required_keys=("verdicts",))
        keeps, rejects, dropped = gate_triage(out1["verdicts"], submitted)
        self.rejected_nodes.update(rejects)  # accumulate — exclusions persist across reruns
        self.gate_rejections += [{"kind": "triage", "node_id": d} for d in dropped]
        self.pulled = pull_governance(self._service, set(keeps), set(rejects))
        map_ids = set(keeps) | {p.node_id for p in self.pulled}
        claims_user = (brief_header + "Carte stabilisée :\n"
                       + render_stabilized(keeps, self.pulled, self._service))
        out2 = complete_with_retry(self._provider, load_prompt("challenge_claims"),
                                   claims_user, required_keys=(
                                       "pulled_justifications", "claims",
                                       "domains", "challenge_statement"))
        valid, rejected_claims = gate_claims(out2, map_ids, self._service)
        self.gate_rejections += [{"kind": "claim", **r} for r in rejected_claims]
        cards: list[Proposal] = []
        for claim in valid:
            pid = self.ledger.add(Proposal.claim(
                kind=claim["kind"], node_ids=claim["node_ids"],
                target_section=claim["target_section"], reason=claim["reason"]))
            cards.append(self.ledger.get(pid))
        self.proposed_domains = gate_domains(out2.get("domains", []), self._service)
        statement = _coerce_text(out2["challenge_statement"])
        # P2: flag any number in the free-prose statement absent from its sources, and
        # #2: an LLM faithfulness pass for the semantic drift the number guard misses.
        source_texts = [f["text"] for f in node_provenance(self._service, sorted(map_ids))]
        source_texts.append(self.brief.text())
        self.statement_flags = statement_fact_flags(statement, source_texts)
        self.statement_issues = judge_statement_fidelity(self._provider, statement, source_texts)
        self.edb.add_entry("challenge", EdbEntry(source="llm", text=statement))
        self.challenge_done = True
        return statement, cards

    def accept_proposal(self, pid: str, edited_text: str | None = None) -> Proposal:
        proposal = self.ledger.accept(pid, edited_text)
        if proposal.kind == "field":
            self.edb.add_entry(proposal.payload["section_id"], EdbEntry(
                source="user", text=proposal.text,
                node_refs=list(proposal.payload["node_refs"])))
        else:  # claim
            self.edb.add_entry(proposal.payload["target_section"], EdbEntry(
                source=f"claim:{pid}", text=proposal.text,
                node_refs=list(proposal.payload["node_ids"])))
        return proposal

    def reject_proposal(self, pid: str) -> Proposal:
        return self.ledger.reject(pid)

    def restore_node(self, node_id: str) -> None:
        """Moves an LLM-rejected node back into the kept map (user override)."""
        if node_id in self.rejected_nodes:
            del self.rejected_nodes[node_id]
            self.restored.add(node_id)

    def remove_enrichment(self, index: int) -> Turn:
        """Drops one AI vocabulary chip and re-runs the round on the leaner query."""
        assert self.brief is not None
        del self.brief.enrichments[index]
        return self._map_round(enrich=False)


def _coerce_text(value) -> str:
    """A model may wrap the statement in a dict (e.g. {'en_francais': '...'}); pull the
    inner string rather than leaking the dict repr into the EDB/UI."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for inner in value.values():
            if isinstance(inner, str) and inner.strip():
                return inner
    return str(value)


def _tokens(text: str) -> set[str]:
    return {token.strip(".,!?;:()«»\"'").lower() for token in text.split()}


def _match_domains(answer: str, candidates: tuple[str, ...]) -> list[str]:
    """Domains explicitly named in the answer (whole-token match — slugs have no spaces)."""
    tokens = _tokens(answer)
    return [domain for domain in candidates if domain.lower() in tokens]


def _parse_yes_no(answer: str) -> bool | None:
    tokens = _tokens(answer)
    yes = bool(tokens & {"oui", "yes"})
    no = bool(tokens & {"non", "no"})
    if yes and not no:
        return True
    if no and not yes:
        return False
    return None  # hedge ("ni oui ni non") or neither: never a silent confirmation
