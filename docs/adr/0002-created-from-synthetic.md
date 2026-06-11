---
summary: ADR 0002 — `created_from: synthetic` provenance label for generated stress-test data
read_when:
  - reviewing distractor stress bench (W3 lot 0) or graph-distractors/ generation
  - understanding why pool nodes carry `created_from: synthetic` instead of `ingestion:synthetic`
---

# ADR 0002 — `created_from: synthetic` provenance label

Date: 2026-06-11 · Status: accepted

## Context

Schema v1 (ADR 0001) freezes `created_from` to `seed | scoping:<id> | ingestion:<id>`.
W3 lot 0 (distractor stress bench, spec 2026-06-11) needs a committed pool of generated
stress-test nodes that must be distinguishable from real ecosystem data everywhere
(loader gates, bench metrics, any future UI filter). `ingestion:synthetic` would fit the
existing pattern but lies about provenance: nothing was ingested.

## Decision

Add the literal `synthetic` to `CREATED_FROM_PATTERN`. It labels generated stress-test
data only. The runtime never produces it; the app and the demo never load nodes carrying
it (the pool lives outside `graph/`). Loader-level enforcement that pool content carries
exactly this label lives in `core/graph/distractors.py`, not in the schema.

## Consequences

- `graph-distractors/` content is schema-valid and mechanically identifiable.
- Bench metrics (anchor intrusion, map pollution) key off `created_from == "synthetic"`.
- Any other future provenance still requires its own ADR.
