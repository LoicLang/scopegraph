"""Graph schema v1 — the frozen contract (ADR 0001). Changes require a new ADR.

The domain vocabulary is NOT defined here: it is ecosystem data, loaded from
graph/domains.yaml and enforced by the loader.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
CREATED_FROM_PATTERN = r"^(seed|scoping:[a-z0-9-]+|ingestion:[a-z0-9-]+)$"


class EdgeType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    PART_OF = "PART_OF"
    OPERATES_ON = "OPERATES_ON"
    PRODUCED = "PRODUCED"
    CONSTRAINS = "CONSTRAINS"
    SUPERSEDES = "SUPERSEDES"
    RELATES_TO = "RELATES_TO"


# Allowed (source node type, target node type) pairs per edge type (ADR 0001).
# RELATES_TO is deliberately absent: it is the any-to-any last resort.
TOPOLOGY: dict[EdgeType, frozenset[tuple[str, str]]] = {
    EdgeType.PART_OF: frozenset({("feature", "system")}),
    EdgeType.OPERATES_ON: frozenset({
        ("feature", "business_object"),
        ("system", "business_object"),
    }),
    EdgeType.DEPENDS_ON: frozenset({
        ("system", "system"),
        ("feature", "feature"),
        ("feature", "system"),
    }),
    EdgeType.CONSTRAINS: frozenset({
        (source, target)
        for source in ("constraint", "decision")
        for target in ("system", "feature", "business_object", "project")
    }),
    EdgeType.PRODUCED: frozenset({
        ("project", "system"),
        ("project", "feature"),
        ("project", "decision"),
    }),
    EdgeType.SUPERSEDES: frozenset({("decision", "decision")}),
}


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(pattern=SLUG_PATTERN)
    target_id: str = Field(pattern=SLUG_PATTERN)
    type: EdgeType
    note: str = ""
    evidence: str = ""
    created_from: str = Field(default="seed", pattern=CREATED_FROM_PATTERN)
    verified: bool = False

    @model_validator(mode="after")
    def relates_to_must_carry_note(self) -> "Edge":
        if self.type is EdgeType.RELATES_TO and not self.note.strip():
            raise ValueError("RELATES_TO is a last-resort link and must carry a note (ADR 0001)")
        return self
