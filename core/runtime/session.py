"""ScopingSession: the deterministic state machine (MVP spec §3, W3 spec §4-§5).

W3 turn pipeline: enrich → retrieve → extract → pool → question | challenge | done.
The runtime owns every decision; the LLM proposes within gates and the ledger.
provider=None degrades to W2-template behavior plus EDB gap questions.
"""

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
    pull_governance,
    render_stabilized,
    render_subgraph,
)
from core.runtime.ledger import Ledger, Proposal
from core.runtime.llm_steps import enrich_brief, extract_fields, pick_question
from core.runtime.pool import Candidate, build_pool
from core.runtime.triggers import DomainTieTrigger, PivotTrigger, WeakBriefTrigger

CHALLENGE_FAILED_MESSAGE = "Le challenge a échoué (modèle) — réessayez."
EDB_COMPLETE_MESSAGE = "EDB complet — prêt pour la rédaction (W4)"


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

    def handle_message(self, text: str) -> Turn:
        text = text.strip()
        if not text:
            raise ValueError("empty message")
        free_text: str | None = None
        if self.state is SessionState.DESCRIBING:
            self.brief = ProjectBrief(description=text)
            self.state = SessionState.MAPPING
        elif self.state in (SessionState.MAPPING, SessionState.SCOPING):
            if self.pending is not None:
                if self._apply_answer(self.pending, text):
                    free_text = text
                self.pending = None
                self.pending_question = None
            else:  # detail volunteered after stability: enrich and re-run
                self.brief.qa.append(QA(question="(précision)", answer=text))
                free_text = text
        else:
            raise NotImplementedError(f"state {self.state} arrives with W4")
        return self._map_round(free_text)

    def _apply_answer(self, candidate: Candidate, answer: str) -> bool:
        """Records the QA and applies domain effects; returns True for free-text answers."""
        assert self.brief is not None
        question = self.pending_question or ""
        self.brief.qa.append(QA(question=question, answer=answer))
        match candidate.trigger:
            case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
                for domain in _match_domains(answer, (domain_a, domain_b)):
                    if domain not in self.brief.domains:
                        self.brief.domains.append(domain)
                # an answer naming neither domain resolves nothing: the QA text still enriches the brief
                return False
            case PivotTrigger(domain=domain):
                verdict = _parse_yes_no(answer)
                if verdict is True and domain not in self.brief.domains:
                    self.brief.domains.append(domain)
                elif verdict is False and domain not in self.brief.excluded_domains:
                    self.brief.excluded_domains.append(domain)
                # unparseable → the QA text alone enriches the brief; never re-asked
                return False
            case WeakBriefTrigger() | None:
                return True  # weak-brief and EDB-gap answers are free prose
        return True  # pragma: no cover

    def _map_round(self, free_text: str | None = None) -> Turn:
        assert self.brief is not None
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
        pool = build_pool(result, self.brief, self.asked, self.edb, profile=self._profile)
        graph_candidates = [c for c in pool if c.kind != "edb_gap"]
        question: str | None = None
        message: str | None = None
        can_ask = self.questions_asked < config.MAX_QUESTIONS
        if graph_candidates and can_ask:
            question = self._ask(pool)
        elif (self.state is SessionState.MAPPING and not self.challenge_done
              and self._provider is not None):
            try:
                self.state = SessionState.CHALLENGING
                message, claim_cards = self._run_challenge(result)
                cards.extend(claim_cards)
                self.state = SessionState.SCOPING
            except JsonContractError:
                self.state = SessionState.MAPPING  # next message retries the challenge
                message = CHALLENGE_FAILED_MESSAGE
        elif pool and can_ask:  # EDB gaps only
            question = self._ask(pool)
        elif not pool:
            message = EDB_COMPLETE_MESSAGE
        return Turn(state=self.state, question=question, result=result,
                    brief=self.brief, message=message, cards=cards)

    def _ask(self, pool: list[Candidate]) -> str:
        candidate, question = pick_question(self._provider, pool, self._service)
        self.asked.add(candidate.key)
        self.questions_asked += 1
        self.pending = candidate
        self.pending_question = question
        return question

    def _run_challenge(self, result: RetrievalResult) -> tuple[str, list[Proposal]]:
        """Two-message challenge (spec §5). Returns (statement, new claim cards)."""
        submitted = {s.node_id for s in [*result.anchors, *result.expanded]}
        triage_user = render_subgraph(result, self._service)
        out1 = complete_with_retry(self._provider, load_prompt("challenge_triage"),
                                   triage_user, required_keys=("verdicts",))
        keeps, rejects, dropped = gate_triage(out1["verdicts"], submitted)
        self.rejected_nodes = rejects
        self.gate_rejections += [{"kind": "triage", "node_id": d} for d in dropped]
        self.pulled = pull_governance(self._service, set(keeps), set(rejects))
        map_ids = set(keeps) | {p.node_id for p in self.pulled}
        claims_user = render_stabilized(keeps, self.pulled, self._service)
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
        statement = str(out2["challenge_statement"])
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
