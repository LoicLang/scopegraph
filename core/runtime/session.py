"""ScopingSession: the deterministic state machine. W2 implements DESCRIBING → MAPPING;
CHALLENGING and beyond arrive with W3/W4 (MVP spec §3)."""

from dataclasses import dataclass
from enum import StrEnum

from core.graph.service import GraphService
from core.retrieval import config
from core.retrieval.index import VectorIndex
from core.retrieval.retriever import RetrievalResult, retrieve
from core.runtime.brief import QA, ProjectBrief
from core.runtime.questions import render_question
from core.runtime.triggers import (
    DomainTieTrigger,
    PivotTrigger,
    Trigger,
    WeakBriefTrigger,
    detect_trigger,
)


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
    brief: ProjectBrief


class ScopingSession:
    def __init__(self, service: GraphService, index: VectorIndex) -> None:
        self._service = service
        self._index = index
        self.state = SessionState.DESCRIBING
        self.brief: ProjectBrief | None = None
        self.asked: set[str] = set()
        self.questions_asked = 0
        self.pending: Trigger | None = None

    def handle_message(self, text: str) -> Turn:
        text = text.strip()
        if not text:
            raise ValueError("empty message")
        if self.state is SessionState.DESCRIBING:
            self.brief = ProjectBrief(description=text)
            self.state = SessionState.MAPPING
        elif self.state is SessionState.MAPPING:
            if self.pending is not None:
                self._apply_answer(self.pending, text)
                self.pending = None
            else:  # detail volunteered after stability: enrich and re-run
                self.brief.qa.append(QA(question="(précision)", answer=text))
        else:
            raise NotImplementedError(f"state {self.state} arrives with W3/W4")
        return self._map_round()

    def _apply_answer(self, trigger: Trigger, answer: str) -> None:
        assert self.brief is not None
        self.brief.qa.append(
            QA(question=render_question(trigger, self._service), answer=answer)
        )
        match trigger:
            case DomainTieTrigger(domain_a=domain_a, domain_b=domain_b):
                lowered = answer.lower()
                for domain in (domain_a, domain_b):
                    if domain.lower() in lowered and domain not in self.brief.domains:
                        self.brief.domains.append(domain)
            case PivotTrigger(domain=domain):
                verdict = _parse_yes_no(answer)
                if verdict is True and domain not in self.brief.domains:
                    self.brief.domains.append(domain)
                elif verdict is False and domain not in self.brief.excluded_domains:
                    self.brief.excluded_domains.append(domain)
                # unparseable → the QA text alone enriches the brief; never re-asked
            case WeakBriefTrigger():
                pass  # the answer text itself enriches the brief

    def _map_round(self) -> Turn:
        assert self.brief is not None
        result = retrieve(
            self.brief.text(),
            self._service,
            self._index,
            domains=self.brief.domains,
            excluded_domains=self.brief.excluded_domains,
        )
        question: str | None = None
        if self.questions_asked < config.MAX_QUESTIONS:
            trigger = detect_trigger(result, self.brief, self.asked)
            if trigger is not None:
                self.asked.add(trigger.key)
                self.questions_asked += 1
                self.pending = trigger
                question = render_question(trigger, self._service)
        return Turn(state=self.state, question=question, result=result, brief=self.brief)


def _parse_yes_no(answer: str) -> bool | None:
    tokens = {token.strip(".,!?;:()«»\"'").lower() for token in answer.split()}
    if tokens & {"oui", "yes"}:
        return True
    if tokens & {"non", "no"}:
        return False
    return None
