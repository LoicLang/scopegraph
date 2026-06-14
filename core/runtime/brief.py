"""ProjectBrief: the accumulated transcript and its positive semantic projection.

The full transcript remains available through text(). query_text() omits the question
of an excluded graph pivot, so an irrelevant topic introduced by the assistant does not
become positive retrieval evidence on the next round.
"""

from pydantic import BaseModel, Field


class QA(BaseModel):
    question: str
    answer: str
    include_question_in_query: bool = True


class ProjectBrief(BaseModel):
    description: str
    qa: list[QA] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # user-confirmed only
    excluded_domains: list[str] = Field(default_factory=list)
    enrichments: list[str] = Field(default_factory=list)  # AI-added query vocabulary

    def text(self) -> str:
        parts = [self.description, *(f"{item.question} {item.answer}" for item in self.qa)]
        return "\n".join(parts)

    def positive_text(self) -> str:
        parts = [self.description]
        for item in self.qa:
            if item.include_question_in_query:
                parts.append(f"{item.question} {item.answer}")
            else:
                parts.append(item.answer)
        return "\n".join(parts)

    def query_text(self) -> str:
        """Retrieval query = the user's words + revocable AI vocabulary (W3 spec §4.1)."""
        if not self.enrichments:
            return self.positive_text()
        return self.positive_text() + "\n" + " ".join(self.enrichments)
