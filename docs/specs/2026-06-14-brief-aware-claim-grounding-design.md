---
summary: design for judging claim grounding against both cited graph facts and the user project brief
read_when:
  - changing claim grounding or investigating false claim rejections
  - reviewing the Gemini comparison follow-up
status: implemented (2026-06-14)
---

# Brief-aware claim grounding

## Problem

`judge_claim_grounding` currently receives only the text of cited graph nodes. A valid
claim often combines a graph fact with a project fact, for example a freeze recorded in
the graph and the pilot date stated in the brief. The judge sees the project clause as
unsupported and rejects the whole claim.

## Design

Keep the existing claim schema and mandatory node IDs. Pass the accumulated
`ProjectBrief` to `judge_claim_grounding` and render two explicitly labelled source
blocks for every claim:

- cited graph facts, authoritative for dependencies, constraints, risks, and decisions;
- project context, authoritative only for the user's need, scope, dates, objectives, and
  accepted answers.

The prompt accepts a clause only when it is covered by one of those source blocks. The
brief must not justify an invented graph fact, and a graph node must not invent project
scope. Existing recall-first behavior on provider absence or contract failure remains
unchanged.

## Testing

- Unit test: the grounding request includes both the cited node text and the project
  brief under distinct labels.
- Session test: `_run_challenge` passes the live accumulated brief to the grounding call.
- Existing unsupported-claim, no-provider, contract-failure, and missing-verdict tests
  remain green.
