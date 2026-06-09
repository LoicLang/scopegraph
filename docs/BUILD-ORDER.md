---
summary: short source of truth for the current state and the immediate next chantier
read_when:
  - starting a work session
  - checking what to do next
  - re-scoping before coding
---

# Build order

## Current state (2026-06-09)

- Repo bootstrapped: structure, pyproject, CI (ruff + pytest, green), pre-commit.
- `docs/project-kickoff.md` committed — founding contract (positioning, schema v1, MVP scope).
- MVP design spec validated and committed: `docs/specs/2026-06-09-scopegraph-mvp-design.md`
  (language split FR/EN, minimal web UI, Mistral/DeepSeek/Mock providers, multilingual local
  embeddings, iterative retrieval loop, dossier structure, 4-week milestones).
- Workflow doctrine in place: `AGENTS.md`, `docs/README.md`, `scripts/docs-list`.

## Next chantier — Week 1 (foundations)

1. Implementation plan for W1 → `docs/plans/` (via writing-plans).
2. ADR 0000 (pivot from MAS) + ADR 0001 (graph schema v1) — content specified in kickoff §1 and §4.
3. Schema v1 as Pydantic models + YAML loader + in-memory `GraphService`
   (`get_node`, `neighbors`, `k_hop`) — TDD, hermetic.
4. Seed data: 15–25 fictional French banking-IT nodes across ≥4 domains, with the deliberate
   traps of kickoff §5.1 (aliases MONAUT/« moteur d'autorisation », contradictory decisions,
   one superseded decision, one 2-hop cross-domain chain monétique→TPE).
5. README v1 (English): positioning, pivot story, 6-step workflow, demo scenario, honest
   "seeded registry" statement, roadmap → ecosystem-foundry.
6. Draft the 5 eval cases (French) in `docs/eval/`.

## Later

W2 retrieval + web screens · W3 grounding gate + challenge · W4 dossier + Context Map +
write-back + scripted demo. See spec §8.
