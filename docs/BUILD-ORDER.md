---
summary: short source of truth for the current state and the immediate next chantier
read_when:
  - starting a work session
  - checking what to do next
  - re-scoping before coding
---

# Build order

## Current state (2026-06-10)

- Repo bootstrapped: structure, pyproject, CI (ruff + pytest, green), pre-commit.
- `docs/project-kickoff.md` committed — founding contract (positioning, MVP scope; its §4
  schema is superseded by the 2026-06-10 spec below).
- MVP design spec validated and committed: `docs/specs/2026-06-09-scopegraph-mvp-design.md`
  (language split FR/EN, minimal web UI, Mistral/DeepSeek/Mock providers, multilingual local
  embeddings, iterative retrieval loop, dossier structure, 4-week milestones).
- Schema refined to feature/business-object grain and validated:
  `docs/specs/2026-06-10-graph-schema-fine-grain-design.md` (7 node types, 7 edge types with
  topology matrix, domains as ecosystem data, ~72-node seed, 7 traps).
- Workflow doctrine in place: `AGENTS.md`, `docs/README.md`, `scripts/docs-list`.
- W1 implementation plan rewritten for the refined schema:
  `docs/plans/2026-06-10-week1-foundations.md` (15 TDD tasks, full code included — execute via
  subagent-driven-development). The 2026-06-09 plan is archived, superseded before execution.

## Next chantier — Week 1 (foundations)

Execute `docs/plans/2026-06-10-week1-foundations.md`, task by task, in order:

1. ADR 0000 (pivot from MAS) + ADR 0001 (graph schema v1, written from the 2026-06-10 spec).
2. Schema v1 as Pydantic models (7+7, TOPOLOGY) + vocabulary-aware fail-fast loader +
   in-memory `GraphService` (`get_node`, `neighbors`, `k_hop`) — TDD, hermetic.
3. Seed data: 72 fictional French banking-IT nodes (9 systems, 24 features, 6 business
   objects, 7 projects, 8 decisions, 12 constraints, 6 risks), 100 edges, 7 deliberate traps
   (alias MONAUT, superseded decision, contradiction, 2-hop monétique→TPE chain, constraint
   inheritance via obj-beneficiaire, non-uniform depth, cancelled project).
4. README v1 (English): positioning, pivot story, 6-step workflow, schema universality note,
   demo scenario, honest "seeded registry" statement, roadmap → ecosystem-foundry.
5. Draft the 6 eval cases (French) in `docs/eval/`.

## Later

W2 retrieval + web screens · W3 grounding gate + challenge · W4 dossier + Context Map +
write-back + scripted demo. See spec §8.
