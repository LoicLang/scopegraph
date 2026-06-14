---
summary: design for a context-aware interview runtime, Gemini 3.5 Flash provider, and matched Mistral/Gemini retest
read_when:
  - implementing Gemini as a scopegraph provider
  - changing question relevance, negative retrieval context, or post-challenge delta triage
  - comparing Mistral and Gemini on real conversations
status: approved (Loïc, 2026-06-14)
---

# Context-aware interview + Gemini comparison — design

Source: the post-fix real-user retest recorded in `docs/BUILD-ORDER.md`, followed by
Loïc's approval on 2026-06-14. The goal is not to hide runtime defects behind a stronger
model: fix the missing context first, then compare Mistral and Gemini fairly.

## Success criteria

The same two project briefs are run uncached with `mistral-small-latest` and
`gemini-3.5-flash`:

1. BNPL e-commerce card payment pilot;
2. temporary card-limit increase for travel.

For each run, record question relevance, final-map pollution, grounded claims offered,
automatic and manual claim rejections, statement fidelity, and EDB completion. The
runtime must preserve its existing deterministic fallbacks and hermetic test suite.

## Decisions

### 1. Gemini is a first-class provider

Add `GeminiProvider` behind the existing `LLMProvider` Protocol, using Google's official
`google-genai` Python SDK and model code `gemini-3.5-flash`. It sends the existing system
and user messages with temperature 0 and requests JSON output. SDK imports remain lazy
and confined to `core/llm/`.

`SCOPEGRAPH_LLM_PROVIDER=gemini` resolves `GEMINI_API_KEY`. The real-model benchmark
scripts accept `--provider gemini`. Gemini is the only model used for every LLM step in a
Gemini run: enrichment, extraction, question selection, triage, claims, grounding,
fidelity, and PM persona.

### 2. Question selection receives project context and may decline a graph pivot

`pick_question` receives:

- the accumulated project brief;
- the current accepted EDB;
- confirmed and excluded domains;
- all graph and EDB-gap candidates in one pool.

The model may return either one offered candidate key or `skip_graph`. `skip_graph` is
valid only when at least one EDB-gap candidate exists; the runtime then asks the
highest-priority EDB gap deterministically. An unknown key still falls back to the first
candidate. The model never invents a new topic.

Graph candidates are no longer hard-separated from gaps before selection. The existing
two-consecutive-graph-question cadence remains a deterministic ceiling: once reached,
the runtime offers only gap candidates for that turn.

### 3. Excluded questions do not become positive retrieval evidence

`ProjectBrief` keeps the full QA transcript for audit and prompts, but retrieval uses a
separate positive-context projection:

- the initial user description;
- answers to EDB-gap questions;
- answers to confirmed or unclear graph pivots;
- answers to excluded pivots, without the assistant's question text;
- accepted enrichment chips.

For an excluded pivot, only the user's answer enters retrieval; the question that named
the irrelevant domain does not. This prevents a bad question about beneficiaries from
making beneficiaries more retrievable on the next turn.

Explicit exclusions written in the opening brief or free answers are also interpreted
against the known domain vocabulary. A new gated LLM step proposes domain slugs to
exclude from the user's text; the runtime accepts only existing slugs and accumulates
them in `brief.excluded_domains`. Contract failure is a no-op.

### 4. New post-challenge nodes receive delta triage

After the initial challenge, each live retrieval computes:

`new_ids = current retrieval ids - previously_mapped - rejected_nodes`.

Only these new nodes are sent to the existing triage prompt together with the complete
brief. Rejected new nodes accumulate in `rejected_nodes`; kept new nodes remain annotated
`nouveau`. Governance pull is recomputed after delta triage. A triage contract failure is
recall-first: new nodes stay visible and the failure is recorded in `gate_rejections`.

This replaces the previous policy of displaying all new nodes without relevance review.

### 5. Challenge prose is derived from grounded claims

The claims call still proposes structured claims, but its free-prose statement is not
trusted as the final challenge. After syntactic and semantic grounding:

- the runtime renders the accepted grounded claim texts plus the project's own facts;
- a final `render_challenge` LLM step writes the user-facing challenge from only that
  material;
- the existing number guard and statement-fidelity judge remain;
- a flagged statement stays quarantined in the ledger.

If rendering fails, use a deterministic French summary of grounded claim texts. If no
grounded claim remains, state that no additional graph-backed challenge was established.

## Components

| Component | Responsibility |
|---|---|
| `core/llm/gemini.py` | Official Gemini transport and JSON decoding |
| `core/llm/factory.py` | Resolve Gemini from environment |
| `core/runtime/brief.py` | Full audit transcript plus positive retrieval projection |
| `core/runtime/llm_steps.py` | Context-aware question choice, exclusion extraction, challenge rendering |
| `core/runtime/session.py` | Candidate policy, delta triage, grounded challenge orchestration |
| `prompts/*.txt` | Externalized French contracts for the three changed LLM roles |
| `scripts/conversation-eval` | Gemini support and matched scenario reporting |

No graph schema, node, edge, or domain-vocabulary change is required.

## Testing

Hermetic TDD coverage:

- Gemini provider request shape, lazy SDK import, factory resolution, and JSON parsing;
- question prompt contains brief/EDB/exclusions and `skip_graph` cannot escape the pool;
- excluded pivot questions are absent from `query_text`, while their user answers remain;
- free-text domain exclusions are vocabulary-gated;
- post-challenge delta triage rejects a newly retrieved sibling without re-triaging the
  stabilized map;
- challenge rendering receives only grounded claims and falls back deterministically;
- `provider=None` preserves deterministic behavior;
- existing convergence and `MAX_QUESTIONS` invariants remain green.

Real verification after the hermetic suite:

1. run both approved scenarios through the real HTTP application with Mistral, uncached;
2. run the same scenarios and PM answers with Gemini, uncached;
3. manually review every offered claim against provenance;
4. update `docs/BUILD-ORDER.md` with the comparison and remaining defects.

## Out of scope

- Hybrid Mistral-generator/Gemini-judge routing;
- automatic provider selection;
- W4 dossier generation;
- retrieval threshold or embedding-profile tuning;
- graph schema changes.
