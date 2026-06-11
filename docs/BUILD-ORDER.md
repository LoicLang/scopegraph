---
summary: short source of truth for the current state and the immediate next chantier
read_when:
  - starting a work session
  - checking what to do next
  - re-scoping before coding
---

# Build order

## Current state (2026-06-11, end of session)

- Repo bootstrapped: structure, pyproject, CI (ruff + pytest, green), pre-commit.
- Founding docs: `docs/project-kickoff.md` (its §4 schema superseded), MVP design spec
  `docs/specs/2026-06-09-scopegraph-mvp-design.md`, fine-grain schema spec
  `docs/specs/2026-06-10-graph-schema-fine-grain-design.md`.
- **W1 foundations DONE** (branch `w1-foundations`, executed via subagent-driven-development
  from `docs/plans/2026-06-10-week1-foundations.md`):
  - ADR 0000 (pivot) + ADR 0001 (schema v1 frozen: 7 node types, 7 edge types, topology
    matrix, domains as ecosystem data).
  - `core/graph/`: Pydantic models + TOPOLOGY, fail-fast loader (vocabulary, topology,
    PART_OF cardinality, cancelled-project rules), GraphService (`get_node`, `neighbors`,
    `k_hop` with path provenance). 37 hermetic tests, ruff clean.
  - Seed: 72 fictional French banking-IT nodes (9 systems, 24 features, 6 business objects,
    7 projects, 8 decisions, 12 constraints, 6 risks), 100 edges, 7 deliberate traps — each
    trap has an integration test in `tests/test_seed.py`.
  - README v1 · 6 eval cases drafted in `docs/eval/cases.md`.
- **Graph viewer** (2026-06-10): `./scripts/graph-viz` generates an interactive standalone
  Cytoscape view of the graph (filters, search incl. aliases, highlight mode). Built on
  `core/viz/payload.py` — the data seam the W2 web Context Map pane and the W4 scoping
  highlight will reuse. Spec: `docs/specs/2026-06-10-graph-viz-design.md` (amends the MVP
  spec: Context Map medium = interactive viewer; Mermaid deferred to the dossier export).

- **W2 retrieval + MAPPING + first screens DONE** (2026-06-11, branch `w2-retrieval-web`,
  subagent-driven from `docs/plans/2026-06-11-week2-retrieval-mapping-web.md`; spec:
  `docs/specs/2026-06-10-week2-retrieval-mapping-web-design.md`):
  - `core/retrieval/`: Embedder Protocol (SentenceTransformers lazy via the `embeddings`
    extra + FakeEmbedder), Chroma cosine index with fingerprint staleness, hybrid scorer
    (semantic + domain boost + 1–2 hop expansion with edge-path provenance, deterministic
    type-priority tie-break). Eval cases 1–2 are unit tests: the TPE 2-hop trap passes.
  - `core/runtime/`: ProjectBrief (the accumulating query), triggers T1/T2/T3 with
    asked-log + precedence, French template questions, ScopingSession (6-state enum,
    DESCRIBING→MAPPING active, question cap, guaranteed convergence; hedge answers
    never confirm a domain).
  - `web/`: FastAPI session endpoints (map payload rides the message response) + one
    Alpine/Cytoscape page (chat + live Context Map, anchors vs expanded styling) on the
    extended `core/viz/payload.py` seam (`only` + `annotations`).
  - `scripts/retrieval-smoke`: real-model calibration bench over the 6 eval briefs (not
    in CI — constants in `core/retrieval/config.py` are tuned by reading its output).
  - 102 hermetic tests, ruff clean. Run the app: `pip install -e ".[embeddings]"` then
    `uvicorn --factory web.app:create_app --reload`.

## Next chantier — Week 3 (LLM providers + grounding + challenge)

Per MVP spec §8: `LLMProvider` Protocol (Mistral default, DeepSeek dev, Mock hermetic) ·
grounding gate (every claim cites a node ID or is rejected, visibly) · propose/validate/
apply ledger · CHALLENGING + SCOPING states (already declared, currently raising
NotImplementedError) · LLM rephrasing of the W2 template questions (templates stay as
permanent fallback). Brainstorm/plan first — no W3 spec exists yet.

Calibration TODO before or during W3: run `./scripts/retrieval-smoke` once (downloads the
MiniLM model) and read the rankings on the 6 briefs; adjust `core/retrieval/config.py`
constants in a dedicated commit if a case ranks poorly.

## Later

W4 dossier + Context Map polish + write-back + scripted demo + eval run. See MVP spec §8.

W4 note (decided in session, 2026-06-10): write-back needs a small TOPOLOGY-extension ADR —
allow `Project → DEPENDS_ON → System` and `Project → OPERATES_ON → BusinessObject` so an
in-flight project can express what it touches (collision detection). New `Feature` nodes are
NOT created at scoping write-back (intention ≠ reality); they enter the graph at delivery,
via `PRODUCED` (see fine-grain spec §6).
