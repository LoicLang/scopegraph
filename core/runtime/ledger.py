"""Propose/validate/apply ledger (MVP spec §3): the LLM proposes, the USER decides.

Holds claims (challenge output) and extracted EDB field entries as pending cards.
Application (writing accepted entries into the EDB) is the session's job — the
ledger only tracks consent. Serialized with the session.
"""

from dataclasses import dataclass, field


@dataclass
class Proposal:
    id: str
    kind: str  # "claim" | "field"
    text: str  # FR display text (claim reason or field entry text)
    payload: dict  # kind-specific data, applied on accept
    status: str = "pending"  # pending | accepted | rejected

    @classmethod
    def claim(cls, *, kind: str, node_ids: list[str], target_section: str, reason: str):
        return cls(id="", kind="claim", text=reason, payload={
            "claim_kind": kind, "node_ids": node_ids, "target_section": target_section,
        })

    @classmethod
    def field(cls, *, section_id: str, text: str, node_refs: list[str] | None = None):
        return cls(id="", kind="field", text=text, payload={
            "section_id": section_id, "node_refs": node_refs or [],
        })


@dataclass
class Ledger:
    proposals: dict[str, Proposal] = field(default_factory=dict)
    _counter: int = 0

    def add(self, proposal: Proposal) -> str:
        self._counter += 1
        proposal.id = f"p{self._counter}"
        self.proposals[proposal.id] = proposal
        return proposal.id

    def get(self, pid: str) -> Proposal:
        return self.proposals[pid]

    def pending(self) -> list[Proposal]:
        return [p for p in self.proposals.values() if p.status == "pending"]

    def _decide(self, pid: str, status: str) -> Proposal:
        proposal = self.proposals[pid]
        if proposal.status != "pending":
            raise ValueError(f"proposal {pid} already decided: {proposal.status}")
        proposal.status = status
        return proposal

    def accept(self, pid: str, edited_text: str | None = None) -> Proposal:
        proposal = self._decide(pid, "accepted")
        if edited_text is not None:
            proposal.text = edited_text
        return proposal

    def reject(self, pid: str) -> Proposal:
        return self._decide(pid, "rejected")

    def to_dict(self) -> dict:
        return {
            "counter": self._counter,
            "proposals": [
                {"id": p.id, "kind": p.kind, "text": p.text,
                 "payload": p.payload, "status": p.status}
                for p in self.proposals.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        ledger = cls()
        ledger._counter = data["counter"]
        for raw in data["proposals"]:
            ledger.proposals[raw["id"]] = Proposal(**raw)
        return ledger
