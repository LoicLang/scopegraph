---
summary: implementation plan for W3 — core/llm providers, EDB template, conversation orchestrator, two-phase challenge with pull, three-pane UI, challenge bench
read_when:
  - executing W3 task by task
  - resuming a partially executed w3-llm-edb branch
---

# W3 — LLM Layer + EDB Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the W3 LLM layer per spec `docs/specs/2026-06-12-week3-llm-challenge-design.md`: official-SDK providers behind a Protocol, the EDB template as conversation engine, the fluid graph-woven interview, the two-phase challenge with deterministic governance pull, the three-pane UI, and the end-to-end challenge bench.

**Architecture:** Everything LLM-facing crosses `LLMProvider.complete_json` (Mock in CI — a real call in a test is a bug). The runtime stays the deterministic authority: gates A/B, the governance pull, the EDB state machine, the candidate pool, and the ledger are pure Python, hermetically tested. The LLM only proposes; `provider=None` degrades to W2-template behavior everywhere (the permanent fallback path IS the no-provider path).

**Tech Stack:** Python 3.12, Pydantic v2, `mistralai` + `openai` SDKs (lazy, new `llm` extra), FastAPI + Alpine.js/Cytoscape (existing page), pytest hermetic.

**Branch:** `w3-llm-edb` off `main`.

**File map:**
- Create: `core/llm/__init__.py` · `core/llm/provider.py` (Protocol + MockProvider) · `core/llm/json_contract.py` (one schema-reminder retry) · `core/llm/prompts.py` (loader) · `core/llm/mistral.py` · `core/llm/deepseek.py` · `core/llm/factory.py` (env resolution)
- Create: `prompts/enrich_brief.txt` · `prompts/extract_fields.txt` · `prompts/pick_question.txt` · `prompts/challenge_triage.txt` · `prompts/challenge_claims.txt`
- Create: `core/dossier/__init__.py` · `core/dossier/template.py` (EDB_TEMPLATE_V1 + EdbState)
- Create: `core/runtime/ledger.py` · `core/runtime/pool.py` (mixed candidate pool) · `core/runtime/challenge.py` (pull + gates + two-message flow) · `core/runtime/llm_steps.py` (enrichment/extraction/question steps)
- Modify: `core/runtime/brief.py` (enrichments + query_text) · `core/runtime/session.py` (provider + EDB + orchestrator wiring) · `core/runtime/triggers.py` (pivot candidate collection) · `core/runtime/questions.py` (gap-question templates)
- Create: `core/benchdata/__init__.py` · `core/benchdata/scenarios.py` (single ground-truth source) · `scripts/challenge-eval`
- Modify: `scripts/retrieval-eval` (import scenarios from core/benchdata) · `web/app.py` · `web/static/index.html` · `pyproject.toml` (`llm` extra) · docs at the end
- Tests: `tests/test_llm.py` · `tests/test_dossier.py` · `tests/test_ledger.py` · `tests/test_pool.py` · `tests/test_llm_steps.py` · `tests/test_challenge.py` · extend `tests/test_session.py`, `tests/test_web.py`

**Conventions for every task:** run commands with `.venv/bin/python -m pytest` and `.venv/bin/ruff check .`. Stay on branch `w3-llm-edb` (verify `git branch --show-current` before each commit; NEVER `git checkout <sha>` — a detached HEAD orphaned a commit in lot 0bis). All LLM-visible text and prompt files are French; code/comments English (hard rule 6).

---

### Task 0: Branch

- [ ] **Step 1:**

```bash
git checkout -b w3-llm-edb main
```

### Task 1: `core/llm` — Protocol, MockProvider, JSON contract, prompt loader

**Files:**
- Create: `core/llm/__init__.py`, `core/llm/provider.py`, `core/llm/json_contract.py`, `core/llm/prompts.py`
- Create: `prompts/enrich_brief.txt` (others arrive with their consuming tasks)
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_llm.py`:

```python
"""LLMProvider Protocol, MockProvider, JSON contract retry, prompt loader."""

import pytest

from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import MockProvider


def test_mock_provider_returns_scripted_responses_in_order():
    mock = MockProvider([{"a": 1}, {"b": 2}])
    assert mock.complete_json("sys", "user one") == {"a": 1}
    assert mock.complete_json("sys", "user two") == {"b": 2}
    assert mock.calls == [("sys", "user one"), ("sys", "user two")]


def test_mock_provider_exhausted_raises():
    mock = MockProvider([])
    with pytest.raises(IndexError):
        mock.complete_json("s", "u")


def test_retry_passes_through_valid_response():
    mock = MockProvider([{"verdicts": []}])
    out = complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))
    assert out == {"verdicts": []}
    assert len(mock.calls) == 1


def test_retry_reprompts_once_with_schema_then_succeeds():
    mock = MockProvider([{"wrong": True}, {"verdicts": []}])
    out = complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))
    assert out == {"verdicts": []}
    assert len(mock.calls) == 2
    assert "verdicts" in mock.calls[1][1]  # the retry message restates the schema keys


def test_retry_fails_clean_after_second_miss():
    mock = MockProvider([{"wrong": True}, {"still": "wrong"}])
    with pytest.raises(JsonContractError, match="réponse du modèle invalide"):
        complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))


def test_load_prompt_reads_french_template():
    text = load_prompt("enrich_brief")
    assert "synonymes" in text.lower()


def test_load_prompt_unknown_fails_loud():
    with pytest.raises(FileNotFoundError):
        load_prompt("does-not-exist")
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_llm.py -v` → ImportError on `core.llm`.

- [ ] **Step 3: Implement.**

`core/llm/__init__.py`: empty (namespace).

`core/llm/provider.py`:

```python
"""LLMProvider Protocol and the scripted MockProvider (hermetic tests, no network)."""

from typing import Protocol


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class MockProvider:
    """FIFO queue of scripted dict responses; records every call."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self._responses.pop(0)
```

`core/llm/json_contract.py`:

```python
"""Content-level JSON contract: one schema-reminder retry, then a clean French error.

Transport retries (429, network) belong to the SDKs; THIS layer only handles a
syntactically valid but schema-miss response (MVP spec §6).
"""

from core.llm.provider import LLMProvider


class JsonContractError(RuntimeError):
    pass


def complete_with_retry(
    provider: LLMProvider, system: str, user: str, *, required_keys: tuple[str, ...]
) -> dict:
    out = provider.complete_json(system, user)
    if all(key in out for key in required_keys):
        return out
    reminder = (
        f"{user}\n\nTa réponse précédente ne respectait pas le schéma attendu. "
        f"Réponds UNIQUEMENT avec un objet JSON contenant les clés : "
        f"{', '.join(required_keys)}."
    )
    out = provider.complete_json(system, reminder)
    if all(key in out for key in required_keys):
        return out
    raise JsonContractError(
        "réponse du modèle invalide après relance — réessayez ou changez de provider"
    )
```

`core/llm/prompts.py`:

```python
"""Prompt templates live in prompts/*.txt (doctrine: never inline in Python)."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"unknown prompt: {path}")
    return path.read_text(encoding="utf-8")
```

`prompts/enrich_brief.txt` (French — the model's output language):

```text
Tu assistes un outil de cadrage de projets bancaires. À partir du brief ci-dessous,
propose au plus 4 ajouts de vocabulaire qui aideraient une recherche sémantique dans
le référentiel du SI : synonymes métier, objets métier sous-entendus, termes internes
probables. N'invente aucun fait, ne reformule pas le besoin — uniquement du
vocabulaire. Réponds en JSON : {"additions": [{"text": "...", "kind": "synonym"}]}
avec kind ∈ {"synonym", "business_object"}.
```

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_llm.py -v` → 7 PASS. `.venv/bin/ruff check core/llm/ tests/test_llm.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add core/llm/ prompts/ tests/test_llm.py
git commit -m "feat: core/llm — Protocol, MockProvider, JSON-contract retry, prompt loader"
```

### Task 2: Mistral & DeepSeek providers + factory + `llm` extra

**Files:**
- Create: `core/llm/mistral.py`, `core/llm/deepseek.py`, `core/llm/factory.py`
- Modify: `pyproject.toml` (add `llm` extra)
- Test: extend `tests/test_llm.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_llm.py`:

```python
def test_importing_provider_modules_does_not_import_sdks():
    import sys

    import core.llm.deepseek  # noqa: F401
    import core.llm.mistral  # noqa: F401

    assert "mistralai" not in sys.modules
    assert "openai" not in sys.modules


def test_mistral_missing_sdk_raises_clear_error(monkeypatch):
    import sys

    from core.llm.mistral import MistralProvider

    monkeypatch.setitem(sys.modules, "mistralai", None)
    with pytest.raises(RuntimeError, match="mistralai"):
        MistralProvider(api_key="k")


def test_deepseek_calls_openai_compatible_endpoint(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = types.SimpleNamespace(content='{"ok": true}')
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class _Client:
        def __init__(self, api_key, base_url):
            captured["base_url"] = base_url
            self.chat = types.SimpleNamespace(completions=_Completions())

    fake = types.ModuleType("openai")
    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)

    from core.llm.deepseek import DeepSeekProvider

    out = DeepSeekProvider(api_key="k").complete_json("sys", "user")
    assert out == {"ok": True}
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": "sys"}


def test_factory_resolves_provider_from_env(monkeypatch):
    from core.llm.factory import make_provider

    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "mock")
    assert type(make_provider()).__name__ == "MockProvider"
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "none")
    assert make_provider() is None
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="nope"):
        make_provider()
```

- [ ] **Step 2: Verify failure** — `.venv/bin/python -m pytest tests/test_llm.py -v` → ImportError.

- [ ] **Step 3: Implement.**

`core/llm/mistral.py`:

```python
"""Mistral provider (official SDK, lazy import — demo default)."""

import json


class MistralProvider:
    def __init__(self, api_key: str, model: str = "mistral-small-latest") -> None:
        self.model = model
        try:
            from mistralai import Mistral
        except ImportError as exc:
            raise RuntimeError(
                "mistralai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = Mistral(api_key=api_key)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.chat.complete(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)
```

`core/llm/deepseek.py`:

```python
"""DeepSeek provider via the openai SDK (DeepSeek's documented client) — dev/bench."""

import json

_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.model = model
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)
```

`core/llm/factory.py`:

```python
"""Provider resolution from env (SCOPEGRAPH_LLM_PROVIDER: mistral|deepseek|mock|none)."""

import os

from core.llm.provider import LLMProvider, MockProvider


def make_provider() -> LLMProvider | None:
    name = os.environ.get("SCOPEGRAPH_LLM_PROVIDER", "none").lower()
    if name == "none":
        return None  # template-only mode: every LLM step falls back deterministically
    if name == "mock":
        return MockProvider([])
    if name == "mistral":
        from core.llm.mistral import MistralProvider

        return MistralProvider(api_key=os.environ["MISTRAL_API_KEY"])
    if name == "deepseek":
        from core.llm.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
    raise ValueError(f"unknown SCOPEGRAPH_LLM_PROVIDER: {name}")
```

`pyproject.toml`: in `[project.optional-dependencies]`, add alongside `embeddings`:

```toml
llm = [
    "mistralai>=1.0",
    "openai>=1.40",
]
```

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_llm.py -v` → all PASS; `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
git add core/llm/ pyproject.toml tests/test_llm.py
git commit -m "feat: Mistral + DeepSeek providers (official SDKs, lazy), env factory, llm extra"
```

### Task 3: EDB template — `core/dossier/template.py`

**Files:**
- Create: `core/dossier/__init__.py`, `core/dossier/template.py`
- Test: `tests/test_dossier.py`

- [ ] **Step 1: Failing tests** — create `tests/test_dossier.py`:

```python
"""EDB template v1: sections, owners, entry sources, statuses, completeness."""

import pytest

from core.dossier.template import (
    CLAIM_SECTIONS,
    EDB_TEMPLATE_V1,
    EdbEntry,
    EdbState,
)


def test_template_has_the_12_frozen_sections_in_order():
    ids = [section.id for section in EDB_TEMPLATE_V1]
    assert ids == [
        "contexte", "besoin", "utilisateurs", "objectifs", "perimetre", "exigences",
        "dependances", "contraintes", "risques", "jalons", "challenge", "carte",
    ]
    assert all(section.title_fr and section.prompt_hint_fr for section in EDB_TEMPLATE_V1)


def test_claim_sections_enum():
    assert CLAIM_SECTIONS == ("dependances", "contraintes", "risques", "perimetre", "jalons")


def test_state_starts_empty_and_fills():
    state = EdbState.new()
    assert state.status("besoin") == "empty"
    state.add_entry("besoin", EdbEntry(source="user", text="Un programme de cash-back."))
    assert state.status("besoin") == "filled"
    assert state.sections["besoin"][0].source == "user"


def test_unknown_section_fails_loud():
    state = EdbState.new()
    with pytest.raises(KeyError):
        state.add_entry("budget", EdbEntry(source="user", text="x"))


def test_completeness_lists_missing_user_facing_sections():
    state = EdbState.new()
    state.add_entry("besoin", EdbEntry(source="user", text="t"))
    missing = state.missing_sections()
    assert "besoin" not in missing
    assert "objectifs" in missing
    assert "carte" not in missing  # runtime-owned, never asked
    assert "challenge" not in missing  # llm-owned, never asked


def test_state_round_trips_through_dict():
    state = EdbState.new()
    state.add_entry("risques", EdbEntry(source="claim:c1", text="r", node_refs=["risk-x"]))
    clone = EdbState.from_dict(state.to_dict())
    assert clone.sections["risques"][0].node_refs == ["risk-x"]
    assert clone.status("risques") == "filled"
```

- [ ] **Step 2: Verify failure** — `.venv/bin/python -m pytest tests/test_dossier.py -v` → ImportError.

- [ ] **Step 3: Implement** `core/dossier/template.py`:

```python
"""EDB template v1 — the conversation engine's state (W3 spec §2).

The 12 sections of the project's first framing document (standard French
expression-de-besoins + note-de-cadrage merge). The runtime owns this state;
the LLM only proposes entries that cross a gate and the user ledger.
"""

from dataclasses import dataclass, field
from typing import Literal

Owner = Literal["user", "graph", "mixed", "llm", "runtime"]

# Sections a challenge claim may write into (W3 spec §5 gate B).
CLAIM_SECTIONS = ("dependances", "contraintes", "risques", "perimetre", "jalons")


@dataclass(frozen=True)
class EdbSectionSpec:
    id: str
    title_fr: str
    owner: Owner
    prompt_hint_fr: str  # the deterministic fallback question for gap candidates


EDB_TEMPLATE_V1: tuple[EdbSectionSpec, ...] = (
    EdbSectionSpec("contexte", "Contexte & raison d'être", "mixed",
                   "Dans quel contexte ce besoin apparaît-il (origine, déclencheur) ?"),
    EdbSectionSpec("besoin", "Expression du besoin", "user",
                   "Quel problème métier ce projet doit-il résoudre, en une phrase ?"),
    EdbSectionSpec("utilisateurs", "Utilisateurs & parties prenantes", "mixed",
                   "Qui utilisera le résultat, et qui sponsorise le projet ?"),
    EdbSectionSpec("objectifs", "Objectifs & critères de réussite", "user",
                   "À quelles conditions ce projet sera-t-il un succès ?"),
    EdbSectionSpec("perimetre", "Périmètre in / hors périmètre", "mixed",
                   "Qu'est-ce qui est explicitement dans — et hors — du périmètre ?"),
    EdbSectionSpec("exigences", "Exigences fonctionnelles et non-fonctionnelles", "mixed",
                   "Quelles exigences fortes (fonctionnelles ou non) faut-il poser dès maintenant ?"),
    EdbSectionSpec("dependances", "Dépendances & systèmes impactés", "graph",
                   "Des dépendances connues à signaler ?"),
    EdbSectionSpec("contraintes", "Contraintes héritées", "graph",
                   "Des contraintes (réglementaires, gels, standards) à signaler ?"),
    EdbSectionSpec("risques", "Risques initiaux", "mixed",
                   "Quels risques voyez-vous à ce stade ?"),
    EdbSectionSpec("jalons", "Jalons / échéance cible", "mixed",
                   "Y a-t-il une échéance cible ou des jalons imposés ?"),
    EdbSectionSpec("challenge", "Challenge & arbitrages ouverts", "llm",
                   ""),
    EdbSectionSpec("carte", "Context Map", "runtime", ""),
)

_SPEC_BY_ID = {section.id: section for section in EDB_TEMPLATE_V1}
# Sections the conversation may ask about (never the llm/runtime-owned ones).
_ASKABLE = tuple(s.id for s in EDB_TEMPLATE_V1 if s.owner in ("user", "mixed"))


@dataclass
class EdbEntry:
    source: str  # "user" | "claim:<id>" | "llm"
    text: str
    node_refs: list[str] = field(default_factory=list)


class EdbState:
    """Mutable per-session EDB content; statuses derive from entries."""

    def __init__(self, sections: dict[str, list[EdbEntry]]) -> None:
        self.sections = sections

    @classmethod
    def new(cls) -> "EdbState":
        return cls({section.id: [] for section in EDB_TEMPLATE_V1})

    def add_entry(self, section_id: str, entry: EdbEntry) -> None:
        if section_id not in self.sections:
            raise KeyError(f"unknown EDB section: {section_id}")
        self.sections[section_id].append(entry)

    def status(self, section_id: str) -> str:
        return "filled" if self.sections[section_id] else "empty"

    def missing_sections(self) -> list[str]:
        """Askable sections still empty, in template order (the gap candidates)."""
        return [sid for sid in _ASKABLE if not self.sections[sid]]

    def to_dict(self) -> dict:
        return {
            sid: [
                {"source": e.source, "text": e.text, "node_refs": e.node_refs}
                for e in entries
            ]
            for sid, entries in self.sections.items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EdbState":
        state = cls.new()
        for sid, entries in data.items():
            for e in entries:
                state.add_entry(sid, EdbEntry(e["source"], e["text"], list(e["node_refs"])))
        return state


def section_spec(section_id: str) -> EdbSectionSpec:
    return _SPEC_BY_ID[section_id]
```

Note: `status()` is binary in v1 (`empty|filled`); the spec's `partial` arrives when
W4's rendering needs it — YAGNI now, the missing-list only cares about empty.

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_dossier.py -v` → 6 PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/dossier/ tests/test_dossier.py
git commit -m "feat: EDB template v1 — 12 frozen sections, entry sources, completeness"
```

### Task 4: Ledger — `core/runtime/ledger.py`

**Files:**
- Create: `core/runtime/ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Failing tests** — create `tests/test_ledger.py`:

```python
"""Propose/validate ledger: pending cards the user accepts, edits, or rejects."""

import pytest

from core.runtime.ledger import Ledger, Proposal


def _claim(node_ids=("sys-a",), section="dependances"):
    return Proposal.claim(
        kind="depends_on", node_ids=list(node_ids), target_section=section,
        reason="dépend du moteur",
    )


def test_proposals_get_sequential_ids_and_pending_status():
    ledger = Ledger()
    pid = ledger.add(_claim())
    assert pid == "p1"
    assert ledger.get(pid).status == "pending"
    assert ledger.add(_claim()) == "p2"


def test_accept_with_optional_edit():
    ledger = Ledger()
    pid = ledger.add(Proposal.field(section_id="objectifs", text="Réduire le délai"))
    accepted = ledger.accept(pid, edited_text="Réduire le délai à 2 jours")
    assert accepted.status == "accepted"
    assert accepted.text == "Réduire le délai à 2 jours"


def test_reject_keeps_the_proposal_visible():
    ledger = Ledger()
    pid = ledger.add(_claim())
    ledger.reject(pid)
    assert ledger.get(pid).status == "rejected"
    assert [p.id for p in ledger.pending()] == []


def test_double_decision_fails_loud():
    ledger = Ledger()
    pid = ledger.add(_claim())
    ledger.accept(pid)
    with pytest.raises(ValueError, match="already decided"):
        ledger.reject(pid)


def test_round_trip():
    ledger = Ledger()
    ledger.add(_claim())
    clone = Ledger.from_dict(ledger.to_dict())
    assert clone.get("p1").kind == "claim"
    assert clone.get("p1").payload["target_section"] == "dependances"
```

- [ ] **Step 2: Verify failure** — `.venv/bin/python -m pytest tests/test_ledger.py -v` → ImportError.

- [ ] **Step 3: Implement** `core/runtime/ledger.py`:

```python
"""Propose/validate/apply ledger (MVP spec §3): the LLM proposes, the USER decides.

Holds claims (challenge output) and extracted EDB field entries as pending cards.
Application (writing accepted entries into the EDB) is the session's job — the
ledger only tracks consent. Serialized with the session.
"""

from dataclasses import dataclass, field


@dataclass
class Proposal:
    id: str
    kind: str  # "claim" | "field"
    text: str  # FR display text (claim reason or field entry text)
    payload: dict  # kind-specific data, applied on accept
    status: str = "pending"  # pending | accepted | rejected

    @classmethod
    def claim(cls, *, kind: str, node_ids: list[str], target_section: str, reason: str):
        return cls(id="", kind="claim", text=reason, payload={
            "claim_kind": kind, "node_ids": node_ids, "target_section": target_section,
        })

    @classmethod
    def field(cls, *, section_id: str, text: str, node_refs: list[str] | None = None):
        return cls(id="", kind="field", text=text, payload={
            "section_id": section_id, "node_refs": node_refs or [],
        })


@dataclass
class Ledger:
    proposals: dict[str, Proposal] = field(default_factory=dict)
    _counter: int = 0

    def add(self, proposal: Proposal) -> str:
        self._counter += 1
        proposal.id = f"p{self._counter}"
        self.proposals[proposal.id] = proposal
        return proposal.id

    def get(self, pid: str) -> Proposal:
        return self.proposals[pid]

    def pending(self) -> list[Proposal]:
        return [p for p in self.proposals.values() if p.status == "pending"]

    def _decide(self, pid: str, status: str) -> Proposal:
        proposal = self.proposals[pid]
        if proposal.status != "pending":
            raise ValueError(f"proposal {pid} already decided: {proposal.status}")
        proposal.status = status
        return proposal

    def accept(self, pid: str, edited_text: str | None = None) -> Proposal:
        proposal = self._decide(pid, "accepted")
        if edited_text is not None:
            proposal.text = edited_text
        return proposal

    def reject(self, pid: str) -> Proposal:
        return self._decide(pid, "rejected")

    def to_dict(self) -> dict:
        return {
            "counter": self._counter,
            "proposals": [
                {"id": p.id, "kind": p.kind, "text": p.text,
                 "payload": p.payload, "status": p.status}
                for p in self.proposals.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        ledger = cls()
        ledger._counter = data["counter"]
        for raw in data["proposals"]:
            ledger.proposals[raw["id"]] = Proposal(**raw)
        return ledger
```

- [ ] **Step 4: Run** — 5 PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/ledger.py tests/test_ledger.py
git commit -m "feat: propose/validate ledger — pending cards, accept-with-edit, round-trip"
```

### Task 5: Mixed candidate pool — `core/runtime/pool.py` + pivot collection

**Files:**
- Create: `core/runtime/pool.py`
- Modify: `core/runtime/triggers.py` (add `collect_pivot_candidates`)
- Modify: `core/runtime/questions.py` (add `gap_question`)
- Test: `tests/test_pool.py`

- [ ] **Step 1: Failing tests** — create `tests/test_pool.py`:

```python
"""One mixed pool per turn: graph-ambiguity candidates (priority) + EDB gaps."""

from core.dossier.template import EdbEntry, EdbState
from core.retrieval.retriever import RetrievalResult, ScoredNode
from core.runtime.brief import ProjectBrief
from core.runtime.pool import build_pool
from core.runtime.questions import gap_question


def _result(anchors=(), expanded=(), domain_scores=None):
    return RetrievalResult(
        anchors=list(anchors), expanded=list(expanded),
        domain_scores=domain_scores or {}, derived_domains=[],
    )


def _anchor(node_id="sys-a", score=0.9):
    return ScoredNode(node_id=node_id, score=score)


def _pivot(node_id, domain, score=0.5):
    return ScoredNode(node_id=node_id, score=score, domains=(domain,),
                      semantic_sim=0.0, anchor_id="sys-a", path=("e",),
                      expansion_only=True)


def test_graph_candidates_outrank_edb_gaps():
    brief = ProjectBrief(description="d")
    edb = EdbState.new()
    result = _result(anchors=[_anchor()],
                     expanded=[_pivot("sys-t", "tpe-acceptation")])
    pool = build_pool(result, brief, set(), edb)
    assert pool[0].kind == "pivot"
    assert any(c.kind == "edb_gap" for c in pool)


def test_all_qualifying_pivots_are_collected_not_just_the_first():
    brief = ProjectBrief(description="d")
    result = _result(anchors=[_anchor()], expanded=[
        _pivot("sys-t", "tpe-acceptation"), _pivot("sys-m", "monetique"),
    ])
    pool = build_pool(result, brief, set(), EdbState.new())
    pivot_domains = [c.domain for c in pool if c.kind == "pivot"]
    assert set(pivot_domains) == {"tpe-acceptation", "monetique"}


def test_asked_log_and_filled_sections_drop_candidates():
    brief = ProjectBrief(description="d")
    edb = EdbState.new()
    edb.add_entry("besoin", EdbEntry(source="user", text="t"))
    result = _result(anchors=[_anchor()],
                     expanded=[_pivot("sys-t", "tpe-acceptation")])
    asked = {"pivot:tpe-acceptation", "gap:objectifs"}
    pool = build_pool(result, brief, asked, edb)
    assert all(c.key != "pivot:tpe-acceptation" for c in pool)
    assert all(c.key != "gap:objectifs" for c in pool)
    assert all(c.key != "gap:besoin" for c in pool)  # filled section → no gap


def test_gap_question_uses_the_template_hint():
    assert "succès" in gap_question("objectifs")
```

- [ ] **Step 2: Verify failure** — ImportError.

- [ ] **Step 3: Implement.**

Append to `core/runtime/triggers.py` (existing `detect_trigger` is untouched — it
remains the T1/T2 detection and the no-provider fallback path):

```python
def collect_pivot_candidates(
    result: RetrievalResult, brief: ProjectBrief, asked: set[str]
) -> list[PivotTrigger]:
    """ALL qualifying pivots (not just the first) — the W3 pool feeds the LLM choice.

    Same qualification rules as detect_trigger's T3 branch: expansion-only node,
    no known domain, not already asked. One candidate per unknown domain (the
    best-scored node represents it, list order = expansion score order).
    """
    known = set(brief.domains) | set(result.derived_domains) | set(brief.excluded_domains)
    candidates: list[PivotTrigger] = []
    seen_domains: set[str] = set()
    for scored in result.expanded:  # already sorted best-first
        if not scored.expansion_only or set(scored.domains) & known:
            continue
        for domain in scored.domains:
            trigger = PivotTrigger(domain=domain, node_id=scored.node_id)
            if trigger.key in asked or domain in seen_domains:
                continue
            seen_domains.add(domain)
            candidates.append(trigger)
    return candidates
```

Append to `core/runtime/questions.py`:

```python
from core.dossier.template import section_spec


def gap_question(section_id: str) -> str:
    """Deterministic fallback question for an EDB gap (the section's hint)."""
    return section_spec(section_id).prompt_hint_fr
```

Create `core/runtime/pool.py`:

```python
"""The per-turn candidate pool: graph ambiguity first, then EDB gaps (W3 spec §4.4).

Pure assembly — the runtime decides WHAT may be asked; the LLM (or the template
fallback) only picks within this pool and phrases the question.
"""

from dataclasses import dataclass

from core.dossier.template import EdbState
from core.retrieval.retriever import RetrievalResult
from core.runtime.brief import ProjectBrief
from core.runtime.triggers import (
    DomainTieTrigger,
    PivotTrigger,
    Trigger,
    WeakBriefTrigger,
    collect_pivot_candidates,
    detect_trigger,
)


@dataclass(frozen=True)
class Candidate:
    kind: str  # "weak" | "tie" | "pivot" | "edb_gap"
    key: str  # asked-log key
    domain: str = ""  # pivot/tie context
    node_id: str = ""  # pivot context
    section_id: str = ""  # edb_gap context
    trigger: Trigger | None = None  # the W2 trigger object for fallback rendering


def build_pool(
    result: RetrievalResult, brief: ProjectBrief, asked: set[str], edb: EdbState
) -> list[Candidate]:
    pool: list[Candidate] = []
    primary = detect_trigger(result, brief, asked)
    if isinstance(primary, WeakBriefTrigger):
        pool.append(Candidate(kind="weak", key=primary.key, trigger=primary))
    elif isinstance(primary, DomainTieTrigger):
        pool.append(Candidate(kind="tie", key=primary.key,
                              domain=f"{primary.domain_a}|{primary.domain_b}",
                              trigger=primary))
    for pivot in collect_pivot_candidates(result, brief, asked):
        pool.append(Candidate(kind="pivot", key=pivot.key, domain=pivot.domain,
                              node_id=pivot.node_id, trigger=pivot))
    for section_id in edb.missing_sections():
        key = f"gap:{section_id}"
        if key not in asked:
            pool.append(Candidate(kind="edb_gap", key=key, section_id=section_id))
    return pool
```

Note: when `detect_trigger` returns a `PivotTrigger`, it is already covered by
`collect_pivot_candidates` — only weak/tie need the primary slot.

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_pool.py tests/test_triggers.py -v` → all PASS (existing trigger tests untouched); ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/pool.py core/runtime/triggers.py core/runtime/questions.py tests/test_pool.py
git commit -m "feat: mixed candidate pool — all pivots collected, EDB gaps, asked-log unified"
```

### Task 6: LLM steps — enrichment, extraction, question pick (`core/runtime/llm_steps.py`)

**Files:**
- Create: `core/runtime/llm_steps.py`
- Create: `prompts/extract_fields.txt`, `prompts/pick_question.txt`
- Modify: `core/runtime/brief.py` (enrichments + query_text)
- Test: `tests/test_llm_steps.py`

- [ ] **Step 1: Failing tests** — create `tests/test_llm_steps.py`:

```python
"""The three per-turn LLM steps, each with a deterministic no-provider fallback."""

from core.dossier.template import EdbState
from core.llm.provider import MockProvider
from core.runtime.brief import ProjectBrief
from core.runtime.llm_steps import enrich_brief, extract_fields, pick_question
from core.runtime.pool import Candidate
from core.runtime.triggers import WeakBriefTrigger


def test_brief_query_text_appends_enrichments_not_user_text():
    brief = ProjectBrief(description="cash-back commerçants")
    brief.enrichments.append("programme de fidélité")
    assert "fidélité" in brief.query_text()
    assert "fidélité" not in brief.text()


def test_enrich_brief_caps_at_4_and_records(monkeypatch):
    brief = ProjectBrief(description="d")
    mock = MockProvider([{"additions": [
        {"text": f"t{i}", "kind": "synonym"} for i in range(6)
    ]}])
    enrich_brief(mock, brief)
    assert brief.enrichments == ["t0", "t1", "t2", "t3"]


def test_enrich_brief_none_provider_is_a_noop():
    brief = ProjectBrief(description="d")
    enrich_brief(None, brief)
    assert brief.enrichments == []


def test_enrich_brief_swallows_contract_failure(monkeypatch):
    brief = ProjectBrief(description="d")
    mock = MockProvider([{"bad": 1}, {"still": 2}])  # fails after retry
    enrich_brief(mock, brief)  # must NOT raise (never blocking)
    assert brief.enrichments == []


def test_extract_fields_gates_unknown_sections():
    mock = MockProvider([{"entries": [
        {"section_id": "objectifs", "text": "réduire le délai"},
        {"section_id": "budget", "text": "x"},  # unknown → dropped
    ]}])
    entries, dropped = extract_fields(mock, "réponse libre", EdbState.new())
    assert [e["section_id"] for e in entries] == ["objectifs"]
    assert dropped == ["budget"]


def test_pick_question_gated_to_pool_with_template_fallback():
    weak = Candidate(kind="weak", key="weak", trigger=WeakBriefTrigger())
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    # LLM picks an id outside the pool → fallback to the first candidate's template
    mock = MockProvider([{"candidate_key": "gap:nope", "question": "Q?"}])
    candidate, question = pick_question(mock, [weak, gap], service=None)
    assert candidate.key == "weak"
    assert "préciser" in question  # W2 WEAK_QUESTION template


def test_pick_question_accepts_a_valid_choice():
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    mock = MockProvider([{"candidate_key": "gap:objectifs",
                          "question": "Quel succès visez-vous, sachant le gel T3 ?"}])
    candidate, question = pick_question(mock, [gap], service=None)
    assert candidate.section_id == "objectifs"
    assert question.startswith("Quel succès")


def test_pick_question_none_provider_uses_templates():
    gap = Candidate(kind="edb_gap", key="gap:objectifs", section_id="objectifs")
    candidate, question = pick_question(None, [gap], service=None)
    assert candidate.key == "gap:objectifs"
    assert "succès" in question
```

- [ ] **Step 2: Verify failure** — ImportError.

- [ ] **Step 3: Implement.**

`core/runtime/brief.py` — add to `ProjectBrief`:

```python
    enrichments: list[str] = Field(default_factory=list)  # AI-added query vocabulary

    def query_text(self) -> str:
        """Retrieval query = the user's words + revocable AI vocabulary (W3 spec §4.1)."""
        if not self.enrichments:
            return self.text()
        return self.text() + "\n" + " ".join(self.enrichments)
```

`prompts/extract_fields.txt`:

```text
Tu assistes un outil de cadrage de projets bancaires qui remplit une expression de
besoin (EDB) pendant la conversation. Voici la dernière réponse libre de
l'utilisateur. Extrais-en les éléments qui remplissent des sections de l'EDB, sans
rien inventer ni reformuler au-delà du nécessaire. Sections autorisées :
{sections}. Réponds en JSON :
{"entries": [{"section_id": "...", "text": "...", "node_refs": []}]}
Si rien n'est extractible, renvoie {"entries": []}.
```

`prompts/pick_question.txt`:

```text
Tu mènes un entretien de cadrage de projet bancaire. Tu connais bien le SI de
l'entreprise. Voici les questions candidates de ce tour, chacune avec son contexte
(ambiguïté détectée dans le graphe du SI, ou section manquante de l'EDB). Choisis
LA candidate la plus utile maintenant et formule UNE question naturelle en
français qui tisse le contexte du SI dans la question (jamais de jargon technique
brut, jamais de slug). L'utilisateur doit avoir l'impression de parler à quelqu'un
qui connaît la boîte. Réponds en JSON :
{"candidate_key": "...", "question": "..."}
```

`core/runtime/llm_steps.py`:

```python
"""Per-turn LLM steps (W3 spec §4). Every step degrades deterministically:
no provider, or a failed JSON contract, never blocks a turn (hard rule: the
templates and the gates are the product's floor, the LLM is the polish)."""

from core.dossier.template import EdbState
from core.graph.service import GraphService
from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import LLMProvider
from core.runtime.brief import ProjectBrief
from core.runtime.pool import Candidate
from core.runtime.questions import gap_question, render_question

MAX_ENRICHMENTS_PER_TURN = 4


def enrich_brief(provider: LLMProvider | None, brief: ProjectBrief) -> None:
    """Adds ≤4 revocable vocabulary chips to the retrieval query (spec §4.1)."""
    if provider is None:
        return
    try:
        out = complete_with_retry(
            provider, load_prompt("enrich_brief"), brief.text(),
            required_keys=("additions",),
        )
    except JsonContractError:
        return  # enrichment is sugar — never blocking, the UI shows a discreet notice
    for addition in out["additions"][:MAX_ENRICHMENTS_PER_TURN]:
        text = str(addition.get("text", "")).strip()
        if text and text not in brief.enrichments:
            brief.enrichments.append(text)


def extract_fields(
    provider: LLMProvider | None, answer: str, edb: EdbState
) -> tuple[list[dict], list[str]]:
    """Proposes EDB entries from a free answer; returns (gated entries, dropped ids)."""
    if provider is None:
        return [], []
    allowed = set(edb.sections) 
    system = load_prompt("extract_fields").replace("{sections}", ", ".join(sorted(allowed)))
    try:
        out = complete_with_retry(provider, system, answer, required_keys=("entries",))
    except JsonContractError:
        return [], []
    entries, dropped = [], []
    for raw in out["entries"]:
        section_id = raw.get("section_id", "")
        if section_id in allowed and raw.get("text"):
            entries.append({"section_id": section_id, "text": raw["text"],
                            "node_refs": list(raw.get("node_refs", []))})
        else:
            dropped.append(section_id)
    return entries, dropped


def _template_question(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        return gap_question(candidate.section_id)
    return render_question(candidate.trigger, service)


def _candidate_context(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        return f"[{candidate.key}] section EDB manquante — piste : {gap_question(candidate.section_id)}"
    return f"[{candidate.key}] ambiguïté graphe ({candidate.kind}) — gabarit : {_template_question(candidate, service)}"


def pick_question(
    provider: LLMProvider | None,
    pool: list[Candidate],
    service: GraphService | None,
) -> tuple[Candidate, str]:
    """LLM choice gated to the pool; templates are the permanent fallback (spec §4.4)."""
    assert pool, "pick_question requires a non-empty pool"
    fallback = (pool[0], _template_question(pool[0], service))
    if provider is None:
        return fallback
    user = "\n".join(_candidate_context(c, service) for c in pool)
    try:
        out = complete_with_retry(
            provider, load_prompt("pick_question"), user,
            required_keys=("candidate_key", "question"),
        )
    except JsonContractError:
        return fallback
    by_key = {c.key: c for c in pool}
    candidate = by_key.get(str(out["candidate_key"]))
    question = str(out["question"]).strip()
    if candidate is None or not question:
        return fallback  # gated: an id outside the pool is an LLM error, not a crash
    return candidate, question
```

Note for the implementer: `render_question(trigger, service)` is called with
`service=None` only in tests where the candidate is weak/tie (templates that don't
touch the service for weak; tie uses domains only). The pivot template DOES read the
service — tests passing `service=None` must only use weak/tie/gap candidates, as the
ones above do.

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_llm_steps.py tests/test_session.py -v` → llm_steps PASS, session untouched PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/llm_steps.py core/runtime/brief.py prompts/ tests/test_llm_steps.py
git commit -m "feat: per-turn LLM steps — enrichment chips, gated field extraction, pool-gated question pick"
```

### Task 7: Challenge mechanics — governance pull + gates A/B (`core/runtime/challenge.py`)

**Files:**
- Create: `core/runtime/challenge.py`
- Create: `prompts/challenge_triage.txt`, `prompts/challenge_claims.txt`
- Test: `tests/test_challenge.py`

- [ ] **Step 1: Failing tests** — create `tests/test_challenge.py`. Build the graph
fixture with the same in-memory pattern as `tests/test_pool.py`/`tests/test_retriever.py`
(read those fixtures first and reuse the loader-validated YAML-dict style used across
the suite — a small graph with: `sys-a` (kept anchor), `con-x` CONSTRAINS `sys-a`,
`dec-y` SUPERSEDES-attached or CONSTRAINS `sys-a`, `risk-z` adjacent to `sys-a`,
`sys-far` connected only to a rejected node, plus enough nodes to satisfy topology
rules — follow the existing test-graph helpers):

```python
"""Governance pull (deterministic) + gates A and B (the grounding guarantees)."""

import pytest

from core.runtime.challenge import gate_claims, gate_triage, pull_governance

# -- gate A -----------------------------------------------------------------

def test_gate_triage_defaults_missing_nodes_to_keep_and_drops_unknown_ids():
    submitted = {"sys-a", "con-x", "feat-b"}
    verdicts = [
        {"node_id": "sys-a", "verdict": "keep", "reason": "central"},
        {"node_id": "con-x", "verdict": "reject", "reason": "hors sujet"},
        {"node_id": "sys-GHOST", "verdict": "reject", "reason": "?"},
        # feat-b missing → keep (recall-first: the LLM must argue to remove)
    ]
    keeps, rejects, dropped = gate_triage(verdicts, submitted)
    assert keeps == {"sys-a": "central", "feat-b": ""}
    assert rejects == {"con-x": "hors sujet"}
    assert dropped == ["sys-GHOST"]


def test_gate_triage_malformed_verdict_is_dropped_not_fatal():
    keeps, rejects, dropped = gate_triage(
        [{"node_id": "sys-a"}, {"verdict": "keep"}], {"sys-a"}
    )
    assert "sys-a" in keeps  # missing verdict → default keep
    assert dropped == [""]  # the id-less entry

# -- pull --------------------------------------------------------------------
# (fixture: build `service` as described above)

def test_pull_brings_back_governance_neighbors_of_keeps(service):
    pulled = pull_governance(service, kept_ids={"sys-a"}, rejected_ids=set(), cap=10)
    pulled_ids = {p.node_id for p in pulled}
    assert {"con-x", "dec-y", "risk-z"} <= pulled_ids
    assert all(p.via_id == "sys-a" for p in pulled)
    assert all(p.edge_type for p in pulled)


def test_pull_excludes_rejected_and_already_kept_and_respects_cap(service):
    pulled = pull_governance(service, kept_ids={"sys-a", "con-x"},
                             rejected_ids={"dec-y"}, cap=1)
    pulled_ids = {p.node_id for p in pulled}
    assert "con-x" not in pulled_ids  # already kept
    assert "dec-y" not in pulled_ids  # explicitly rejected by the LLM
    assert len(pulled) <= 1  # cap

# -- gate B -------------------------------------------------------------------

def test_gate_claims_filters_ids_sections_and_domains(service):
    payload = {
        "pulled_justifications": [{"node_id": "con-x", "reason": "s'applique"}],
        "claims": [
            {"kind": "constraint_applies", "node_ids": ["con-x"],
             "target_section": "contraintes", "reason": "ok"},
            {"kind": "depends_on", "node_ids": ["sys-GHOST"],
             "target_section": "dependances", "reason": "ghost"},
            {"kind": "risk", "node_ids": ["risk-z"],
             "target_section": "budget", "reason": "bad section"},
        ],
        "domains": ["monetique", "not-a-domain"],
        "challenge_statement": "Le défi.",
    }
    valid, rejected = gate_claims(payload, map_ids={"sys-a", "con-x", "risk-z"},
                                  service=service)
    assert [c["target_section"] for c in valid] == ["contraintes"]
    assert len(rejected) == 2
    assert all(r["reason_rejected"] for r in rejected)


def test_gate_claims_filters_domains_against_vocabulary(service):
    payload = {"pulled_justifications": [], "claims": [],
               "domains": ["monetique", "fake-domain"], "challenge_statement": "x"}
    valid, rejected = gate_claims(payload, map_ids=set(), service=service)
    # gate_claims returns claims; domains are filtered via its companion:
    from core.runtime.challenge import gate_domains
    assert gate_domains(["monetique", "fake-domain"], service) == ["monetique"]
```

(Adapt fixture/domain names to the seed's actual vocabulary — `monetique` exists.
If the in-memory fixture defines its own domains, gate_domains validates against
`service` — use a domain the fixture declares.)

- [ ] **Step 2: Verify failure** — ImportError.

- [ ] **Step 3: Implement** `core/runtime/challenge.py`:

```python
"""CHALLENGING mechanics: gate A (triage), the deterministic governance pull
(the L4-residual answer), gate B (claims) — all pure, no LLM in this module.

The runtime decides; rejections are returned, never swallowed (hard rule 2)."""

from dataclasses import dataclass

from core.dossier.template import CLAIM_SECTIONS
from core.graph.service import GraphService

PULL_CAP = 10  # structural: max governance nodes pulled back per challenge
_PULL_EDGE_TYPES = {"CONSTRAINS", "SUPERSEDES"}
_PULL_NODE_TYPES = {"decision", "risk", "constraint"}
_CLAIM_KINDS = {"depends_on", "constraint_applies", "risk", "overlap"}


def gate_triage(
    verdicts: list[dict], submitted_ids: set[str]
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Returns (keeps {id: reason}, rejects {id: reason}, dropped unknown ids).

    Missing nodes default to KEEP — recall-first, the LLM must argue to remove."""
    keeps: dict[str, str] = {}
    rejects: dict[str, str] = {}
    dropped: list[str] = []
    seen: set[str] = set()
    for verdict in verdicts:
        node_id = str(verdict.get("node_id", ""))
        if node_id not in submitted_ids:
            dropped.append(node_id)
            continue
        seen.add(node_id)
        reason = str(verdict.get("reason", ""))
        if verdict.get("verdict") == "reject":
            rejects[node_id] = reason
        else:
            keeps[node_id] = reason
    for node_id in submitted_ids - seen:
        keeps[node_id] = ""
    return keeps, rejects, dropped


@dataclass(frozen=True)
class PulledNode:
    node_id: str
    via_id: str  # the kept node that brought it back
    edge_type: str


def pull_governance(
    service: GraphService, kept_ids: set[str], rejected_ids: set[str], cap: int = PULL_CAP
) -> list[PulledNode]:
    """1 hop from keeps along governance edges / to governance node types.

    Deterministic order: kept ids sorted, then neighbor ids sorted — stable runs."""
    pulled: list[PulledNode] = []
    seen = set(kept_ids) | set(rejected_ids)
    for kept_id in sorted(kept_ids):
        for edge in sorted(service.neighbors(kept_id), key=lambda e: (e.type, e.source, e.target)):
            other = edge.target if edge.source == kept_id else edge.source
            if other in seen:
                continue
            node = service.get_node(other)
            if edge.type in _PULL_EDGE_TYPES or node.type in _PULL_NODE_TYPES:
                pulled.append(PulledNode(node_id=other, via_id=kept_id, edge_type=edge.type))
                seen.add(other)
                if len(pulled) >= cap:
                    return pulled
    return pulled


def gate_domains(domains: list[str], service: GraphService) -> list[str]:
    known = service.known_domains()
    return [d for d in domains if d in known]


def gate_claims(
    payload: dict, map_ids: set[str], service: GraphService
) -> tuple[list[dict], list[dict]]:
    """Returns (valid claims, rejected claims each carrying reason_rejected)."""
    valid: list[dict] = []
    rejected: list[dict] = []
    for claim in payload.get("claims", []):
        node_ids = [str(n) for n in claim.get("node_ids", [])]
        section = claim.get("target_section", "")
        kind = claim.get("kind", "")
        problem = ""
        if kind not in _CLAIM_KINDS:
            problem = f"type de claim inconnu : {kind}"
        elif not node_ids or any(n not in map_ids for n in node_ids):
            problem = "cite un nœud hors de la carte stabilisée"
        elif section not in CLAIM_SECTIONS:
            problem = f"section non autorisée : {section}"
        if problem:
            rejected.append({**claim, "reason_rejected": problem})
        else:
            valid.append(claim)
    return valid, rejected
```

**Integration notes for the implementer (verify against the real code, adapt):**
`GraphService.neighbors(node_id)` exists (W1); check its return type (edges) and
adapt the edge attribute names (`type`, `source`, `target`) to the actual Edge model.
`service.known_domains()` — check the real accessor for the domain vocabulary
(`domains.yaml` is loaded by the loader; find the existing API, e.g. on the service
or the loader module; if none exists, add a `known_domains()` method to GraphService
returning the vocabulary set, with a 2-line test in `tests/test_challenge.py`).

`prompts/challenge_triage.txt`:

```text
Tu es un architecte SI qui connaît parfaitement le référentiel de l'entreprise.
Voici le brief d'un nouveau projet et la carte brute des éléments du SI retrouvés
par la recherche (volontairement trop large). Pour CHAQUE élément, rends un verdict :
"keep" s'il est réellement pertinent pour cadrer CE projet, "reject" sinon, avec une
raison d'une phrase en français. Ne juge que la pertinence — n'invente rien.
Réponds en JSON : {"verdicts": [{"node_id": "...", "verdict": "keep|reject", "reason": "..."}]}
```

`prompts/challenge_claims.txt`:

```text
Tu es un architecte SI qui challenge un nouveau projet, carte stabilisée en main
(certains éléments ont été ramenés automatiquement : gouvernance liée aux éléments
gardés — justifie-les). Produis :
- "pulled_justifications" : pour chaque élément ramené, une phrase qui dit pourquoi
  il concerne ce projet (ou laisse-le hors de ta liste si tu ne peux pas le justifier) ;
- "claims" : tes affirmations de cadrage (kind ∈ {"depends_on", "constraint_applies",
  "risk", "overlap"}), chacune citant les node_ids concernés et sa section de
  destination dans l'EDB (target_section ∈ {"dependances", "contraintes", "risques",
  "perimetre", "jalons"}), avec une raison en français ;
- "domains" : les domaines du projet (slugs existants uniquement) ;
- "challenge_statement" : le défi argumenté en français — interpelle l'utilisateur
  sur les contraintes, recouvrements et risques que la carte révèle.
Chaque affirmation doit s'appuyer sur des nœuds cités. Réponds en JSON avec ces
quatre clés exactement.
```

- [ ] **Step 4: Run** — `.venv/bin/python -m pytest tests/test_challenge.py -v` → all PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/challenge.py prompts/ tests/test_challenge.py
git commit -m "feat: challenge mechanics — gate A, deterministic governance pull, gate B"
```

### Task 8: Session orchestration — EDB state, turn flow, CHALLENGING wiring

**Files:**
- Modify: `core/runtime/session.py` (the biggest change of the plan — read it fully first)
- Test: extend `tests/test_session.py`

**Target behavior (spec §4-§5), expressed as the new `_map_round` pipeline:**

```
handle_message(text):
  DESCRIBING → brief created → state=MAPPING
  MAPPING/CHALLENGING/SCOPING with pending question → record answer (existing _apply_answer)
  free detail → extract_fields → pending field cards (ledger)
turn pipeline (every message):
  1 enrich_brief(provider, brief)                       # chips
  2 result = retrieve(brief.query_text(), ...)           # query_text, not text
  3 if last message was a free answer: extract_fields → ledger pending cards
  4 pool = build_pool(result, brief, asked, edb)
  5 graph candidates present? → pick_question → Turn(question)
     else if state is MAPPING (map stable, no graph trigger):
         run the two-message challenge once → state=CHALLENGING done → SCOPING
         claims → ledger pending cards; pulled nodes annotated on the map payload;
         challenge_statement → edb 'challenge' section + Turn.message
     else (SCOPING): EDB gaps remain? → pick_question → Turn(question)
         else → Turn(message="EDB complet — prêt pour la rédaction (W4)")
  6 question cap respected for ALL questions (graph + gap)
accept/reject ledger:
  accept field card → edb.add_entry(section, EdbEntry(source="user", ...))
  accept claim card → edb.add_entry(target_section, EdbEntry(source=f"claim:{id}",
                       text=reason, node_refs=node_ids))
```

`ScopingSession.__init__` gains `provider: LLMProvider | None = None` and creates
`self.edb = EdbState.new()`, `self.ledger = Ledger()`, `self.challenge_done = False`,
`self.rejected_nodes: dict[str, str] = {}` (id → reason, the restorable panel),
`self.pulled: list[PulledNode] = []`, `self.gate_rejections: list[dict] = []`.
`Turn` gains `message: str | None = None` (assistant text that is not a question),
`cards: list[Proposal]` (new pending ledger items this turn), and keeps
`result`/`brief` (the web layer reads edb/ledger off the session).

The challenge call sequence (extract into a private method `_run_challenge(result)`):

```python
    def _run_challenge(self, result: RetrievalResult) -> str:
        """Two-message challenge (spec §5). Returns the challenge statement."""
        submitted = {s.node_id for s in [*result.anchors, *result.expanded]}
        triage_user = render_subgraph(result, self._service)  # module-level in challenge.py
        out1 = complete_with_retry(self._provider, load_prompt("challenge_triage"),
                                   triage_user, required_keys=("verdicts",))
        keeps, rejects, dropped = gate_triage(out1["verdicts"], submitted)
        self.rejected_nodes = rejects
        self.gate_rejections += [{"kind": "triage", "node_id": d} for d in dropped]
        self.pulled = pull_governance(self._service, set(keeps), set(rejects))
        map_ids = set(keeps) | {p.node_id for p in self.pulled}
        claims_user = render_stabilized(keeps, self.pulled, self._service)
        out2 = complete_with_retry(self._provider, load_prompt("challenge_claims"),
                                   claims_user, required_keys=(
                                       "pulled_justifications", "claims",
                                       "domains", "challenge_statement"))
        valid, rejected_claims = gate_claims(out2, map_ids, self._service)
        self.gate_rejections += [{"kind": "claim", **r} for r in rejected_claims]
        for claim in valid:
            self.ledger.add(Proposal.claim(
                kind=claim["kind"], node_ids=claim["node_ids"],
                target_section=claim["target_section"], reason=claim["reason"]))
        self.proposed_domains = gate_domains(out2.get("domains", []), self._service)
        statement = str(out2["challenge_statement"])
        self.edb.add_entry("challenge", EdbEntry(source="llm", text=statement))
        self.challenge_done = True
        return statement
```

`render_subgraph(result, service)` / `render_stabilized(keeps, pulled, service)`:
module-level functions in `core/runtime/challenge.py` (the bench reuses them in
Task 11) — plain-text French renderings (one line per node:
`id · type · title — description (domaines: …)`; one line per edge:
`source —TYPE→ target`; pulled nodes appended with `[ramené via X ← TYPE]`). Keep
them dumb and complete — the LLM needs the descriptions to judge.

Provider failure anywhere in `_run_challenge` (JsonContractError) → re-raise as a
session-level error message Turn (`message="Le challenge a échoué (modèle) — réessayez."`),
state STAYS MAPPING so the next message retries. `provider=None` → the session never
enters the challenge (W2 behavior + gap questions only) — assert this in a test.

- [ ] **Step 1: Failing tests** — append to `tests/test_session.py` (reuse the file's
existing service/index fixtures; MockProvider responses must be queued in EXACT call
order — the pipeline calls enrich → extract (only when answering free text) → pick /
challenge phases; count carefully per scenario and document the queue inline):

```python
def test_full_turn_with_provider_fills_edb_and_asks_woven_question():
    # queue: enrich(noop additions) · pick_question(valid gap choice)
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "gap:objectifs", "question": "Quel succès, sachant le gel T3 ?"},
    ])
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question == "Quel succès, sachant le gel T3 ?"
    assert "gap:objectifs" in session.asked


def test_no_provider_session_behaves_like_w2_plus_gap_templates():
    session = ScopingSession(service, index)  # provider=None
    turn = session.handle_message("améliorer notre canal mobile")
    assert turn.question is not None  # template (graph trigger or gap hint)
    assert session.challenge_done is False


def test_challenge_runs_when_map_stable_and_fills_ledger_and_edb():
    # Craft fixture so no graph trigger fires (strong anchor, no foreign pivots).
    # queue: enrich · triage(keep all) · claims(one valid claim + statement)
    provider = MockProvider([
        {"additions": []},
        {"verdicts": []},  # gate A defaults everything to keep
        {"pulled_justifications": [], "claims": [
            {"kind": "depends_on", "node_ids": ["sys-canal"],
             "target_section": "dependances", "reason": "le canal porte le besoin"}],
         "domains": [], "challenge_statement": "Défi : le gel bloque T3."},
    ])
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("refonte du canal")
    assert session.challenge_done is True
    assert session.edb.status("challenge") == "filled"
    pending = session.ledger.pending()
    assert len(pending) == 1 and pending[0].payload["target_section"] == "dependances"
    assert "Défi" in (turn.message or "")


def test_accept_claim_card_writes_edb_section():
    ...build session through the challenge as above...
    pid = session.ledger.pending()[0].id
    session.accept_proposal(pid)
    assert session.edb.status("dependances") == "filled"
    assert session.edb.sections["dependances"][0].source == f"claim:{pid}"


def test_challenge_provider_failure_keeps_state_mapping():
    # queue: enrich ok · triage invalid twice (contract failure)
    provider = MockProvider([{"additions": []}, {"bad": 1}, {"bad": 2}])
    session = ScopingSession(service, index, provider=provider)
    turn = session.handle_message("refonte du canal")
    assert session.challenge_done is False
    assert "réessayez" in (turn.message or "")
```

(The exact fixture graphs/fragments: copy the patterns at the top of
`tests/test_session.py`; pick fragments so the first scenario yields one anchor and
no pivot — e.g. one fragment matching one system. Adjust expected question keys to
what build_pool produces for an empty EDB: `gap:contexte` comes first in template
order, so either fill `contexte` via QA in the fixture or assert on the queue's
chosen key. The MockProvider queue ORDER is the contract — document each entry.)

- [ ] **Step 2: Verify failure** — new tests fail (TypeError: unexpected 'provider').

- [ ] **Step 3: Implement** in `core/runtime/session.py` per the pipeline above. Keep
`detect_trigger`-based W2 behavior intact for `provider=None` (the pool's primary
candidate + template). `accept_proposal(pid, edited_text=None)` and
`reject_proposal(pid)` on the session: accept applies field/claim entries to the EDB
(sources `user`/`claim:<id>` respectively); both return the Proposal for the web
layer. `MAX_QUESTIONS` cap now counts ALL asked questions (graph + gap) — unchanged
constant.

- [ ] **Step 4: Run the full suite** — `.venv/bin/python -m pytest -q` → ALL PASS
(existing session/web tests must stay green: `provider=None` default preserves W2
behavior except that gap questions can now follow graph ones — if an existing test
asserted `question is None` after triggers exhaust, update it deliberately and note
it in the commit message). `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/session.py tests/test_session.py
git commit -m "feat: session orchestration — EDB-driven turns, two-message challenge, ledger application"
```

### Task 9: Web endpoints

**Files:**
- Modify: `web/app.py`
- Test: extend `tests/test_web.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_web.py` (reuse its FakeEmbedder
fixture; `create_app` gains a `provider` param threaded to sessions):

```python
def test_message_response_carries_edb_cards_and_rejections():
    provider = MockProvider([
        {"additions": []},
        {"candidate_key": "gap:objectifs", "question": "Quel succès ?"},
    ])
    client = TestClient(create_app(graph_dir=GRAPH_DIR,
                                   embedder=FakeEmbedder(["application mobile"]),
                                   provider=provider))
    session_id = client.post("/api/session").json()["session_id"]
    out = client.post(f"/api/session/{session_id}/message",
                      json={"text": "projet dans l'application mobile"}).json()
    assert "edb" in out and out["edb"]["besoin"] == []
    assert "cards" in out and "enrichments" in out["brief"]
    assert "rejected_nodes" in out and "gate_rejections" in out


def test_proposal_accept_endpoint_applies_to_edb():
    ...drive a session through a challenge with a scripted MockProvider
       (same queue as test_challenge_runs_when_map_stable...), then:
    pid = ...from the message response cards...
    out = client.post(f"/api/session/{session_id}/proposal/{pid}",
                      json={"decision": "accept"}).json()
    assert out["edb"]["dependances"]


def test_enrichment_removal_endpoint_reruns_retrieval():
    ...session with one enrichment chip...
    out = client.delete(f"/api/session/{session_id}/enrichment/0").json()
    assert out["brief"]["enrichments"] == []


def test_node_restore_endpoint_moves_rejected_back_to_map():
    ...session with challenge done and one rejected node...
    out = client.post(f"/api/session/{session_id}/restore/{node_id}").json()
    assert node_id not in out["rejected_nodes"]
```

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** in `web/app.py`:
- `create_app(..., provider: LLMProvider | None = None)`; if None AND env configured,
  `provider = make_provider()` (so `uvicorn` picks up `SCOPEGRAPH_LLM_PROVIDER`);
  sessions get the provider.
- The message response grows: `edb` (state.to_dict()), `cards` (this turn's pending
  proposals as dicts), `message` (assistant text), `rejected_nodes`,
  `gate_rejections`, `pulled` (id, via, edge_type), `proposed_domains`; `brief`
  already serializes (now includes enrichments via the Pydantic model).
- New endpoints, all returning the same full session payload (one rendering helper
  `_session_payload(session, result)` shared by every route):
  `POST /api/session/{id}/proposal/{pid}` body `{"decision": "accept"|"reject", "edited_text"?}` ·
  `DELETE /api/session/{id}/enrichment/{index}` (removes chip, re-runs `_map_round`) ·
  `POST /api/session/{id}/restore/{node_id}` (moves the node from rejected back into
  the kept map; provenance label "restauré par l'utilisateur").
- Restore/enrichment removal call back into session methods (`restore_node`,
  `remove_enrichment`) — implement them on `ScopingSession` (4-6 lines each, with one
  hermetic test each appended to `tests/test_session.py`).

- [ ] **Step 4: Run full suite + ruff** — all green.

- [ ] **Step 5: Commit**

```bash
git add web/app.py core/runtime/session.py tests/
git commit -m "feat: web endpoints — edb payload, proposal decisions, chip removal, node restore"
```

### Task 10: UI — three panes

**Files:**
- Modify: `web/static/index.html` (121 lines today — read it fully first; keep its
  Alpine + Cytoscape structure and CSS conventions, extend rather than rewrite)

No hermetic tests (the repo has none for HTML); verification is manual via the
preview workflow below. Implementation contract:

- **Layout**: 3 columns (chat · map · EDB). The EDB pane lists the 12 sections
  (`title_fr`), each showing its entries (text + small source badge `vous`/`IA`/
  `claim`) or a muted "—"; a completeness badge at the top ("2 sections à remplir" —
  count from `edb` payload of askable sections, the backend exposes
  `missing_sections` in the payload to avoid duplicating owner logic in JS).
- **Chat**: assistant messages (questions AND `message` texts); below the input,
  enrichment chips (`brief.enrichments`) each with an × calling the DELETE endpoint;
  pending `cards` render inline with Accepter / Modifier (prompt() is fine) /
  Refuser buttons calling the proposal endpoint.
- **Map pane**: unchanged Cytoscape; below it a collapsible "Rejetés (N)" list
  (id, reason, bouton Restaurer → restore endpoint) and a thin amber strip listing
  `gate_rejections` ("réclamations de l'IA rejetées par le runtime") when non-empty.
  Pulled nodes get the existing `annotations` mechanism with role "pulled" (extend
  `_annotations` in web/app.py accordingly — style them with a distinct border in
  the Cytoscape stylesheet).
- Every endpoint response refreshes the whole Alpine state from `_session_payload`
  (no incremental DOM surgery).

- [ ] **Step 1: Implement the page** per the contract.
- [ ] **Step 2: Verify with the preview tools** — start
  `uvicorn --factory web.app:create_app` via preview_start (env
  `SCOPEGRAPH_LLM_PROVIDER=none` → template mode works without keys), then
  preview_snapshot: 3 panes render, sections listed, a question appears; post a
  message via the chat input (preview_fill + preview_click) and confirm the EDB pane
  updates. Screenshot for the record.
- [ ] **Step 3: Commit**

```bash
git add web/static/index.html web/app.py
git commit -m "feat: three-pane UI — live EDB, chips, cards, rejected panel, pulled styling"
```

### Task 11: Shared scenarios module + challenge bench

**Files:**
- Create: `core/benchdata/__init__.py`, `core/benchdata/scenarios.py`
- Modify: `scripts/retrieval-eval` (import SCENARIOS/BRIEFS from core.benchdata)
- Create: `scripts/challenge-eval`
- Test: `tests/test_benchdata.py` (3 lines: 11 scenarios, ids unique, expected sets non-empty)

- [ ] **Step 1**: Move the `SCENARIOS` list verbatim from `scripts/retrieval-eval` into
`core/benchdata/scenarios.py` (module docstring: "Ground truth for the real-model
benches — single source, hand-derived from seed edges; hermetic data, no imports").
`scripts/retrieval-eval` imports it (`from core.benchdata.scenarios import SCENARIOS`)
and deletes its local copy; `BRIEFS` in `scripts/retrieval-smoke` stays (different
purpose — calibration briefs). Add `tests/test_benchdata.py`:

```python
from core.benchdata.scenarios import SCENARIOS


def test_scenarios_shape():
    assert len(SCENARIOS) == 11
    names = [s[0] for s in SCENARIOS]
    assert len(set(names)) == 11
    assert all(s[2] for s in SCENARIOS)
```

Run the full suite + `./scripts/retrieval-eval --help` (exit 0). Commit:

```bash
git add core/benchdata/ scripts/retrieval-eval tests/test_benchdata.py
git commit -m "refactor: scenario ground truth to core/benchdata (single source for both benches)"
```

- [ ] **Step 2: Create `scripts/challenge-eval`** (real models, out of CI — same
header pattern as retrieval-eval: sys.path insert, line-buffered stdout). Contract:

```
usage: ./scripts/challenge-eval [--provider deepseek|mistral] [--n 0 2000] [--no-cache]
```

For each scenario × N: build service (`build_service` pattern from retrieval-eval),
build index (DEFAULT_PROFILE embedder), run `retrieve`, then drive the SAME
challenge code path the session uses — instantiate `ScopingSession(service, index,
provider=provider)` is wrong here (it would ask questions); instead call the
extracted mechanics directly: `gate_triage`/`pull_governance`/`gate_claims` around
two `complete_with_retry` calls with the SAME prompts and the SAME subgraph
rendering used by the session (import the session's `_render_subgraph` helper — to
make it importable, implement it in Task 8 as a module-level function
`render_subgraph(result, service)` in `core/runtime/challenge.py`, used by both).
Per scenario, report recall of the expected set at three stages: raw retrieval →
post-pull → post-LLM-keeps; final map size + precision; expected nodes the LLM
itself rejected (`lost_by_llm`). Per N, mean line; at the end the per-case trap
criterion vs raw N=0 + the autopsy style of retrieval-eval (reuse what is cheap,
don't over-engineer).

**Cache**: `.bench-cache/` (add to `.gitignore`), key = sha256 of
`(scenario_name, n, provider_name, model, prompt_file_hashes, subgraph_text)`,
value = the raw JSON responses of both calls. `--no-cache` bypasses. Provider name +
model + date in the output header.

Provider resolution: `--provider` flag → explicit constructor with env key
(`DEEPSEEK_API_KEY` / `MISTRAL_API_KEY`); a missing key is a clean startup error
naming the variable.

Validation without keys: `./scripts/challenge-eval --help` exits 0;
`.venv/bin/ruff check scripts/challenge-eval` clean; the cache/key logic gets a
hermetic test in `tests/test_benchdata.py` if extracted to a small function
(`cache_key(...)` in the script is fine to leave untested — it's out of CI).

- [ ] **Step 3: Commit**

```bash
git add scripts/challenge-eval .gitignore
git commit -m "feat: challenge-eval — end-to-end real-LLM bench, per-stage recall, disk cache"
```

### Task 12: Docs closure + demo script

**Files:**
- Modify: `docs/BUILD-ORDER.md` (W3 status: lots done, what the bench showed if run, next = bench run/W4)
- Create: `docs/demo-w3.md` (the scripted demo: setup `pip install -e ".[embeddings,llm]"`,
  `SCOPEGRAPH_LLM_PROVIDER=mistral`, the cash-back walkthrough from spec §8 step by step
  with the expected on-screen behavior at each step)
- Modify: `README.md` if it documents how to run the app (add the env vars)

- [ ] **Step 1**: Write both docs; BUILD-ORDER per its conventions (status only there).
- [ ] **Step 2**: Full suite + ruff one last time.
- [ ] **Step 3: Commit**

```bash
git add docs/ README.md
git commit -m "docs: W3 closure — BUILD-ORDER status, scripted demo walkthrough"
```

### STOP point

The real-LLM bench run (`./scripts/challenge-eval`) and the live Mistral demo need
API keys and Loïc's go — they are NOT part of plan execution. Stop after Task 12 and
report; the bench numbers land in known-limits L1/L4 in a follow-up session.

---

## Self-review notes (kept for the executor)

- Spec coverage: §1→tasks 1-2 · §2→task 3 · §3→tasks 1-2 · §4→tasks 5-6-8 · §5→tasks 7-8 ·
  §6→tasks 9-10 · §7→task 11 · §8→task 12 · §9→every task's test steps. The
  `partial` status of spec §2 is deliberately deferred (noted in task 3) — binary
  fill is enough for gap detection; W4's renderer revisits.
- The MockProvider queue order (enrich → extract → pick/challenge) is the
  brittleness hotspot of the session tests: every test documents its queue inline.
- Type consistency pinned across tasks: `Candidate.key` strings (`"weak"`,
  `"tie:a:b"`, `"pivot:<domain>"`, `"gap:<section>"`); `Proposal.payload` dict keys
  (`claim_kind|node_ids|target_section` / `section_id|node_refs`); `PulledNode`
  dataclass; `complete_with_retry(provider, system, user, required_keys=...)`.
- Open integration risks flagged where they live: Edge attribute names (task 7),
  GraphService domain vocabulary accessor (task 7), existing web tests' expectations
  (task 8 step 4), index.html conventions (task 10).

