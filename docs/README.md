---
summary: index of the docs area — hierarchy of truth, layout, hygiene rules
read_when:
  - looking for which doc to read before a task
  - adding, renaming, or archiving a doc
---

# docs/ — index

Run `./scripts/docs-list` for the live index of active docs with their "read when" hints.

## Hierarchy of truth

In case of conflict, the higher one wins:

1. `BUILD-ORDER.md` — current state and next action
2. `specs/2026-06-09-scopegraph-mvp-design.md` — validated MVP design (decisions + architecture)
3. `project-kickoff.md` — founding contract: positioning, pivot, graph schema v1, MVP scope
4. `adr/` — one decision per file, numbered

## Layout

| Path | Role |
|---|---|
| `BUILD-ORDER.md` | The only status doc: where we are, what's next |
| `project-kickoff.md` | Founding document (single source of truth at project start) |
| `adr/` | Architecture decision records (`0000-...`, `0001-...`) |
| `specs/` | Dated design specs — working area, excluded from `docs-list` |
| `plans/` | Dated implementation plans — working area, excluded from `docs-list` |
| `eval/` | Eval cases (French): scopegraph vs naive prompt |
| `archive/` | Completed/superseded material — excluded by default (`--all` to include) |

## Hygiene rules

- Every active doc carries front matter: `summary` (one line) + `read_when` (list).
- Keep active docs short; prefer a test gate over a long explanation.
- Archive completed plans; never let a stale doc pretend to be current.
- Status lives in `BUILD-ORDER.md` only — no duplication anywhere else.
