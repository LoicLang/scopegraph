---
summary: ADR 0001 — graph schema v1 (frozen contract): 7 node types, 7 edge types with
  topology matrix, domain vocabulary as ecosystem data
read_when:
  - touching core/graph/models.py, core/graph/loader.py, or any YAML under graph/
  - proposing any schema or domain-vocabulary change (requires a new ADR)
---

# ADR 0001 — Graph schema v1

Date: 2026-06-10 · Status: accepted

## Context

The graph schema is the only contact point between scopegraph (consumer) and the future
sibling project ecosystem-foundry (producer). Any silent drift between what scopegraph
expects and what ecosystem-foundry emits would break the contract without a visible error
at design time. The schema must therefore be frozen: once this ADR is accepted, no type,
field, or topology rule may change without a successor ADR. At the same time, the schema
must be domain-agnostic — universal across any IT estate (banking, hospital, retail) — so
that porting scopegraph to a new environment requires only swapping per-ecosystem data
files, not touching schema code. Only the domain vocabulary and the graph content are
environment-specific; node and edge types contain nothing banking-specific.

## Decision

### Node types (7)

All nodes share the following fields:

- `id` — slug, prefixed by type: `sys-`, `feat-`, `obj-`, `proj-`, `dec-`, `con-`, `risk-`
- `domains[]` — one or more values, validated at load time against the loaded domain vocabulary
- `tags[]`
- `created_from` — one of `seed`, `scoping:<id>`, or `ingestion:<id>`; `synthetic` added
  by ADR 0002 (stress-test data only, never produced by the runtime)

Specific fields per type:

| Type | Purpose | Specific fields (beyond shared) |
|---|---|---|
| `System` | Existing software or data source | `name`, `aliases[]`, `description`, `owner_team`, `data_quality_notes`, `known_risks[]` |
| `Feature` | A capability of one system | `name`, `description` (concrete behaviour incl. parameters), `parameters[]` |
| `BusinessObject` | Shared business data concept | `name`, `aliases[]`, `description`, `steward_team` |
| `Project` | Past or ongoing project | `name`, `aliases[]`, `description`, `status` (done/ongoing/cancelled), `owner_team`, `outcomes`, `known_risks[]` |
| `Decision` | Past decision constraining the future | `title`, `statement`, `rationale`, `date`, `decided_by`, `still_active` |
| `Constraint` | Standard, regulation, policy, or business rule | `title`, `statement`, `source`, `severity` |
| `Risk` | Known risk attached to the ecosystem | `title`, `statement`, `likelihood`, `impact`, `mitigations[]` |

### Edge types (7) and allowed topology

Endpoint kinds are validated at load time (fail-fast, same as all other graph rules).

| Edge | Allowed source → target | Notes |
|---|---|---|
| `PART_OF` | Feature → System | Exactly one parent per feature; loader-enforced. |
| `OPERATES_ON` | Feature → BusinessObject · System → BusinessObject | `note` may qualify the mode (e.g. "création et modification"). |
| `DEPENDS_ON` | System → System · Feature → Feature · Feature → System | Feature → Feature denotes a real cross-app call, not data coupling. |
| `CONSTRAINS` | Constraint or Decision → System, Feature, BusinessObject, or Project | Attaching to a BusinessObject binds all features that `OPERATES_ON` it; attaching to a Feature is feature-specific. |
| `PRODUCED` | Project → System, Feature, or Decision | Forbidden from `cancelled` projects. |
| `SUPERSEDES` | Decision → Decision | |
| `RELATES_TO` | any → any | Last resort only; `note` is mandatory (model-enforced). |

Edge fields: `source_id`, `target_id`, `type`, `note`, `evidence`, `created_from`, `verified`.
Seed edges carry `verified: true`.

### Shared-constraint semantics

A `Constraint` node is defined once. Its `CONSTRAINS` edges are drawn to every place it
applies. When a `Constraint` is attached to a `BusinessObject`, it binds every `Feature`
that has an `OPERATES_ON` edge to that object — including features not yet created at the
time the constraint was defined. When attached directly to a `Feature`, the constraint is
feature-specific. This structure allows the graph to derive cross-application rule
inheritance from shared data objects without requiring direct application-to-application
edges.

### Cancelled project rule

A `cancelled` project node remains in the graph as a memorial record. Its `outcomes` field
records the lesson learned. Structural edges (`PRODUCED`, `CONSTRAINS`) are forbidden from
cancelled projects; nothing in the graph may `DEPENDS_ON` a cancelled project. Only
`RELATES_TO` edges are allowed, each carrying a `note` with the abandonment reason. The runtime
must surface a cancelled project as history or warning, never as an inherited constraint or
active dependency.

### Domain vocabulary as ecosystem data

The domain vocabulary lives in `graph/domains.yaml`. The loader reads this file alongside
the graph nodes and validates every node's `domains[]` field against it. The vocabulary is
not part of the schema code (`DOMAINS` is not in `models.py`). The 10 initial banking
domains — monetique, tpe-acceptation, paiement-instantane, dsp2-open-banking, lcb-ft,
credit, banque-en-ligne, referentiel-client, editique-reporting, socle-si — are data, not
schema. Porting scopegraph to a different estate means replacing `graph/domains.yaml` and
the graph content; the schema code is unchanged.

Changing the vocabulary (adding or removing a domain) requires a new ADR, because such a
change affects which nodes are valid and which retrieval paths exist.

### Storage format

- One YAML file per node under `graph/nodes/`
- All edges in `graph/edges.yaml`
- The graph is loaded entirely into memory at runtime; there is no persistent database

## Consequences

- `core/graph/models.py` must define Pydantic models for all 7 node types and all 7 edge
  types, plus a `TOPOLOGY` table that maps each edge type to its allowed source and target
  node kinds. The models are the executable form of this ADR.
- All graph rules (topology, single `PART_OF` parent per feature, mandatory `note` on
  `RELATES_TO`, forbidden edges from cancelled projects, vocabulary validation) are enforced
  at load time. Violations cause immediate failure; no silent degradation.
- `core/graph/loader.py` must load `graph/domains.yaml` first, then validate every node's
  `domains[]` against the loaded vocabulary, then enforce topology on every edge.
- Ecosystem-foundry output must validate against these models without modification. Any
  divergence is a producer-side defect, not a consumer-side workaround.
- Porting scopegraph to another IT estate requires swapping `graph/domains.yaml` and the
  graph content files; zero code change.
- Any future change to node types, edge types, topology rules, field definitions, or the
  domain vocabulary requires a new ADR. This document is the diff target.
