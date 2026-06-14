---
summary: completed TDD implementation plan for Gemini 3.5 Flash, context-aware questions, exclusion-safe retrieval, delta triage, and matched retesting
read_when:
  - implementing the approved context-aware interview and Gemini design
  - reviewing the Mistral/Gemini comparison work
---

# Context-Aware Interview + Gemini Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four reliability mechanisms identified by the real-user retest, add
Gemini 3.5 Flash as a first-class provider, and compare matched uncached Mistral/Gemini
conversations.

**Architecture:** Keep the existing `LLMProvider` Protocol and deterministic session
authority. Add context to the bounded question chooser, separate the audit transcript
from positive retrieval context, vocabulary-gate explicit domain exclusions, delta-triage
only post-challenge additions, and render the challenge from grounded claims. Every LLM
step remains fail-open/recall-first with a deterministic fallback.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, `google-genai`, pytest, ruff, Qwen3
embeddings, Mistral and Gemini APIs for the non-CI comparison.

---

## File map

- Create `core/llm/gemini.py`: official Gemini transport behind `LLMProvider`.
- Create `prompts/extract_excluded_domains.txt`: gated polarity-to-domain extraction.
- Create `prompts/render_challenge.txt`: grounded-claim-only challenge rendering.
- Modify `core/llm/factory.py`: resolve `gemini`.
- Modify `core/runtime/brief.py`: mark whether each question is positive retrieval context.
- Modify `core/runtime/llm_steps.py`: contextual question choice, exclusions, rendering.
- Modify `core/runtime/challenge.py`: render a node subset for delta triage.
- Modify `core/runtime/session.py`: question policy, delta triage, grounded challenge flow.
- Modify `prompts/pick_question.txt`: relevance veto and full project context contract.
- Modify `prompts/challenge_claims.txt`: structured claims are authoritative; draft prose ignored.
- Modify `scripts/conversation-eval`: Gemini provider and comparison-compatible output.
- Modify `.env.example`, `pyproject.toml`: Gemini configuration and optional dependency.
- Modify focused tests in `tests/test_llm.py`, `tests/test_brief.py`,
  `tests/test_llm_steps.py`, `tests/test_challenge.py`, and `tests/test_session.py`.
- Update `docs/BUILD-ORDER.md` only after the real comparison.

### Task 1: Gemini provider and configuration

**Files:**
- Create: `core/llm/gemini.py`
- Modify: `core/llm/factory.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `tests/test_llm.py`

- [ ] **Step 1: Write failing provider tests**

Add tests that install fake `google`/`google.genai` modules and assert:

```python
def test_gemini_calls_official_sdk_for_json(monkeypatch):
    captured = {}

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text='{"ok": true}')

    class _Client:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = _Models()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = _Client
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    from core.llm.gemini import GeminiProvider

    out = GeminiProvider(api_key="k").complete_json("sys", "user")
    assert out == {"ok": True}
    assert captured["model"] == "gemini-3.5-flash"
    assert captured["contents"] == "user"
    assert captured["config"]["system_instruction"] == "sys"
    assert captured["config"]["temperature"] == 0
    assert captured["config"]["response_mime_type"] == "application/json"
```

Also extend the lazy-import test and add a factory test for
`SCOPEGRAPH_LLM_PROVIDER=gemini`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm.py -q
```

Expected: failure because `core.llm.gemini` and factory support do not exist.

- [ ] **Step 3: Implement the minimal provider**

Create:

```python
"""Gemini provider (official Google Gen AI SDK, lazy import)."""

import json


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash") -> None:
        self.model = model
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = genai.Client(api_key=api_key)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config={
                "system_instruction": system,
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )
        return json.loads(response.text)
```

Add `google-genai` to the `llm` extra, add `GEMINI_API_KEY=` to `.env.example`, and
resolve `gemini` in `make_provider()`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm.py -q
.venv/bin/ruff check core/llm tests/test_llm.py
```

Expected: all focused tests pass and ruff is clean.

- [ ] **Step 5: Commit**

```bash
git add core/llm/gemini.py core/llm/factory.py pyproject.toml .env.example tests/test_llm.py
git commit -m "feat: add Gemini 3.5 Flash provider"
```

### Task 2: Positive retrieval context

**Files:**
- Modify: `core/runtime/brief.py`
- Modify: `core/runtime/session.py`
- Modify: `tests/test_brief.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing brief tests**

Add:

```python
def test_query_text_omits_excluded_pivot_question_but_keeps_answer():
    brief = ProjectBrief(description="hausse temporaire de plafond carte")
    brief.qa.append(QA(
        question="Le projet touche-t-il les bénéficiaires et virements ?",
        answer="Non, uniquement les plafonds carte.",
        include_question_in_query=False,
    ))
    assert "bénéficiaires" not in brief.query_text()
    assert "uniquement les plafonds carte" in brief.query_text()
    assert "bénéficiaires" in brief.text()  # full audit transcript remains
```

Add a session test whose excluded pivot answer produces a QA with
`include_question_in_query=False`; confirmed/unclear pivots and EDB gaps remain `True`.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_brief.py tests/test_session.py -q
```

Expected: `QA` does not accept `include_question_in_query`.

- [ ] **Step 3: Implement the projection**

Extend `QA`:

```python
class QA(BaseModel):
    question: str
    answer: str
    include_question_in_query: bool = True
```

Keep `ProjectBrief.text()` unchanged semantically. Add a private positive projection used
by `query_text()`:

```python
def positive_text(self) -> str:
    parts = [self.description]
    for item in self.qa:
        if item.include_question_in_query:
            parts.append(f"{item.question} {item.answer}")
        else:
            parts.append(item.answer)
    return "\n".join(parts)
```

Change `_apply_answer` to determine the pivot verdict before appending `QA`, and append
with `include_question_in_query=verdict != "exclude"`. Tie and EDB-gap answers stay true.

- [ ] **Step 4: Verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_brief.py tests/test_session.py -q
.venv/bin/ruff check core/runtime/brief.py core/runtime/session.py tests/test_brief.py tests/test_session.py
```

- [ ] **Step 5: Commit**

```bash
git add core/runtime/brief.py core/runtime/session.py tests/test_brief.py tests/test_session.py
git commit -m "fix: keep excluded questions out of retrieval context"
```

### Task 3: Context-aware question selection

**Files:**
- Modify: `core/runtime/llm_steps.py`
- Modify: `core/runtime/session.py`
- Modify: `prompts/pick_question.txt`
- Modify: `tests/test_llm_steps.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing chooser tests**

Add tests proving:

```python
candidate, question = pick_question(
    provider,
    [pivot, gap],
    service,
    brief=brief,
    edb=edb,
)
```

The captured user prompt must contain the project description, accepted EDB content,
confirmed/excluded domains, and both candidates. A provider response
`{"candidate_key": "skip_graph", "question": ""}` must return the first gap candidate
and its deterministic/follow-up question. `skip_graph` with no gap must fall back to the
first offered graph candidate.

Add a session test where graph and gap candidates coexist and the model selects the gap
on the first turn. Assert `_consecutive_graph_questions == 0`.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
```

Expected: signature/context assertions fail and the session currently sends graph-only.

- [ ] **Step 3: Implement contextual choice**

Add a compact EDB renderer in `llm_steps.py`, extend `pick_question` with keyword-only
`brief` and `edb`, and construct:

```text
Brief complet:
...
Domaines confirmés: ...
Domaines exclus: ...
EDB acceptée:
...
Candidates autorisées:
...
```

Gate `candidate_key` to offered keys plus `skip_graph`. In `_map_round`:

- when the graph-question ceiling has been reached and gaps exist, offer only gaps;
- otherwise offer the full pool;
- update `_consecutive_graph_questions` from the selected candidate kind.

The runtime still owns the candidate pool and question cap.

- [ ] **Step 4: Verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
.venv/bin/ruff check core/runtime prompts tests/test_llm_steps.py tests/test_session.py
```

- [ ] **Step 5: Commit**

```bash
git add core/runtime/llm_steps.py core/runtime/session.py prompts/pick_question.txt \
  tests/test_llm_steps.py tests/test_session.py
git commit -m "fix: rank questions with project context"
```

### Task 4: Explicit free-text domain exclusions

**Files:**
- Create: `prompts/extract_excluded_domains.txt`
- Modify: `core/runtime/llm_steps.py`
- Modify: `core/runtime/session.py`
- Modify: `tests/test_llm_steps.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing exclusion tests**

Add a unit test:

```python
provider = MockProvider([{"excluded_domains": [
    "paiement-instantane", "not-a-domain",
]}])
assert extract_excluded_domains(provider, text, service) == ["paiement-instantane"]
```

Add no-provider and contract-failure tests returning `[]`. Add a session test where the
opening brief says `sans changer le plafond de virement`; the exclusion extraction runs
before retrieval and accumulates `paiement-instantane`.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
```

- [ ] **Step 3: Implement the gated step**

The prompt receives the exact known-domain catalogue and instructs the model to return
only domains explicitly excluded by the user's text:

```json
{"excluded_domains": ["..."]}
```

Implement `extract_excluded_domains(provider, text, service)` with
`complete_with_retry`; filter to `service.known_domains()`. In `_map_round`, call it for
each `free_text` before `enrich_brief`/`retrieve` and append unseen exclusions unless the
same domain is already confirmed.

- [ ] **Step 4: Verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
.venv/bin/ruff check core/runtime tests/test_llm_steps.py tests/test_session.py
```

- [ ] **Step 5: Commit**

```bash
git add prompts/extract_excluded_domains.txt core/runtime/llm_steps.py \
  core/runtime/session.py tests/test_llm_steps.py tests/test_session.py
git commit -m "fix: extract explicit domain exclusions"
```

### Task 5: Post-challenge delta triage

**Files:**
- Modify: `core/runtime/challenge.py`
- Modify: `core/runtime/session.py`
- Modify: `tests/test_challenge.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing delta-triage tests**

Add a pure rendering test for `render_node_set({"sys-new"}, service)`. Add an end-to-end
session test that:

1. sets `challenge_done=True` and a stable `previously_mapped`;
2. exposes one newly retrieved sibling;
3. scripts triage to reject only that new node;
4. asserts the stable map was not submitted for re-triage;
5. asserts the sibling enters `rejected_nodes` and stays out of `kept_node_ids()`.

Add a failure test: two invalid triage responses keep the node visible and append a
`{"kind": "delta_triage", ...}` gate rejection.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m pytest tests/test_challenge.py tests/test_session.py -q
```

- [ ] **Step 3: Implement delta triage**

Add `render_node_set(node_ids, service)` using `_node_line` and `_edge_lines`. Add
`self.delta_triaged: set[str]` to the session. During post-challenge rounds:

```python
new_ids = (
    set(result.node_ids())
    - self.previously_mapped
    - set(self.rejected_nodes)
    - self.delta_triaged
)
```

If non-empty and a provider exists, run `challenge_triage` with the full brief and only
`render_node_set(new_ids, service)`. Gate with `gate_triage`, accumulate rejects, and mark
all submitted ids triaged on success. On `JsonContractError`, record the visible failure
and keep nodes. Recompute governance pull only after this pass.

- [ ] **Step 4: Verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_challenge.py tests/test_session.py -q
.venv/bin/ruff check core/runtime tests/test_challenge.py tests/test_session.py
```

- [ ] **Step 5: Commit**

```bash
git add core/runtime/challenge.py core/runtime/session.py \
  tests/test_challenge.py tests/test_session.py
git commit -m "fix: triage new post-challenge nodes"
```

### Task 6: Render challenge from grounded claims

**Files:**
- Create: `prompts/render_challenge.txt`
- Modify: `prompts/challenge_claims.txt`
- Modify: `core/runtime/llm_steps.py`
- Modify: `core/runtime/session.py`
- Modify: `tests/test_llm_steps.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing rendering tests**

Add:

```python
text = render_grounded_challenge(
    provider,
    brief_text="Projet carte.",
    claims=[{"reason": "Le projet dépend de sys-a."}],
)
assert text == "Défi fidèle."
assert "Le projet dépend de sys-a." in provider.calls[0][1]
assert "claim rejeté" not in provider.calls[0][1]
```

Test no-provider/contract-failure fallback:

```text
Points de challenge fondés sur la carte :
- Le projet dépend de sys-a.
```

Test the empty-claims fallback. Add a session test where one claim is grounded and one
rejected; only the grounded reason reaches the rendering call and the resulting statement
then follows the existing fidelity/quarantine path.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
```

- [ ] **Step 3: Implement grounded rendering**

Add `render_grounded_challenge` using `prompts/render_challenge.txt` and JSON key
`challenge_statement`. The prompt forbids introducing any fact outside the supplied
brief and accepted claims.

In `_run_challenge`, continue requiring the legacy `challenge_statement` key for provider
compatibility during this change, but ignore its content. After grounding, call
`render_grounded_challenge` with only `grounded`. Apply `statement_fact_flags` and
`judge_statement_fidelity` to the new text exactly as before.

- [ ] **Step 4: Verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -q
.venv/bin/ruff check core/runtime prompts tests/test_llm_steps.py tests/test_session.py
```

- [ ] **Step 5: Commit**

```bash
git add prompts/render_challenge.txt prompts/challenge_claims.txt \
  core/runtime/llm_steps.py core/runtime/session.py \
  tests/test_llm_steps.py tests/test_session.py
git commit -m "fix: render challenges from grounded claims"
```

### Task 7: Gemini benchmark support and regression verification

**Files:**
- Modify: `scripts/conversation-eval`
- Modify: `scripts/challenge-eval`
- Modify: `tests/test_benchdata.py` or add focused provider-choice tests if extraction is needed

- [ ] **Step 1: Preserve the existing conversation-eval behavior probes**

Before editing in the isolated worktree, apply the existing workspace diff for
`scripts/conversation-eval` so the five-fix probes remain present. Confirm the diff
contains `brief_field_cards` and `behavior_probes`.

- [ ] **Step 2: Add Gemini to both bench CLIs**

Extend provider choices and key mappings:

```python
env_var = {
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "grok": "GROK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}[name]
```

Instantiate `GeminiProvider` for `gemini`; preserve all other branches.

- [ ] **Step 3: Run the complete hermetic verification**

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
git diff --check
```

Expected: ruff clean, all tests pass, no whitespace errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/conversation-eval scripts/challenge-eval tests
git commit -m "test: support Gemini in real-model benches"
```

### Task 8: Matched real Mistral/Gemini simulations

**Files:**
- Modify: `docs/BUILD-ORDER.md`

- [ ] **Step 1: Install the new optional dependency**

```bash
.venv/bin/pip install -e ".[llm]"
```

Expected: `google-genai` imports successfully.

- [ ] **Step 2: Verify Gemini credentials and one JSON call**

Load the project-root `.env` without printing secrets and invoke `GeminiProvider` with a
minimal JSON request. Confirm model `gemini-3.5-flash` returns valid JSON.

- [ ] **Step 3: Run the two matched scenarios with Mistral**

Use the real HTTP app/runtime, `SCOPEGRAPH_LLM_PROVIDER=mistral`, and no
`SCOPEGRAPH_CACHE_DIR`. Use the fixed PM answer script for BNPL and temporary card limits.
For every turn capture:

- question;
- accepted/rejected field cards;
- claim card text and provenance;
- gate rejections;
- final map ids;
- EDB completion and statement flags/issues.

- [ ] **Step 4: Run the same scenarios with Gemini**

Repeat with `SCOPEGRAPH_LLM_PROVIDER=gemini`, `gemini-3.5-flash`, no cache, and exactly
the same user answers and proposal decisions wherever the offered cards are equivalent.

- [ ] **Step 5: Compare manually**

Score each model:

| Metric | Rule |
|---|---|
| question relevance | relevant questions / total questions |
| contradictory premise | count questions contradicting explicit brief/exclusion |
| map pollution | unrelated final nodes after delta triage |
| auto grounding | rejected claims / generated syntactically valid claims |
| manual claim rejection | offered claims rejected after provenance review |
| statement fidelity | unsupported/date-direction issues |
| EDB completion | accepted askable sections filled |

- [ ] **Step 6: Update the status source**

Add the dated comparison and recommendation to `docs/BUILD-ORDER.md`. Do not duplicate
status elsewhere.

- [ ] **Step 7: Final verification**

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
git diff --check
git status --short --branch
```

- [ ] **Step 8: Commit the measured result**

```bash
git add docs/BUILD-ORDER.md
git commit -m "docs: record Mistral and Gemini real-user comparison"
```
