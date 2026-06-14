"""EDB template v1 — the conversation engine's state (W3 spec §2).

The 12 sections of the project's first framing document (standard French
expression-de-besoins + note-de-cadrage merge). The runtime owns this state;
the LLM only proposes entries that cross a gate and the user ledger.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

Owner = Literal["user", "graph", "mixed", "llm", "runtime"]

# Sections a challenge claim may write into (W3 spec §5 gate B).
CLAIM_SECTIONS = ("dependances", "contraintes", "risques", "perimetre", "jalons")


@dataclass(frozen=True)
class EdbSectionSpec:
    id: str
    title_fr: str
    owner: Owner
    prompt_hint_fr: str  # the deterministic fallback question for gap candidates
    sufficiency_fr: str = ""  # what makes the section precise enough (drives the LLM judge)


EDB_TEMPLATE_V1: tuple[EdbSectionSpec, ...] = (
    EdbSectionSpec("contexte", "Contexte & raison d'être", "mixed",
                   "Dans quel contexte ce besoin apparaît-il (origine, déclencheur) ?",
                   "Un déclencheur concret est nommé (événement, contrainte, opportunité datée)."),
    EdbSectionSpec("besoin", "Expression du besoin", "user",
                   "Quel problème métier ce projet doit-il résoudre, en une phrase ?",
                   "Le problème métier est nommé concrètement (le manque ou le risque actuel et qui il affecte), pas une généralité comme « améliorer l'expérience »."),
    EdbSectionSpec("utilisateurs", "Utilisateurs & parties prenantes", "mixed",
                   "Qui utilisera le résultat, et qui sponsorise le projet ?",
                   "Le sponsor ET les utilisateurs finaux sont nommés."),
    EdbSectionSpec("objectifs", "Objectifs & critères de réussite", "user",
                   "À quelles conditions ce projet sera-t-il un succès ?",
                   "Au moins un critère de réussite mesurable (un chiffre, une cible, un seuil)."),
    EdbSectionSpec("perimetre", "Périmètre in / hors périmètre", "mixed",
                   "Qu'est-ce qui est explicitement dans — et hors — du périmètre ?",
                   "Le dans-périmètre ET le hors-périmètre sont tous deux explicités."),
    EdbSectionSpec("exigences", "Exigences fonctionnelles et non-fonctionnelles", "mixed",
                   "Quelles exigences fortes (fonctionnelles ou non) faut-il poser dès maintenant ?",
                   "Les exigences non-fonctionnelles sont chiffrées quand cela a un sens (volumétrie, SLA, délai)."),
    EdbSectionSpec("dependances", "Dépendances & systèmes impactés", "graph",
                   "Des dépendances connues à signaler ?",
                   ""),
    EdbSectionSpec("contraintes", "Contraintes héritées", "graph",
                   "Des contraintes (réglementaires, gels, standards) à signaler ?",
                   ""),
    EdbSectionSpec("risques", "Risques initiaux", "mixed",
                   "Quels risques voyez-vous à ce stade ?",
                   "Au moins un risque concret avec son origine est nommé."),
    EdbSectionSpec("jalons", "Jalons / échéance cible", "mixed",
                   "Y a-t-il une échéance cible ou des jalons imposés ?",
                   "Une échéance ou un jalon daté est précisé."),
    EdbSectionSpec("challenge", "Challenge & arbitrages ouverts", "llm", "", ""),
    EdbSectionSpec("carte", "Context Map", "runtime", "", ""),
)

_SPEC_BY_ID = {section.id: section for section in EDB_TEMPLATE_V1}
# Sections the conversation may ask about (never the llm/runtime-owned ones).
ASKABLE_SECTIONS = tuple(s.id for s in EDB_TEMPLATE_V1 if s.owner in ("user", "mixed"))
_ASKABLE = ASKABLE_SECTIONS  # internal alias


@dataclass
class EdbEntry:
    source: str  # "user" | "claim:<id>" | "llm"
    text: str
    node_refs: list[str] = field(default_factory=list)


class EdbState:
    """Mutable per-session EDB content; statuses derive from entries."""

    def __init__(self, sections: dict[str, list[EdbEntry]]) -> None:
        self.sections = sections

    @classmethod
    def new(cls) -> "EdbState":
        return cls({section.id: [] for section in EDB_TEMPLATE_V1})

    def add_entry(self, section_id: str, entry: EdbEntry) -> None:
        if section_id not in self.sections:
            raise KeyError(f"unknown EDB section: {section_id}")
        self.sections[section_id].append(entry)

    def status(self, section_id: str) -> str:
        return "filled" if self.sections[section_id] else "empty"

    def missing_sections(self) -> list[str]:
        """Askable sections still empty, in template order (the gap candidates)."""
        return [sid for sid in _ASKABLE if not self.sections[sid]]

    def incomplete_sections(self, insufficient: Collection[str] = frozenset()) -> list[str]:
        """Askable sections still empty OR judged insufficient, in template order.

        `insufficient` is the set of filled-but-imprecise section ids from the LLM
        sufficiency judge; without a provider it is empty → behaves like missing_sections."""
        return [sid for sid in _ASKABLE
                if not self.sections[sid] or sid in insufficient]

    def to_dict(self) -> dict:
        return {
            sid: [
                {"source": e.source, "text": e.text, "node_refs": e.node_refs}
                for e in entries
            ]
            for sid, entries in self.sections.items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EdbState":
        state = cls.new()
        for sid, entries in data.items():
            for e in entries:
                state.add_entry(sid, EdbEntry(e["source"], e["text"], list(e["node_refs"])))
        return state


def section_spec(section_id: str) -> EdbSectionSpec:
    return _SPEC_BY_ID[section_id]
