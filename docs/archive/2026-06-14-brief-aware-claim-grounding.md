---
summary: completed TDD implementation plan for passing project context to the claim-grounding judge
read_when:
  - implementing brief-aware claim grounding
---

# Brief-Aware Claim Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent false grounding rejections when a claim combines a cited graph fact
with a project fact already stated by the user.

**Architecture:** Preserve the claim schema and gates. Thread the existing
`ProjectBrief` into `judge_claim_grounding`, label graph and project sources separately,
and tighten the prompt so neither source category can justify facts owned by the other.

**Tech Stack:** Python 3.12+, pytest, ruff, externalized French prompts.

---

### Task 1: Thread the brief into grounding

**Files:**
- Modify: `tests/test_llm_steps.py`
- Modify: `tests/test_session.py`
- Modify: `core/runtime/llm_steps.py`
- Modify: `core/runtime/session.py`
- Modify: `prompts/judge_claim_grounding.txt`

- [ ] **Step 1: Write the failing unit test**

Call `judge_claim_grounding(provider, claims, service, brief)` and assert that the
provider user message contains the cited node text, `Contexte projet autorisé`, and
`brief.text()`.

- [ ] **Step 2: Write the failing session test**

Extend the challenge integration assertion so the grounding call contains the live
project description.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_llm_steps.py::test_judge_claim_grounding_receives_graph_and_project_sources \
  tests/test_session.py::test_challenge_runs_when_map_stable_and_fills_ledger_and_edb
```

Expected: failure because `judge_claim_grounding` does not accept or receive the brief.

- [ ] **Step 4: Implement the minimal runtime change**

Add an optional `brief: ProjectBrief | None = None` parameter, include
`brief.text()` under a separately labelled project-context block, pass `self.brief` from
`_run_challenge`, and update the French prompt with the source-ownership rules.

- [ ] **Step 5: Verify GREEN**

Run the focused tests, then:

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
git diff --check
```

- [ ] **Step 6: Update status and archive this plan**

Record the fix in `docs/BUILD-ORDER.md`, move this file to `docs/archive/`, and commit:

```bash
git add core/runtime/llm_steps.py core/runtime/session.py \
  prompts/judge_claim_grounding.txt tests/test_llm_steps.py tests/test_session.py \
  docs/BUILD-ORDER.md docs/specs docs/plans docs/archive
git commit -m "fix: ground claims against graph and project context"
```
