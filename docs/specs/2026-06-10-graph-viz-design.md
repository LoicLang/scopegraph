---
summary: validated design — interactive graph viewer (Cytoscape standalone HTML) built on a
  reusable payload module; the future Context Map rendering path
read_when:
  - touching core/viz/ or web/graph_template.html or scripts/graph-viz
  - building the W2 web Context Map pane or the W4 Context Map highlight mode
---

# Graph viewer — Design Spec

Date: 2026-06-10
Status: validated in brainstorming session
Upstream: [2026-06-09-scopegraph-mvp-design.md](2026-06-09-scopegraph-mvp-design.md) §2 —
**amended by this spec**: the Context Map rendering medium becomes an interactive
Cytoscape.js view (this viewer) instead of Mermaid; Mermaid is deferred to the W4 dossier
Markdown export, where it remains the right tool.

## 1. Goal and reuse contract

Explore the 72-node seed graph comfortably today, with the exact seam the product needs
later: **the durable part is the payload, not the page.** One pure function builds the
"what to display" payload (nodes, edges, highlight set, filters applied); the HTML template
renders it. W2 serves the same payload live from FastAPI; W4's Context Map is the same
payload with `highlight` = the nodes surfaced by a scoping session. Nothing built here is
throwaway.

## 2. Components

### `core/viz/payload.py` (the durable seam)

```python
def build_payload(
    service: GraphService,
    *,
    focus: str | None = None,      # center node id; with k, restricts to its k-hop subgraph
    k: int = 2,                    # radius used when focus is set
    domains: set[str] | None = None,   # keep nodes sharing ≥1 of these domains
    types: set[str] | None = None,     # keep nodes of these schema types
    highlight: set[str] | None = None, # display-only emphasis; ids must exist
) -> dict
```

Payload shape (JSON-serializable, stable contract):

```json
{
  "nodes": [{"id", "label", "type", "domains": [...], "summary", "search"}],
  "edges": [{"source", "target", "type", "note"}],
  "highlight": ["node-id", ...]
}
```

- `label` = `name` or `title` depending on node type. `summary` = description/statement
  truncated to 200 chars. `search` = lowercase concatenation of id, label and aliases —
  this is what makes the MONAUT alias trap findable in the UI search box.
- Filters compose by intersection (focus subgraph ∩ domains ∩ types). Edges are kept iff
  both endpoints are kept. `highlight` ids that don't exist in the graph raise
  `UnknownNodeError`; highlight ids filtered out of view are silently dropped from the list.
- Hermetic tests like the rest of core/.

### `web/graph_template.html` (future UI building block)

Standalone HTML, fixed light theme, French UI labels. Cytoscape.js via CDN, built-in `cose`
layout (no plugin). Contains the literal placeholder `__GRAPH_DATA__`. Behaviors:

- Node color by schema type (7-color legend), edge style by edge type (dashed PART_OF,
  amber CONSTRAINS, dotted RELATES_TO, ...), directed arrows.
- Click a node → side panel: label, type, domains, full summary, note of each incident
  edge; button « Isoler le voisinage » (hides everything but the closed neighborhood) and
  « Tout afficher ».
- Search box matching the `search` field (ids, labels, aliases).
- Domain dropdown filter (client-side).
- Highlight mode: when `highlight` is non-empty, highlighted nodes get a strong border and
  full opacity, everything else is dimmed — the Context Map look.

### `scripts/graph-viz` (CLI entry point)

`./scripts/graph-viz [--focus ID] [--k N] [--domain D ...] [--type T ...]
[--highlight id1,id2] [--out PATH]`. Loads the graph via `GraphService.from_dir`, builds
the payload, injects it into the template, writes `out/graph.html` (default) and prints the
path. `out/` is gitignored (regenerable artifact).

## 3. Testing

- `tests/test_viz_payload.py` (hermetic): full-graph counts, focus+k subgraph (the founding
  2-hop beneficiary case), domain/type filters, edge-endpoint closure, highlight passthrough
  and unknown-highlight error, summary truncation, search field contains aliases.
- `tests/test_graph_viz_script.py`: run the script against the real graph into tmp_path;
  assert the file exists, contains `"nodes"` and no remaining `__GRAPH_DATA__`.

## 4. Out of scope

No server (W2). No Mermaid renderer (W4 dossier export). No graph editing. No persistence
of view state. No dark mode.
