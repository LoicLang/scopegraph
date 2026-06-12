"""ProjectBrief: the accumulated, structured semantic query (never raw chat history).

Both question and answer text enter text(): the question carries the graph vocabulary
(domain, node name), so a confirmed pivot becomes a direct semantic anchor next round
— the loop converts hops into anchors (W2 spec §4).
"""

from pydantic import BaseModel, Field


class QA(BaseModel):
    question: str
    answer: str


class ProjectBrief(BaseModel):
    description: str
    qa: list[QA] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # user-confirmed only
    excluded_domains: list[str] = Field(default_factory=list)
    enrichments: list[str] = Field(default_factory=list)  # AI-added query vocabulary

    def text(self) -> str:
        parts = [self.description, *(f"{item.question} {item.answer}" for item in self.qa)]
        return "\n".join(parts)

    def query_text(self) -> str:
        """Retrieval query = the user's words + revocable AI vocabulary (W3 spec §4.1)."""
        if not self.enrichments:
            return self.text()
        return self.text() + "\n" + " ".join(self.enrichments)
