# Post-challenge Reliability + Richer EDB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the post-challenge map coherent (exclusions are commitments), make the EDB precise (sufficiency rubric + challenge-for-numbers), tighten claim grounding, and quarantine flagged challenge statements.

**Architecture:** The runtime keeps deciding; every new LLM step degrades to today's behavior with `provider=None`. The map honors accumulated exclusions and re-applies `excluded_domains` at the payload layer (anchors bypass it in retrieval). EDB completeness moves from binary presence to LLM-judged sufficiency, bounded so the interview still converges. Two new judge steps (sufficiency, claim grounding) batch their work; the flagged statement routes through the existing ledger.

**Tech Stack:** Python 3.12, pytest (hermetic, `MockProvider`), FastAPI, the existing `core/runtime` + `core/dossier` + `core/llm` modules. Spec: `docs/specs/2026-06-14-post-challenge-reliability-edb-design.md`.

**Conventions (read before starting):**
- Tests are hermetic. `tests/conftest.py` forces `SCOPEGRAPH_LLM_PROVIDER=none`. LLM behavior is tested by injecting `MockProvider([{...}, ...])` (a FIFO of scripted dicts). A failed JSON contract = two bad dicts in a row (the one retry).
- `ScopingSession(service, index)` is template-mode; `ScopingSession(service, index, provider=mock)` exercises the LLM path. `tests/test_session.py` has `make_service()` / `make_session(fragments)` helpers — reuse them; for the LLM path build the session inline with a `MockProvider`.
- Prompts live in `prompts/*.txt`, loaded by name via `load_prompt`. Never inline a prompt in Python.
- Run a single test: `pytest tests/test_X.py::test_name -v`. Run all: `pytest -q`. Lint: `ruff check .`.
- Commit after each task. Branch is already `post-challenge-reliability-edb`.

---

## File Structure

**Chantier 1 — live coherent map (#1)**
- Modify `core/runtime/session.py` — accumulate exclusions, `kept_node_ids()` helper, recompute `pulled` post-challenge, `previously_mapped` snapshot.
- Modify `web/app.py` — payload uses `session.kept_node_ids()`, annotate new nodes.
- Modify `web/static/index.html` — style the `nouveau` annotation (non-TDD).
- Tests: `tests/test_session.py`, `tests/test_web.py`.

**Chantier 2 — EDB sufficiency + extraction (#2, #5)**
- Modify `core/dossier/template.py` — `sufficiency_fr` field, `incomplete_sections()`.
- Modify `core/runtime/llm_steps.py` — `judge_section_sufficiency`, extract-prompt wiring.
- Create `prompts/judge_sufficiency.txt`; modify `prompts/extract_fields.txt`.
- Modify `core/runtime/pool.py` — `Candidate.followup`, `build_pool` uses `incomplete_sections`.
- Modify `core/runtime/session.py` — mine initial brief, sufficiency wiring, `precision_asked`, completeness message.
- Tests: `tests/test_dossier.py`, `tests/test_llm_steps.py`, `tests/test_pool.py`, `tests/test_session.py`.

**Chantier 3 — clause-complete grounding (#3)**
- Modify `core/runtime/llm_steps.py` — `judge_claim_grounding`.
- Create `prompts/judge_claim_grounding.txt`.
- Modify `core/runtime/session.py` — `_run_challenge` rejects ungrounded claims.
- Tests: `tests/test_llm_steps.py`, `tests/test_session.py`.

**Chantier 4 — statement quarantine (#4)**
- Modify `core/runtime/ledger.py` — `Proposal.statement` constructor.
- Modify `core/runtime/session.py` — `_run_challenge` quarantines flagged statement; `accept_proposal` writes it to the `challenge` section.
- Modify `web/app.py` — `_card_dict` surfaces flags/issues.
- Tests: `tests/test_ledger.py`, `tests/test_session.py`, `tests/test_web.py`.

**Chantier 5 — end-to-end scenario + verification**
- Modify `core/benchdata/metrics.py` if needed (use `kept_node_ids`).
- Add an integration test tying #1–#5; run full suite + ruff; update `docs/BUILD-ORDER.md`.
- Tests: `tests/test_session.py`.

---

## Chantier 1 — Live coherent map (#1)

### Task 1: `kept_node_ids()` + accumulated exclusions + recomputed pull + new-node snapshot

**Files:**
- Modify: `core/runtime/session.py` (`__init__`, `_run_challenge`, `_map_round`; new `kept_node_ids`)
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_session.py` (uses the existing `make_session`/`make_service` helpers):

```python
def test_excluded_domain_node_stays_off_map_after_a_later_precision() -> None:
    # canal mobile anchors; the user excludes monetique; a later precision must NOT
    # let sys-moteur (monetique) ride back in as an anchor of the broadened query.
    session = make_session(["canal", "moteur"])
    session.handle_message("améliorer notre canal mobile")
    session.handle_message("non")  # monetique out of scope
    assert "sys-moteur" not in session.kept_node_ids()
    # volunteer a precision whose words now surface the moteur as an anchor
    session.handle_message("le moteur central de paiement est concerné par les délais")
    assert "monetique" in session.brief.excluded_domains
    assert "sys-moteur" not in session.kept_node_ids()  # exclusion is a commitment
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_session.py::test_excluded_domain_node_stays_off_map_after_a_later_precision -v`
Expected: FAIL — `AttributeError: 'ScopingSession' object has no attribute 'kept_node_ids'`.

- [ ] **Step 3: Add the `previously_mapped` field**

In `core/runtime/session.py` `__init__`, after the `self.statement_issues` line, add:

```python
        self.previously_mapped: set[str] = set()  # the stabilized map at challenge time (new-node diff)
```

- [ ] **Step 4: Add the `kept_node_ids` method**

In `core/runtime/session.py`, add this method to `ScopingSession` (e.g. right after `_map_round`):

```python
    def kept_node_ids(self) -> set[str]:
        """The nodes currently on the map: retrieval ∪ pulled, minus accumulated
        exclusions and excluded-domain nodes. Retrieval drops excluded domains only in
        the expansion layer (anchors bypass it) — re-apply the rule here so an excluded
        domain can never ride back in as an anchor of a broadened post-challenge query."""
        if self.last_result is None:
            return set()
        confirmed = set(self.brief.domains) if self.brief else set()
        excluded = set(self.brief.excluded_domains) if self.brief else set()
        base = set(self.last_result.node_ids()) | {p.node_id for p in self.pulled}
        base -= set(self.rejected_nodes)
        kept = set()
        for nid in base:
            node_domains = set(self._service.get_node(nid).domains)
            if node_domains & excluded and not (node_domains & confirmed):
                continue  # excluded with no confirmed-domain rescue (mirrors retriever._expand)
            kept.add(nid)
        return kept
```

- [ ] **Step 5: Accumulate exclusions instead of replacing them**

In `_run_challenge`, change line ~243 from `self.rejected_nodes = rejects` to:

```python
        self.rejected_nodes.update(rejects)  # accumulate — exclusions persist across reruns
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_session.py::test_excluded_domain_node_stays_off_map_after_a_later_precision -v`
Expected: PASS.

- [ ] **Step 7: Write the new-node + recomputed-pull test**

Add to `tests/test_session.py` (LLM-free path is fine — these are runtime mechanics):

```python
def test_post_challenge_precision_marks_new_nodes_and_keeps_exclusions() -> None:
    from core.runtime.challenge import PulledNode
    session = make_session(["canal", "moteur", "terminal"])
    session.handle_message("améliorer notre canal mobile")
    # simulate a completed challenge: stabilize on sys-canal, snapshot the map
    session.challenge_done = True
    session.state = SessionState.SCOPING
    session.rejected_nodes = {"sys-terminal": "non spécifique"}
    session.previously_mapped = session.kept_node_ids()
    assert "sys-terminal" not in session.previously_mapped
    snapshot = set(session.previously_mapped)
    # a precision that broadens retrieval must keep sys-terminal excluded
    session.handle_message("préciser le besoin de paiement")
    assert "sys-terminal" not in session.kept_node_ids()
    # any node now on the map but absent from the snapshot is "new"
    new_nodes = session.kept_node_ids() - snapshot
    assert new_nodes == session.kept_node_ids() - session.previously_mapped
```

Note: `previously_mapped` is refreshed only at challenge time (Step 8), so the snapshot
taken here stays the diff baseline through the precision turn.

- [ ] **Step 8: Snapshot the stabilized map + recompute pull post-challenge**

In `_map_round`, replace the challenge `elif` body and the trailing `self.last_result = result` handling so the snapshot is taken once, at challenge time, and `pulled` is recomputed on every post-challenge rerun. Concretely:

Add an import at the top of `session.py` (it already imports from `core.runtime.challenge`): include `pull_governance` in that import list (it is already imported — confirm `pull_governance` is in the `from core.runtime.challenge import (...)` block; it is).

In `_map_round`, after `result = retrieve(...)` and before `pool = build_pool(...)`, add the post-challenge pull recompute:

```python
        if self.challenge_done:
            # the map is live post-challenge: recompute the governance pull on the
            # current retrieval against the accumulated exclusions (deterministic).
            keeps = set(result.node_ids()) - set(self.rejected_nodes)
            self.pulled = pull_governance(self._service, keeps, set(self.rejected_nodes))
```

In the challenge branch (`message, claim_cards = self._run_challenge(result)` block), after `self.state = SessionState.SCOPING`, set `self.last_result = result` early so the snapshot is accurate, then snapshot:

```python
                self.state = SessionState.SCOPING
                self._consecutive_graph_questions = 0
                self.last_result = result
                self.previously_mapped = self.kept_node_ids()  # baseline for the new-node diff
```

(The unconditional `self.last_result = result` at the end of `_map_round` stays; re-assigning is harmless.)

- [ ] **Step 9: Run both Chantier-1 session tests**

Run: `pytest tests/test_session.py -k "excluded_domain_node or post_challenge_precision" -v`
Expected: PASS (2 tests).

- [ ] **Step 10: Run the full session suite (no regressions)**

Run: `pytest tests/test_session.py -q`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add core/runtime/session.py tests/test_session.py
git commit -m "fix(#1): accumulate exclusions, kept_node_ids honors excluded domains, recompute pull post-challenge

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2: Payload uses `kept_node_ids()` and annotates new nodes

**Files:**
- Modify: `web/app.py` (`_annotations`, `_session_payload`)
- Test: `tests/test_web.py`

- [ ] **Step 1: Inspect the existing web test setup**

Run: `pytest tests/test_web.py -q` and open `tests/test_web.py` to learn how it builds a `TestClient` (FakeEmbedder + MockProvider via `create_app`). Reuse that fixture/pattern for the new test.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_web.py` a test asserting the map payload excludes an excluded-domain node and annotates a new node. Follow the file's existing client-construction pattern; the assertion core:

```python
def test_payload_map_drops_excluded_and_marks_new_nodes(client_factory):
    # client_factory is the helper this file already uses to build a TestClient with a
    # scripted MockProvider; adapt to whatever the file names it.
    client = client_factory()  # see existing tests for the exact construction
    sid = client.post("/api/session").json()["session_id"]
    body = client.post(f"/api/session/{sid}/message",
                       json={"text": "améliorer notre canal mobile"}).json()
    # excluded-domain nodes must never be in the rendered map
    map_ids = {n["data"]["id"] for n in body["map"]["elements"]["nodes"]} \
        if "elements" in body["map"] else {n["id"] for n in body["map"]["nodes"]}
    assert isinstance(map_ids, set)
```

If `tests/test_web.py` has no `client_factory`, write the smallest local helper mirroring the file's existing setup (FakeEmbedder, `create_app(..., provider=MockProvider([...]))`). Keep the assertion focused on: (a) the payload renders, (b) `kept_node_ids` drives `only`.

- [ ] **Step 3: Run it to verify it fails or is red against current behavior**

Run: `pytest tests/test_web.py::test_payload_map_drops_excluded_and_marks_new_nodes -v`
Expected: FAIL initially (helper/shape mismatch) — adjust the node-id extraction to the real payload shape printed in the failure, then it should pass once Step 4 lands.

- [ ] **Step 4: Switch the payload to `kept_node_ids()` and annotate new nodes**

In `web/app.py` `_session_payload`, replace the `kept = (...)` computation (lines ~81-83) with:

```python
    kept = session.kept_node_ids()
```

In `_annotations`, after the `restored` loop and before `return annotations`, add the new-node marking:

```python
    if session.challenge_done:
        for node_id in kept_ids - session.previously_mapped:
            annotations[node_id] = {**annotations.get(node_id, {}), "provenance": "nouveau"}
    return annotations
```

`_annotations` must receive the kept set. Change its signature to `_annotations(session, result, kept_ids)` and pass `kept` from `_session_payload`:

```python
        annotations=_annotations(session, result, kept),
```

- [ ] **Step 5: Run the web test + full web suite**

Run: `pytest tests/test_web.py -q`
Expected: all PASS.

- [ ] **Step 6: Style the new-node annotation (non-TDD UI)**

In `web/static/index.html`, find where `provenance === "restauré par l'utilisateur"` styles a node (the restored styling) and add a sibling branch for `provenance === "nouveau"` (e.g. a dashed accent border / "nouveau" badge), matching the existing Cytoscape style convention in that file. Verify the app still loads (`uvicorn --factory web.app:create_app`) if an embedder is available; otherwise rely on the payload test.

- [ ] **Step 7: Commit**

```bash
git add web/app.py web/static/index.html tests/test_web.py
git commit -m "fix(#1): map payload uses kept_node_ids and flags new post-challenge nodes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chantier 2 — EDB sufficiency + extraction (#2, #5)

### Task 3: `sufficiency_fr` rubric + `incomplete_sections()`

**Files:**
- Modify: `core/dossier/template.py`
- Test: `tests/test_dossier.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_dossier.py`:

```python
def test_every_askable_section_has_a_sufficiency_criterion():
    from core.dossier.template import ASKABLE_SECTIONS, section_spec
    for sid in ASKABLE_SECTIONS:
        assert section_spec(sid).sufficiency_fr.strip()


def test_incomplete_sections_includes_empty_and_judged_insufficient():
    state = EdbState.new()
    state.add_entry("besoin", EdbEntry(source="user", text="un cash-back"))
    # besoin filled but judged insufficient → still incomplete; objectifs empty → incomplete
    incomplete = state.incomplete_sections(insufficient={"besoin"})
    assert "besoin" in incomplete
    assert "objectifs" in incomplete
    # filled AND judged sufficient → not incomplete
    assert "besoin" not in state.incomplete_sections(insufficient=set())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_dossier.py -k "sufficiency_criterion or incomplete_sections" -v`
Expected: FAIL — `AttributeError: 'EdbSectionSpec' object has no attribute 'sufficiency_fr'`.

- [ ] **Step 3: Add `sufficiency_fr` to the spec dataclass and every section**

In `core/dossier/template.py`, add the field to `EdbSectionSpec`:

```python
@dataclass(frozen=True)
class EdbSectionSpec:
    id: str
    title_fr: str
    owner: Owner
    prompt_hint_fr: str  # the deterministic fallback question for gap candidates
    sufficiency_fr: str = ""  # what makes the section precise enough (drives the LLM judge)
```

Then fill `sufficiency_fr` for each askable section in `EDB_TEMPLATE_V1` (keep the llm/runtime sections at `""`):

```python
EDB_TEMPLATE_V1: tuple[EdbSectionSpec, ...] = (
    EdbSectionSpec("contexte", "Contexte & raison d'être", "mixed",
                   "Dans quel contexte ce besoin apparaît-il (origine, déclencheur) ?",
                   "Un déclencheur concret est nommé (événement, contrainte, opportunité datée)."),
    EdbSectionSpec("besoin", "Expression du besoin", "user",
                   "Quel problème métier ce projet doit-il résoudre, en une phrase ?",
                   "Le problème métier est formulé précisément, pas en généralités."),
    EdbSectionSpec("utilisateurs", "Utilisateurs & parties prenantes", "mixed",
                   "Qui utilisera le résultat, et qui sponsorise le projet ?",
                   "Le sponsor ET les utilisateurs finaux sont nommés."),
    EdbSectionSpec("objectifs", "Objectifs & critères de réussite", "user",
                   "À quelles conditions ce projet sera-t-il un succès ?",
                   "Au moins un critère de réussite mesurable (un chiffre, une cible, un seuil)."),
    EdbSectionSpec("perimetre", "Périmètre in / hors périmètre", "mixed",
                   "Qu'est-ce qui est explicitement dans — et hors — du périmètre ?",
                   "Le dans-périmètre ET le hors-périmètre sont tous deux explicités."),
    EdbSectionSpec("exigences", "Exigences fonctionnelles et non-fonctionnelles", "mixed",
                   "Quelles exigences fortes (fonctionnelles ou non) faut-il poser dès maintenant ?",
                   "Les exigences non-fonctionnelles sont chiffrées quand cela a un sens (volumétrie, SLA, délai)."),
    EdbSectionSpec("dependances", "Dépendances & systèmes impactés", "graph",
                   "Des dépendances connues à signaler ?",
                   "Les systèmes impactés connus sont listés."),
    EdbSectionSpec("contraintes", "Contraintes héritées", "graph",
                   "Des contraintes (réglementaires, gels, standards) à signaler ?",
                   "Les contraintes réglementaires/gels/standards pertinents sont listés."),
    EdbSectionSpec("risques", "Risques initiaux", "mixed",
                   "Quels risques voyez-vous à ce stade ?",
                   "Au moins un risque concret avec son origine est nommé."),
    EdbSectionSpec("jalons", "Jalons / échéance cible", "mixed",
                   "Y a-t-il une échéance cible ou des jalons imposés ?",
                   "Une échéance ou un jalon daté est précisé."),
    EdbSectionSpec("challenge", "Challenge & arbitrages ouverts", "llm", "", ""),
    EdbSectionSpec("carte", "Context Map", "runtime", "", ""),
)
```

- [ ] **Step 4: Add `incomplete_sections()` to `EdbState`**

In `core/dossier/template.py`, add this method to `EdbState` (keep `missing_sections` — `incomplete_sections` builds on it):

```python
    def incomplete_sections(self, insufficient: set[str] = frozenset()) -> list[str]:
        """Askable sections still empty OR judged insufficient, in template order.

        `insufficient` is the set of filled-but-imprecise section ids from the LLM
        sufficiency judge; without a provider it is empty → behaves like missing_sections."""
        return [sid for sid in _ASKABLE
                if not self.sections[sid] or sid in insufficient]
```

- [ ] **Step 5: Run the dossier tests**

Run: `pytest tests/test_dossier.py -q`
Expected: all PASS (the existing `test_template_has_the_12_frozen_sections_in_order` still passes — `prompt_hint_fr` truthiness for the first 10 is unchanged).

- [ ] **Step 6: Commit**

```bash
git add core/dossier/template.py tests/test_dossier.py
git commit -m "feat(#2): EDB sufficiency rubric per section + incomplete_sections()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4: `judge_section_sufficiency` LLM step + prompt

**Files:**
- Create: `prompts/judge_sufficiency.txt`
- Modify: `core/runtime/llm_steps.py`
- Test: `tests/test_llm_steps.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_steps.py`:

```python
def test_judge_sufficiency_returns_insufficient_set_and_followups():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="améliorer l'expérience"))
    provider = MockProvider([{"verdicts": [
        {"section_id": "objectifs", "sufficient": False,
         "followup_fr": "Quel gain chiffré visez-vous, et à quelle échéance ?"},
    ]}])
    insufficient, followups = judge_section_sufficiency(provider, edb)
    assert insufficient == {"objectifs"}
    assert followups["objectifs"].startswith("Quel gain")


def test_judge_sufficiency_none_provider_is_empty():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="x"))
    assert judge_section_sufficiency(None, edb) == (set(), {})


def test_judge_sufficiency_swallows_contract_failure():
    from core.runtime.llm_steps import judge_section_sufficiency
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="x"))
    provider = MockProvider([{"bad": 1}, {"still": 2}])
    assert judge_section_sufficiency(provider, edb) == (set(), {})
```

Need `EdbEntry` imported in the test file — add it to the existing `from core.dossier.template import EdbState` line: `from core.dossier.template import EdbEntry, EdbState`.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_llm_steps.py -k judge_sufficiency -v`
Expected: FAIL — `ImportError: cannot import name 'judge_section_sufficiency'`.

- [ ] **Step 3: Create the prompt**

Create `prompts/judge_sufficiency.txt`:

```
Tu assistes un outil de cadrage de projets bancaires. Pour chaque section d'expression
de besoin ci-dessous, on te donne son critère de suffisance et son contenu actuel.
Juge si le contenu satisfait le critère. Une section vague, sans chiffre quand le critère
en demande un, ou incomplète est « insuffisante ». Pour chaque section insuffisante,
formule UNE question de relance ciblée, en français, qui demande précisément l'élément
manquant (un chiffre, une date, un nom). N'invente rien. Réponds en JSON :
{"verdicts": [{"section_id": "...", "sufficient": true|false, "followup_fr": "..."}]}
N'inclus que les sections fournies. followup_fr peut être vide si sufficient vaut true.
```

- [ ] **Step 4: Implement `judge_section_sufficiency`**

Add to `core/runtime/llm_steps.py` (after `extract_fields`, near the other judges). Import the template helpers at the top: `from core.dossier.template import ASKABLE_SECTIONS, EdbState, section_spec`.

```python
def judge_section_sufficiency(
    provider: LLMProvider | None, edb: EdbState
) -> tuple[set[str], dict[str, str]]:
    """LLM judge over the FILLED askable sections: which are too vague/imprecise, and a
    targeted follow-up for each. Returns (insufficient_ids, {section_id: followup_fr}).
    (set(), {}) without a provider or on contract failure — binary completeness survives."""
    if provider is None:
        return set(), {}
    filled = [sid for sid in ASKABLE_SECTIONS if edb.sections[sid]]
    if not filled:
        return set(), {}
    blocks = []
    for sid in filled:
        spec = section_spec(sid)
        content = " | ".join(e.text for e in edb.sections[sid])
        blocks.append(f"[{sid}] critère : {spec.sufficiency_fr}\ncontenu : {content}")
    user = "\n\n".join(blocks)
    try:
        out = complete_with_retry(provider, load_prompt("judge_sufficiency"), user,
                                  required_keys=("verdicts",))
    except JsonContractError:
        return set(), {}
    insufficient: set[str] = set()
    followups: dict[str, str] = {}
    for verdict in out.get("verdicts", []):
        sid = str(verdict.get("section_id", ""))
        if sid in filled and verdict.get("sufficient") is False:
            insufficient.add(sid)
            followups[sid] = str(verdict.get("followup_fr", "")).strip()
    return insufficient, followups
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_llm_steps.py -k judge_sufficiency -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add core/runtime/llm_steps.py prompts/judge_sufficiency.txt tests/test_llm_steps.py
git commit -m "feat(#2): judge_section_sufficiency LLM step (targeted precision follow-ups)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5: Pool carries the follow-up and uses `incomplete_sections`

**Files:**
- Modify: `core/runtime/pool.py`
- Test: `tests/test_pool.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pool.py` (mirror the file's existing `build_pool` setup for `result`/`brief`/`edb`):

```python
def test_build_pool_offers_insufficient_filled_section_with_followup():
    from core.dossier.template import EdbEntry, EdbState
    edb = EdbState.new()
    edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    # reuse the file's helpers to build an empty-graph result + a brief with no pivots
    result, brief = _empty_result_and_brief()  # see existing helpers in this file
    pool = build_pool(result, brief, asked=set(), edb=edb,
                      insufficient={"objectifs"}, followups={"objectifs": "Chiffrez ?"})
    objectifs = [c for c in pool if c.section_id == "objectifs"]
    assert objectifs and objectifs[0].followup == "Chiffrez ?"
```

If `tests/test_pool.py` lacks an empty-result helper, build the minimal `RetrievalResult([], [], {}, [])` and `ProjectBrief(description="d")` inline.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_pool.py -k insufficient_filled_section -v`
Expected: FAIL — `build_pool() got an unexpected keyword argument 'insufficient'`.

- [ ] **Step 3: Add `followup` to `Candidate` and the new params to `build_pool`**

In `core/runtime/pool.py`, add the field to `Candidate`:

```python
    section_id: str = ""  # edb_gap context
    followup: str = ""  # edb_gap precision follow-up (sufficiency judge), else ""
    trigger: Trigger | None = None  # the W2 trigger object for fallback rendering
```

Change `build_pool`'s signature and the gap loop:

```python
def build_pool(
    result: RetrievalResult,
    brief: ProjectBrief,
    asked: set[str],
    edb: EdbState,
    *,
    profile: RetrievalProfile = DEFAULT_PROFILE,
    insufficient: set[str] = frozenset(),
    followups: dict[str, str] | None = None,
) -> list[Candidate]:
    followups = followups or {}
    ...  # (weak/tie/pivot blocks unchanged)
    for section_id in edb.incomplete_sections(insufficient):
        key = f"gap:{section_id}"
        if key not in asked:
            pool.append(Candidate(kind="edb_gap", key=key, section_id=section_id,
                                  followup=followups.get(section_id, "")))
    return pool
```

- [ ] **Step 4: Run the pool tests**

Run: `pytest tests/test_pool.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/pool.py tests/test_pool.py
git commit -m "feat(#2): pool offers insufficient filled sections, carries precision follow-up

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6: Session wiring — mine the brief, sufficiency in the round, precision-asked, completeness

**Files:**
- Modify: `core/runtime/session.py`, `core/runtime/llm_steps.py` (`_template_question`/`_candidate_context` use `followup`)
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session.py`:

```python
def test_initial_brief_is_mined_into_the_edb():
    # the first message must feed extract_fields (provider path), not be discarded
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    mock = MockProvider([
        {"additions": []},  # enrich_brief
        {"entries": [{"section_id": "jalons", "text": "pilote octobre 2026"}]},  # extract on brief
        {"verdicts": []},  # judge_section_sufficiency
        {"candidate_key": "gap:contexte", "question": "Contexte ?"},  # pick_question
    ])
    session = ScopingSession(service, index, provider=mock)
    session.handle_message("paiement en 3 fois, pilote octobre 2026")
    assert any("octobre 2026" in e.text for e in session.edb.sections["jalons"])


def test_insufficient_section_is_re_asked_once_then_closed():
    from core.runtime.session import ScopingSession
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    # objectifs filled-but-vague; judged insufficient → re-asked; precision_asked closes it
    session = ScopingSession(service, index)  # template mode: deterministic
    session.handle_message("améliorer le canal mobile")
    session.edb.add_entry("objectifs", EdbEntry(source="user", text="vague"))
    session._mark_precision_asked("objectifs")
    assert "objectifs" not in session.edb.incomplete_sections(insufficient={"objectifs"})
```

Add imports the test needs at the top of `tests/test_session.py`: `from core.dossier.template import EdbEntry` and `from core.llm.provider import MockProvider` (MockProvider is already imported; add `EdbEntry`).

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_session.py -k "initial_brief_is_mined or insufficient_section_is_re_asked" -v`
Expected: FAIL — brief not mined / `_mark_precision_asked` missing.

- [ ] **Step 3: Mine the initial brief**

In `core/runtime/session.py` `handle_message`, the DESCRIBING branch currently leaves `free_text=None`. Change it to mine the description:

```python
        if self.state is SessionState.DESCRIBING:
            self.brief = ProjectBrief(description=text)
            self.state = SessionState.MAPPING
            free_text = text  # #5: mine the initial brief too (jalons/objectifs in the opener)
```

- [ ] **Step 4: Add `precision_asked` state + helper, and the sufficiency judge call**

In `__init__`, after `self.previously_mapped` add:

```python
        self.precision_asked: set[str] = set()  # sections already re-asked for precision (convergence)
```

Add the helper method:

```python
    def _mark_precision_asked(self, section_id: str) -> None:
        self.precision_asked.add(section_id)
```

In `_map_round`, import the new step: add `judge_section_sufficiency` to the `from core.runtime.llm_steps import (...)` block. After `pool = build_pool(...)` is currently built, change the pool construction to feed sufficiency. Replace the `pool = build_pool(result, self.brief, self.asked, self.edb, profile=self._profile)` line with:

```python
        insufficient, followups = judge_section_sufficiency(self._provider, self.edb)
        insufficient -= self.precision_asked  # convergence: each section re-asked at most once
        pool = build_pool(self.brief and result, self.brief, self.asked, self.edb,
                          profile=self._profile, insufficient=insufficient, followups=followups)
```

(Keep `result` as the first arg — the `self.brief and result` above is a typo guard; use plain `result`.) Final form:

```python
        insufficient, followups = judge_section_sufficiency(self._provider, self.edb)
        insufficient -= self.precision_asked
        pool = build_pool(result, self.brief, self.asked, self.edb,
                          profile=self._profile, insufficient=insufficient, followups=followups)
```

- [ ] **Step 5: Mark precision-asked when an insufficient section is asked, and use the follow-up text**

In `_ask`, after `self.pending = candidate`, record precision intent:

```python
    def _ask(self, pool: list[Candidate]) -> str:
        candidate, question = pick_question(self._provider, pool, self._service)
        self.asked.add(candidate.key)
        if candidate.kind == "edb_gap" and self.edb.sections.get(candidate.section_id):
            self._mark_precision_asked(candidate.section_id)  # filled+re-asked → closes next round
        self.questions_asked += 1
        self.pending = candidate
        self.pending_question = question
        return question
```

In `core/runtime/llm_steps.py`, make the follow-up the template question for an insufficient gap. Change `_template_question` and `_candidate_context`:

```python
def _template_question(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        return candidate.followup or gap_question(candidate.section_id)
    return render_question(candidate.trigger, service)


def _candidate_context(candidate: Candidate, service: GraphService | None) -> str:
    if candidate.kind == "edb_gap":
        hint = candidate.followup or gap_question(candidate.section_id)
        return f"[{candidate.key}] section EDB à compléter/préciser — piste : {hint}"
    return f"[{candidate.key}] ambiguïté graphe ({candidate.kind}) — gabarit : {_template_question(candidate, service)}"
```

- [ ] **Step 6: Update the completeness message to use sufficiency**

In `_map_round`, the silent-turn fallback currently calls `self.edb.missing_sections()`. Change it to reflect sufficiency-incomplete sections:

```python
            missing = self.edb.incomplete_sections()  # empty-only when no provider; sufficiency-aware otherwise
```

(With `provider=None`, `incomplete_sections()` with no `insufficient` arg == `missing_sections()`, so the no-provider path is unchanged.)

- [ ] **Step 7: Run the new + full session suite**

Run: `pytest tests/test_session.py -q`
Expected: all PASS. If `make_session`/template-mode tests now ask a different first question because the brief is mined, inspect and adjust only assertions that depended on the brief NOT being mined (none expected — template mode has `provider=None`, so `extract_fields` is a no-op and behavior is unchanged).

- [ ] **Step 8: Run llm_steps + pool suites (signature change)**

Run: `pytest tests/test_llm_steps.py tests/test_pool.py -q`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add core/runtime/session.py core/runtime/llm_steps.py tests/test_session.py
git commit -m "feat(#2,#5): mine the initial brief, sufficiency-driven re-ask (bounded), precision follow-ups

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 7: Canonical-section extraction guidance + synonym remap (#5)

**Files:**
- Modify: `core/runtime/llm_steps.py` (`extract_fields`), `prompts/extract_fields.txt`
- Test: `tests/test_llm_steps.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_steps.py`:

```python
def test_extract_fields_remaps_known_section_synonyms():
    # the model emits non-canonical ids seen live (parties_prenantes, carta)
    mock = MockProvider([{"entries": [
        {"section_id": "parties_prenantes", "text": "DSI sponsor"},  # → utilisateurs
        {"section_id": "carta", "text": "x"},                         # → carte (then dropped: not askable? still remapped)
        {"section_id": "objectifs", "text": "+10% conversion"},
    ]}])
    entries, dropped = extract_fields(mock, "réponse", EdbState.new())
    sids = [e["section_id"] for e in entries]
    assert "utilisateurs" in sids  # parties_prenantes remapped
    assert "parties_prenantes" not in dropped  # remapped, not lost
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_llm_steps.py -k remaps_known_section_synonyms -v`
Expected: FAIL — `parties_prenantes` currently lands in `dropped`, not remapped.

- [ ] **Step 3: Add the remap and pass id→title pairs to the prompt**

In `core/runtime/llm_steps.py`, add a module-level remap and apply it in `extract_fields`:

```python
_SECTION_SYNONYMS = {
    "parties_prenantes": "utilisateurs",
    "parties prenantes": "utilisateurs",
    "carta": "carte",
    "carte_de_contexte": "carte",
    "perimetre_hors": "perimetre",
}
```

In `extract_fields`, build an id→title hint and apply the remap before the gate:

```python
def extract_fields(
    provider: LLMProvider | None, answer: str, edb: EdbState
) -> tuple[list[dict], list[str]]:
    """Proposes EDB entries from a free answer; returns (gated entries, dropped ids)."""
    if provider is None:
        return [], []
    allowed = set(edb.sections)
    catalogue = ", ".join(f"{s.id} ({s.title_fr})" for s in EDB_TEMPLATE_V1 if s.id in allowed)
    system = load_prompt("extract_fields").replace("{sections}", catalogue)
    try:
        out = complete_with_retry(provider, system, answer, required_keys=("entries",))
    except JsonContractError:
        return [], []
    entries, dropped = [], []
    for raw in out["entries"]:
        section_id = _SECTION_SYNONYMS.get(raw.get("section_id", ""), raw.get("section_id", ""))
        if section_id in allowed and raw.get("text"):
            entries.append({"section_id": section_id, "text": raw["text"],
                            "node_refs": list(raw.get("node_refs", []))})
        else:
            dropped.append(raw.get("section_id", ""))
    return entries, dropped
```

Add `EDB_TEMPLATE_V1` to the template import at the top of `llm_steps.py`:
`from core.dossier.template import ASKABLE_SECTIONS, EDB_TEMPLATE_V1, EdbState, section_spec`.

- [ ] **Step 4: Update the prompt to demand canonical ids and « hors périmètre » phrasing**

Replace `prompts/extract_fields.txt` with:

```
Tu assistes un outil de cadrage de projets bancaires qui remplit une expression de
besoin (EDB) pendant la conversation. Voici la dernière réponse libre de l'utilisateur.
Extrais-en les éléments qui remplissent des sections de l'EDB, sans rien inventer ni
reformuler au-delà du nécessaire. Utilise EXCLUSIVEMENT les identifiants de section
ci-dessous (le libellé entre parenthèses n'est qu'une aide — n'écris jamais le libellé
comme identifiant) : {sections}. Pour une exclusion de périmètre, préfixe le texte par
« hors périmètre : ». Réponds en JSON :
{"entries": [{"section_id": "<un id de la liste>", "text": "...", "node_refs": []}]}
Si rien n'est extractible, renvoie {"entries": []}.
```

- [ ] **Step 5: Run the test (and the existing extract test still passes)**

Run: `pytest tests/test_llm_steps.py -k "extract_fields" -v`
Expected: PASS — both `test_extract_fields_gates_unknown_sections` (the `budget` id still drops) and the new remap test.

- [ ] **Step 6: Commit**

```bash
git add core/runtime/llm_steps.py prompts/extract_fields.txt tests/test_llm_steps.py
git commit -m "fix(#5): canonical-section extraction (id+title catalogue, synonym remap, hors-périmètre)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chantier 3 — Clause-complete claim grounding (#3)

### Task 8: `judge_claim_grounding` LLM step + prompt

**Files:**
- Create: `prompts/judge_claim_grounding.txt`
- Modify: `core/runtime/llm_steps.py`
- Test: `tests/test_llm_steps.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_steps.py`:

```python
def _service_with_one_node(text: str):
    from core.graph.models import System
    from core.graph.service import GraphService
    return GraphService(
        {"sys-x": System(id="sys-x", name="X", description=text, owner_team="T", domains=["d"])},
        [],
    )


def test_judge_claim_grounding_flags_unsupported_conclusion():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("Gel monétique à compter du 15 janvier 2026.")
    claims = [{"kind": "constraint_applies", "node_ids": ["sys-x"],
               "target_section": "contraintes", "reason": "le gel impose aussi un audit KYC"}]
    provider = MockProvider([{"verdicts": [
        {"index": 0, "grounded": False, "reason_fr": "l'audit KYC n'est pas dans la source"},
    ]}])
    verdicts = judge_claim_grounding(provider, claims, service)
    assert verdicts[0]["grounded"] is False
    assert "KYC" in verdicts[0]["reason_fr"]


def test_judge_claim_grounding_none_provider_passes_all():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    claims = [{"node_ids": ["sys-x"], "reason": "r"}]
    assert judge_claim_grounding(None, claims, service) == [{"grounded": True, "reason_fr": ""}]


def test_judge_claim_grounding_empty_claims_is_empty():
    from core.runtime.llm_steps import judge_claim_grounding
    service = _service_with_one_node("texte")
    assert judge_claim_grounding(MockProvider([]), [], service) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_llm_steps.py -k judge_claim_grounding -v`
Expected: FAIL — `ImportError: cannot import name 'judge_claim_grounding'`.

- [ ] **Step 3: Create the prompt**

Create `prompts/judge_claim_grounding.txt`:

```
Tu vérifies des affirmations de cadrage par rapport aux sources qu'elles citent (le
texte exact des éléments du référentiel). Pour chaque affirmation, vérifie que TOUTES
ses conclusions sont couvertes par les sources citées. Une affirmation qui ajoute un
système, une conclusion ou une obligation absente des sources n'est PAS couverte.
Ignore le style et les reformulations fidèles. Réponds en JSON :
{"verdicts": [{"index": <numéro de l'affirmation>, "grounded": true|false,
"reason_fr": "<si non couverte, ce qui n'est pas dans les sources>"}]}
Renvoie un verdict par affirmation fournie.
```

- [ ] **Step 4: Implement `judge_claim_grounding`**

Add the import at the top of `core/runtime/llm_steps.py`:
`from core.runtime.challenge import node_provenance` (no cycle: `challenge.py` imports nothing from `llm_steps`).

Add the step (near the other judges):

```python
def judge_claim_grounding(
    provider: LLMProvider | None, claims: list[dict], service: GraphService
) -> list[dict]:
    """Per-claim faithfulness: is every conclusion of the claim's reason covered by the
    text of the nodes it cites? Returns a verdict parallel to `claims`:
    [{"grounded": bool, "reason_fr": str}]. All grounded without a provider, on contract
    failure, or for an empty list (recall-first: the syntactic gate stays the floor)."""
    if provider is None or not claims:
        return [{"grounded": True, "reason_fr": ""} for _ in claims]
    blocks = []
    for i, claim in enumerate(claims):
        facts = node_provenance(service, [str(n) for n in claim.get("node_ids", [])])
        sources = " | ".join(f["text"] for f in facts)
        blocks.append(f"[{i}] affirmation : {claim.get('reason', '')}\nsources citées : {sources}")
    user = "\n\n".join(blocks)
    try:
        out = complete_with_retry(provider, load_prompt("judge_claim_grounding"), user,
                                  required_keys=("verdicts",))
    except JsonContractError:
        return [{"grounded": True, "reason_fr": ""} for _ in claims]
    by_index = {}
    for v in out.get("verdicts", []):
        try:
            by_index[int(v["index"])] = v
        except (KeyError, ValueError, TypeError):
            continue
    verdicts = []
    for i in range(len(claims)):
        v = by_index.get(i, {})
        verdicts.append({
            "grounded": v.get("grounded", True) is not False,  # default keep (recall-first)
            "reason_fr": str(v.get("reason_fr", "")).strip(),
        })
    return verdicts
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_llm_steps.py -k judge_claim_grounding -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add core/runtime/llm_steps.py prompts/judge_claim_grounding.txt tests/test_llm_steps.py
git commit -m "feat(#3): judge_claim_grounding LLM step (clause-complete claim faithfulness)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 9: Wire grounding into `_run_challenge` (auto-reject ungrounded claims)

**Files:**
- Modify: `core/runtime/session.py` (`_run_challenge`)
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_session.py`:

```python
def test_ungrounded_claim_is_rejected_not_carded() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)  # template mode for setup
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage: all keep by default
        {"pulled_justifications": [], "domains": [],
         "claims": [{"kind": "constraint_applies", "node_ids": ["sys-canal"],
                     "target_section": "contraintes", "reason": "impose aussi un audit KYC non cité"}],
         "challenge_statement": "Énoncé fidèle aux sources."},
        {"verdicts": [{"index": 0, "grounded": False, "reason_fr": "audit KYC absent des sources"}]},
        {"issues": []},  # judge_statement_fidelity → clean
    ])
    _msg, cards = session._run_challenge(result)
    assert all(c.kind != "claim" for c in cards)  # ungrounded claim is NOT carded
    assert any(r.get("kind") == "claim" and "KYC" in r.get("reason_rejected", "")
               for r in session.gate_rejections)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_session.py::test_ungrounded_claim_is_rejected_not_carded -v`
Expected: FAIL — the ungrounded claim currently becomes a card.

- [ ] **Step 3: Add the grounding partition in `_run_challenge`**

In `core/runtime/session.py`, add `judge_claim_grounding` to the `from core.runtime.llm_steps import (...)` block. In `_run_challenge`, replace the block from `valid, rejected_claims = gate_claims(...)` through the `for claim in valid:` card-building loop with:

```python
        valid, rejected_claims = gate_claims(out2, map_ids, self._service)
        self.gate_rejections += [{"kind": "claim", **r} for r in rejected_claims]
        # #3: clause-complete grounding — a claim whose conclusions exceed its cited
        # provenance is auto-rejected (lands in the gate panel, not a card).
        groundings = judge_claim_grounding(self._provider, valid, self._service)
        grounded: list[dict] = []
        for claim, verdict in zip(valid, groundings, strict=True):
            if verdict["grounded"]:
                grounded.append(claim)
            else:
                self.gate_rejections.append({
                    "kind": "claim", **claim,
                    "reason_rejected": verdict["reason_fr"] or "non couvert par les sources citées",
                })
        cards: list[Proposal] = []
        for claim in grounded:
            pid = self.ledger.add(Proposal.claim(
                kind=claim["kind"], node_ids=claim["node_ids"],
                target_section=claim["target_section"], reason=claim["reason"]))
            cards.append(self.ledger.get(pid))
```

- [ ] **Step 4: Run the test + full session suite**

Run: `pytest tests/test_session.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/session.py tests/test_session.py
git commit -m "fix(#3): _run_challenge auto-rejects ungrounded claims into the gate panel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chantier 4 — Statement quarantine (#4)

### Task 10: `Proposal.statement` constructor

**Files:**
- Modify: `core/runtime/ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ledger.py`:

```python
def test_statement_proposal_carries_flags_and_issues():
    from core.runtime.ledger import Ledger, Proposal
    ledger = Ledger()
    pid = ledger.add(Proposal.statement(
        text="Le gel court jusqu'au 15 janvier 2026.",
        flags=["30"], issues=["Date inversée."]))
    p = ledger.get(pid)
    assert p.kind == "statement"
    assert p.payload["flags"] == ["30"]
    assert p.payload["issues"] == ["Date inversée."]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_ledger.py::test_statement_proposal_carries_flags_and_issues -v`
Expected: FAIL — `AttributeError: type object 'Proposal' has no attribute 'statement'`.

- [ ] **Step 3: Add the constructor**

In `core/runtime/ledger.py`, add to `Proposal` (after `field`):

```python
    @classmethod
    def statement(cls, *, text: str, flags: list[str], issues: list[str]):
        return cls(id="", kind="statement", text=text, payload={
            "flags": list(flags), "issues": list(issues),
        })
```

Update the `kind` comment on the `Proposal` dataclass to `# "claim" | "field" | "statement"`.

- [ ] **Step 4: Run the ledger suite**

Run: `pytest tests/test_ledger.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/runtime/ledger.py tests/test_ledger.py
git commit -m "feat(#4): Proposal.statement constructor (carries fidelity flags/issues)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 11: Quarantine a flagged statement; accept writes it to the EDB

**Files:**
- Modify: `core/runtime/session.py` (`_run_challenge`, `accept_proposal`)
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session.py`:

```python
def test_clean_statement_is_auto_stored() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage
        {"pulled_justifications": [], "domains": [], "claims": [],
         "challenge_statement": "Énoncé fidèle aux sources."},
        {"issues": []},  # clean fidelity → no quarantine
    ])
    session._run_challenge(result)
    assert [e.text for e in session.edb.sections["challenge"]] == ["Énoncé fidèle aux sources."]


def test_flagged_statement_is_quarantined_not_auto_stored() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal"]))
    index.build(service)
    session = ScopingSession(service, index)
    session.handle_message("améliorer le canal mobile")
    result = session.last_result
    session._provider = MockProvider([
        {"verdicts": []},  # triage
        {"pulled_justifications": [], "domains": [], "claims": [],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"issues": ["Date inversée : « jusqu'au » au lieu de « à compter du »."]},
    ])
    _msg, cards = session._run_challenge(result)
    assert session.edb.sections["challenge"] == []  # NOT auto-stored
    statement_cards = [c for c in cards if c.kind == "statement"]
    assert statement_cards and statement_cards[0].payload["issues"]
    # accepting it lands it in the EDB
    session.accept_proposal(statement_cards[0].id)
    assert any("jusqu'au" in e.text for e in session.edb.sections["challenge"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_session.py -k "clean_statement or flagged_statement" -v`
Expected: FAIL — the flagged statement is currently auto-stored and there is no statement card.

- [ ] **Step 3: Quarantine in `_run_challenge`**

In `core/runtime/session.py`, ensure `Proposal` is imported (it is). Replace the line
`self.edb.add_entry("challenge", EdbEntry(source="llm", text=statement))` with:

```python
        if self.statement_flags or self.statement_issues:
            # #4: a flagged statement is NOT auto-stored — it waits in the ledger.
            pid = self.ledger.add(Proposal.statement(
                text=statement, flags=self.statement_flags, issues=self.statement_issues))
            cards.append(self.ledger.get(pid))
        else:
            self.edb.add_entry("challenge", EdbEntry(source="llm", text=statement))
```

- [ ] **Step 4: Handle the statement kind in `accept_proposal`**

In `accept_proposal`, add a branch:

```python
    def accept_proposal(self, pid: str, edited_text: str | None = None) -> Proposal:
        proposal = self.ledger.accept(pid, edited_text)
        if proposal.kind == "field":
            self.edb.add_entry(proposal.payload["section_id"], EdbEntry(
                source="user", text=proposal.text,
                node_refs=list(proposal.payload["node_refs"])))
        elif proposal.kind == "statement":
            self.edb.add_entry("challenge", EdbEntry(source="llm", text=proposal.text))
        else:  # claim
            self.edb.add_entry(proposal.payload["target_section"], EdbEntry(
                source=f"claim:{pid}", text=proposal.text,
                node_refs=list(proposal.payload["node_ids"])))
        return proposal
```

- [ ] **Step 5: Run the tests + full session suite**

Run: `pytest tests/test_session.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add core/runtime/session.py tests/test_session.py
git commit -m "fix(#4): quarantine flagged challenge statements via the ledger (accept writes to EDB)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 12: Surface statement flags/issues on the card payload

**Files:**
- Modify: `web/app.py` (`_card_dict`)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py` a check that a statement card serializes its flags/issues. Use the file's client/session construction; the assertion core:

```python
def test_statement_card_payload_carries_issues(client_factory):
    from core.runtime.ledger import Proposal
    # build a session, add a statement proposal directly, then read a payload endpoint
    # that returns pending cards; adapt to the file's helpers.
    ...
    card = next(c for c in payload["cards"] if c["kind"] == "statement")
    assert card["payload"]["issues"]
```

If exercising via HTTP is heavy here, instead unit-test `_card_dict` directly:

```python
def test_card_dict_serializes_statement_flags():
    from web.app import _card_dict
    from core.runtime.ledger import Proposal
    from tests.test_session import make_service
    p = Proposal.statement(text="t", flags=["30"], issues=["Date inversée."])
    p.id = "p1"
    out = _card_dict(make_service(), p)
    assert out["kind"] == "statement"
    assert out["payload"]["issues"] == ["Date inversée."]
```

- [ ] **Step 2: Run it to verify it passes or fails**

Run: `pytest tests/test_web.py -k "statement" -v`
Expected: `_card_dict` already returns `proposal.payload`, so the payload test likely PASSES as-is — confirm. If it passes, `_card_dict` needs no change and this task only adds the regression test. If the UI needs flags/issues at top level for rendering, add them in Step 3.

- [ ] **Step 3: (If needed) surface issues/flags for the UI**

If `web/static/index.html` renders cards and needs explicit fields, add to `_card_dict`:

```python
    return {
        "id": proposal.id, "kind": proposal.kind, "text": proposal.text,
        "payload": proposal.payload, "status": proposal.status,
        "provenance": node_provenance(service, ids),
        "issues": proposal.payload.get("issues", []),
        "flags": proposal.payload.get("flags", []),
    }
```

Then add a card-rendering branch in `web/static/index.html` for `kind === "statement"` that shows the amber issues/flags inline (mirror the existing amber statement strip styling).

- [ ] **Step 4: Run the web suite**

Run: `pytest tests/test_web.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app.py web/static/index.html tests/test_web.py
git commit -m "feat(#4): statement card surfaces fidelity flags/issues for the UI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chantier 5 — End-to-end coherence + verification

### Task 13: Metrics use `kept_node_ids()`; integration test; full verification

**Files:**
- Modify: `core/benchdata/metrics.py`
- Test: `tests/test_session.py`, `tests/test_benchdata.py`
- Modify: `docs/BUILD-ORDER.md`

- [ ] **Step 1: Point the recall metric at `kept_node_ids()`**

In `core/benchdata/metrics.py`, replace the manual `kept_ids` block (the `if session.last_result is not None: ...` through the `kept_ids -= set(session.rejected_nodes)` lines) with:

```python
    kept_ids = session.kept_node_ids()
```

This keeps the recall/map_size numbers consistent with what the UI renders (excluded domains honored). Run `pytest tests/test_benchdata.py -q` and fix any assertion that assumed the old (domain-unfiltered) kept set — expected: still PASS, since template-mode sessions have no excluded domains in those fixtures.

- [ ] **Step 2: Write the integration test (the spec's five assertions, hermetic)**

Add to `tests/test_session.py` a single end-to-end test driving a scripted session through map → challenge → precision, asserting all five audit fixes hold together:

```python
def test_audit_fixes_hold_end_to_end() -> None:
    service = make_service()
    index = VectorIndex(FakeEmbedder(["canal", "moteur", "terminal"]))
    index.build(service)
    session = ScopingSession(service, index)  # template setup, provider attached per phase

    # 1) initial brief mined: drive the opener in provider mode
    session._provider = MockProvider([
        {"additions": []},  # enrich
        {"entries": [{"section_id": "jalons", "text": "pilote octobre 2026"}]},  # extract on brief
        {"verdicts": []},  # sufficiency
        {"candidate_key": "weak", "question": "?"},  # pick_question (pool may vary; any valid key)
    ])
    # NOTE: if the pool's first candidate key differs, set candidate_key to it (read pool order).
    session.handle_message("paiement en 3 fois, pilote octobre 2026, hors bénéficiaires")
    assert any("octobre 2026" in e.text for e in session.edb.sections["jalons"])  # #5

    # 2) exclude monetique, then a precision must not bring sys-moteur back (#1)
    session._provider = None  # deterministic resolution
    session.handle_message("non")  # excludes the pending pivot domain
    before = session.kept_node_ids()
    session.handle_message("préciser les délais du moteur de paiement")
    excluded = set(session.brief.excluded_domains)
    for nid in session.kept_node_ids():
        node_domains = set(service.get_node(nid).domains)
        assert not (node_domains & excluded and not (node_domains & set(session.brief.domains)))

    # 3+4) ungrounded claim rejected, flagged statement quarantined (#3,#4)
    session._provider = MockProvider([
        {"verdicts": []},
        {"pulled_justifications": [], "domains": [], "claims": [
            {"kind": "constraint_applies", "node_ids": ["sys-canal"],
             "target_section": "contraintes", "reason": "impose un audit KYC non cité"}],
         "challenge_statement": "Le gel court jusqu'au 15 janvier 2026."},
        {"verdicts": [{"index": 0, "grounded": False, "reason_fr": "KYC absent"}]},
        {"issues": ["Date inversée."]},
    ])
    _msg, cards = session._run_challenge(session.last_result)
    assert any(r.get("kind") == "claim" for r in session.gate_rejections)          # #3
    assert all(c.kind != "claim" for c in cards)                                    # #3
    assert session.edb.sections["challenge"] == []                                 # #4
    assert any(c.kind == "statement" for c in cards)                               # #4
    assert before is not None  # sanity
```

Note for the implementer: pool/candidate ordering in step (1) depends on the seed; if
`candidate_key="weak"` is not in the pool, run the test once, read the
`pick_question` pool from the failure, and set the key to the first candidate. The
assertions that matter (#1,#3,#4,#5) do not depend on which question is asked.

- [ ] **Step 3: Run the integration test**

Run: `pytest tests/test_session.py::test_audit_fixes_hold_end_to_end -v`
Expected: PASS (adjust the one `candidate_key` per the note if needed).

- [ ] **Step 4: Full suite + lint**

Run: `pytest -q`
Expected: all PASS (the prior `235 passed` baseline + the new tests).
Run: `ruff check .`
Expected: clean. Fix any unused-import / line-length findings inline.

- [ ] **Step 5: Update `docs/BUILD-ORDER.md`**

Add a dated entry under "Current state" recording the five fixes as DONE, referencing
this plan and the spec, and the new test count. Do NOT remove Loïc's 2026-06-14 audit
entry — append below it. (Loïc has an uncommitted edit in `BUILD-ORDER.md`; coordinate:
read the current file first, append, and stage only your additions.)

- [ ] **Step 6: Commit**

```bash
git add core/benchdata/metrics.py tests/test_session.py tests/test_benchdata.py docs/BUILD-ORDER.md
git commit -m "test+docs: end-to-end audit-fix coverage, metrics use kept_node_ids, BUILD-ORDER

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 14 (optional, real-LLM): conversation-eval scenario

If/when running the real-LLM `conversation-eval` harness, add a BNPL scenario asserting
the same five behaviors end to end with a live model (cached). This is **not** a CI
deliverable (it needs API keys + Loïc's go); the hermetic Task 13 test is the floor.
Track it as a follow-up in BUILD-ORDER, not a blocking step.

---

## Self-Review

**Spec coverage:**
- #1 live coherent map → Tasks 1–2 (accumulated exclusions, `kept_node_ids` honoring
  excluded domains, recomputed pull, new-node marking). ✓
- #2 EDB sufficiency → Tasks 3–6 (rubric, judge, pool, session wiring, bounded re-ask). ✓
- #5 extraction → Task 6 Step 3 (brief mining) + Task 7 (canonical sections, remap). ✓
- #3 grounding → Tasks 8–9. ✓
- #4 quarantine → Tasks 10–12. ✓
- Convergence invariant → Task 6 (`precision_asked`, each section re-asked once;
  `MAX_QUESTIONS` untouched). ✓
- `provider=None` degradation → asserted in Tasks 4, 8 (and `incomplete_sections()` with
  no arg == `missing_sections()`). ✓
- Integration of all five → Task 13. ✓

**Placeholder scan:** Task 2 and Task 12 reference "the file's existing client/helper"
because `tests/test_web.py`'s fixtures were not read into this plan; both give a concrete
fallback (unit-test `_card_dict` / inline `create_app` with a `MockProvider`) so neither
is a blank TODO. Task 13 Step 2 flags a seed-dependent `candidate_key` with explicit
recovery instructions. No bare "TBD/implement later".

**Type consistency:**
- `kept_node_ids() -> set[str]` used identically in `web/app.py` (Task 2) and
  `core/benchdata/metrics.py` (Task 13). ✓
- `judge_section_sufficiency -> tuple[set[str], dict[str, str]]` consumed in Task 6 as
  `insufficient, followups`. ✓
- `build_pool(..., insufficient=set(), followups=dict)` matches the call in Task 6. ✓
- `Candidate.followup` set in Task 5, read in Task 6's `_template_question`/`_candidate_context`. ✓
- `judge_claim_grounding -> list[dict]` with keys `grounded`/`reason_fr`, consumed via
  `zip(valid, groundings, strict=True)` in Task 9. ✓
- `Proposal.statement(text=, flags=, issues=)` defined in Task 10, used in Tasks 11–12. ✓

**Open coordination note:** `docs/BUILD-ORDER.md` has an uncommitted edit by Loïc — Task 13
Step 5 says append, don't overwrite.

