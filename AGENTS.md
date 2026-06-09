# AGENTS.md — how AI agents (and humans) work inside scopegraph

Single source of truth for the working doctrine. `CLAUDE.md` is a pointer to this file.
Public on purpose: scopegraph is also an experiment in agentic software development.

## North star

The product in five lines: *I describe a project. scopegraph finds the existing context.
It shows the links. It challenges the need. It generates a contextualized scoping dossier.*

- **Demo-first.** Every chantier must make the demo more convincing
  ([docs/project-kickoff.md](docs/project-kickoff.md) §5). Velocity over completeness.
- **Unit of progress:** a scoping that surfaces a dependency a naive LLM prompt would miss.
- **Readable MVP.** If a feature can't be explained inside the five lines above, it waits.

## Hard rules (non-negotiable)

1. **LLM proposes, runtime decides.** All state transitions go through the deterministic
   runtime authority. The LLM never mutates the source of truth.
2. **Mandatory grounding.** Every dependency, risk, or link claimed by the LLM must cite an
   existing node ID. The runtime rejects ungrounded claims — visibly, never silently.
3. **Schema v1 is frozen.** Any graph-schema change requires an ADR (it is the contract with
   the future ecosystem-foundry repo).
4. **Hermetic tests.** The pytest suite needs no API key, no network, no model download
   (MockProvider + FakeEmbedder). A test that calls a real provider is a bug.
5. **Fictional entities only.** Seed/demo entities never mirror real internal systems —
   banking secrecy and NDA apply. No real system names, no real team names, ever.
6. **Language split.** French: graph content, UI, prompts' output, dossiers, demo, eval cases.
   English: code, comments, docstrings, README, ADRs, repo docs.

## Context order

At the start of any session, read in this order — stop as soon as you have enough:

1. `docs/BUILD-ORDER.md` — current state, next chantier (the only status doc)
2. `./scripts/docs-list` — index of active docs with "read when" hints
3. The docs whose `read_when` matches your task (spec, kickoff, ADRs)
4. Source code

## Workflow

- **Before coding:** brainstorm → design spec in `docs/specs/YYYY-MM-DD-<topic>-design.md` →
  implementation plan in `docs/plans/YYYY-MM-DD-<topic>.md`. No code without a validated spec
  for non-trivial work.
- **During:** TDD (test first, watch it fail, make it pass). Small, focused commits.
- **After:** run the verification (ruff + pytest) and read the output before claiming done.
  Update `docs/BUILD-ORDER.md` at the end of each work session.
- **Docs hygiene:** every active doc carries front matter (`summary` + `read_when`); keep
  active docs short; archive completed plans to `docs/archive/`; status lives in
  BUILD-ORDER.md only — never duplicated into this file or any other doc.

## Code style

- Python 3.12, Pydantic v2, type hints everywhere; ruff is the arbiter (line length 100).
- Clarity over cleverness. Small modules with one purpose; if a file needs a tour guide,
  split it.
- Prompts are externalized in `prompts/*.txt` — never inline in Python.
- Providers and embedders live behind Protocols; no SDK import outside `core/llm/` and
  `core/retrieval/`.

## Git

- Conventional-ish prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
- Never force-push `main`. Never commit secrets — API keys live in `.env` (gitignored).
- Commit messages explain *why* when it isn't obvious.

## Repository philosophy

Chat history = short-term context. Repository = long-term memory. A new agent (or Loïc in
three months) must understand the system by reading: `AGENTS.md` → `docs/BUILD-ORDER.md` →
`docs/` → source. Maintain a self-explaining repository.
