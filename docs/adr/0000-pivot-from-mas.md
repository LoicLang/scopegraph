---
summary: ADR 0000 — why scopegraph exists; the pivot from MAS to ecosystem-aware scoping
read_when:
  - telling the project story (README, interviews)
  - questioning the product positioning
---

# ADR 0000 — Pivot from MAS to scopegraph

Date: 2026-06-09 · Status: accepted

## Context

The predecessor project, **MAS** (multi-agent system), converted fuzzy business needs into
structured project proposals — EDB/SPEC artifacts, Confluence integration, a propose/validate/apply
governance loop. The value proposition was: stop describing a project badly, let an AI fill a
better spec.

The problem was twofold. First, MAS overlapped with an existing public project,
**use-case-assistant**, which takes a vague AI idea and turns it into a structured intake form.
Seen from outside, MAS looked like use-case-assistant with more moving parts — the added complexity
wasn't justified by a visibly different promise.

Second, and more fundamentally, classic scoping assistants treat every project as if it arrived
alone. In a real enterprise — banking IT in particular — a new project is never independent. It
inherits constraints from past decisions, depends on existing systems, and competes or overlaps
with parallel initiatives. That propagation is invisible to any tool that only asks "what's your
goal and who are the users?". It surfaces later, as incidents or rework.

## Decision

Stop positioning the product as a better spec-filler. Sell **context-aware project scoping for
non-independent projects** instead.

The core flow changes from `conversation → documents` to:

```
new need → existing ecosystem graph → links / dependencies / risks → contextualized scoping
```

The LLM no longer generates a proposal from the conversation alone; it reasons over a retrieved
subgraph of related systems, past projects, prior decisions, and inherited constraints — with every
claim grounded in a node ID the runtime can verify.

The project is renamed from MAS to **scopegraph**: "multi-agent system" described an implementation
detail; "scopegraph" names the promise. The old repository stays private as `mas-legacy`.

## Consequences

**Portfolio narrative clarified:**
- `use-case-assistant` captures the need → `scopegraph` scopes it within everything that already
  exists → (roadmap) `ecosystem-foundry` builds the ecosystem graph from documents.
  Three links, zero redundancy.

**Patterns ported from MAS (surgically, not wholesale):**
- propose / validate / apply governance flow
- runtime-authority logic (deterministic state transitions; LLM proposes, runtime decides)
- structured source-of-truth handling
- hermetic test approach (MockProvider, no API key needed)

**Features explicitly dropped:**
- Confluence integration
- Artifact-generation pipelines (EDB / SPEC / BACKLOG)
- Multi-agent orchestration layout
- The 16-tool / 5-family toolbox
