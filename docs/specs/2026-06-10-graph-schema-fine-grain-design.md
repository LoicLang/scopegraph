---
summary: validated design — schema v1 refined to feature/business-object grain (7 node types,
  7 edge types), domains as ecosystem data, seed grown to ~72 nodes
read_when:
  - writing or revising ADR 0001 (this spec is its source)
  - touching core/graph models, loader, or any YAML under graph/
  - writing the seed data or eval cases
---

# Graph schema v1 at feature grain — Design Spec

Date: 2026-06-10
Status: validated in brainstorming session
Upstream: [2026-06-09-scopegraph-mvp-design.md](2026-06-09-scopegraph-mvp-design.md) (MVP
design, still authoritative for everything non-schema) ·
[docs/project-kickoff.md](../project-kickoff.md) §4 (superseded by this spec for the schema;
kickoff remains historical record). ADR 0001 must be written from THIS spec, not from
kickoff §4. The W1 plan (`docs/plans/2026-06-09-week1-foundations.md`) must be revised
accordingly before execution.

---

## 1. Motivation

The system-grain schema cannot express the dependency that carries the most scoping value in
a real bank: *feature-level coupling through shared business data*. Founding example: the
beneficiary-management app's "add beneficiary" feature enforces a 48-hour cooling-off delay
and SCA; any other app that creates beneficiaries inherits those same rules. No textual
similarity links the two apps — the coupling exists because both operate on the same business
object. The schema must let the graph *derive* that coupling instead of requiring someone to
have drawn an app-to-app edge in advance.

## 2. Decisions

| Topic | Decision | Rationale |
|---|---|---|
| Node types | 7: the existing 5 + **`Feature`** + **`BusinessObject`** | Features carry the fine-grain rules; business objects are the coupling pivot. |
| Edge types | 7: the existing 5 + **`PART_OF`** + **`OPERATES_ON`** | `PART_OF` anchors a feature to its system; `OPERATES_ON` declares what a feature/system touches. |
| Edge naming | `OPERATES_ON` (over `USES`/`MANAGES`) | Reads unambiguously: "the feature *operates on* the beneficiary object". |
| Schema universality | Node/edge types contain nothing banking-specific. The **domain vocabulary moves out of code** into `graph/domains.yaml`, loaded and validated with the graph. | The schema is the contract with ecosystem-foundry and must fit any IT estate (hospital, retail…). Porting scopegraph = swapping two data files, zero code change. |
| Shared constraints | A business rule is **one `Constraint` node** with `CONSTRAINS` edges to every place it applies. Attached to a `BusinessObject`, it binds *all* features operating on that object; attached to a `Feature`, it is feature-specific. | Materializes "the second app must reuse the same rules in the same format" as graph structure, not duplicated text. |
| Non-uniform depth | Only some systems get feature detail; `System → OPERATES_ON → object` keeps coarse systems in the object web. | Realistic (documentation depth is never uniform) and keeps the seed effort bounded. |
| Cancelled project | Keep one `cancelled` project in the seed. Modeling rule: **no structural edges** (`PRODUCED`/`CONSTRAINS` forbidden, nothing may `DEPENDS_ON` it); exactly one `RELATES_TO` edge with a note giving the abandon reason; `outcomes` records the lesson. | Its influence is memorial, not structural: "this was tried and killed, here is the wall". The system must surface it as a warning, never as an inherited constraint — that distinction is itself a trap. |
| Seed size | **~72 nodes** (was 15–25; target band 70–80). | Large enough that retrieval has real noise to rank; small enough to hand-curate in French. |
| Demo & eval | BNPL demo scenario unchanged (now flows through mobile features). Eval cases go from 5 to **6**: new "beneficiaries" case — a new corporate app creating beneficiaries must inherit BENEFGEST's rules. | The new case is the founding example of this spec, end to end. |

## 3. Schema v1 (full definition — source for ADR 0001)

### Node types (7)

| Type | Purpose | Specific fields (beyond shared) |
|---|---|---|
| `System` | Existing software / data source | `name`, `aliases[]`, `description`, `owner_team`, `data_quality_notes`, `known_risks[]` |
| `Feature` | A capability of one system | `name`, `description` (concrete behaviour incl. parameters), `parameters[]` |
| `BusinessObject` | Shared business data concept | `name`, `aliases[]`, `description`, `steward_team` |
| `Project` | Past or ongoing project | `name`, `aliases[]`, `description`, `status` (done/ongoing/cancelled), `owner_team`, `outcomes`, `known_risks[]` |
| `Decision` | Past decision constraining the future | `title`, `statement`, `rationale`, `date`, `decided_by`, `still_active` |
| `Constraint` | Standard, regulation, policy, business rule | `title`, `statement`, `source`, `severity` |
| `Risk` | Known risk attached to the ecosystem | `title`, `statement`, `likelihood`, `impact`, `mitigations[]` |

Shared fields (all nodes): `id` (slug, prefix by type: `sys- feat- obj- proj- dec- con- risk-`),
`domains[]` (≥1, validated against the loaded vocabulary), `tags[]`, `created_from`
(`seed | scoping:<id> | ingestion:<id>`).

### Edge types (7) and allowed topology

Endpoint kinds are validated at load time (fail-fast, like every other graph rule).

| Edge | Allowed source → target | Notes |
|---|---|---|
| `PART_OF` | Feature → System | Exactly one parent per feature (loader-enforced). |
| `OPERATES_ON` | Feature → BusinessObject · System → BusinessObject | `note` may qualify the mode ("création et modification"). |
| `DEPENDS_ON` | System → System · Feature → Feature · Feature → System | Feature→Feature = a real cross-app call, not data coupling. |
| `CONSTRAINS` | Constraint/Decision → System, Feature, BusinessObject or Project | Object-level = applies to all features operating on it. |
| `PRODUCED` | Project → System, Feature or Decision | Forbidden from `cancelled` projects. |
| `SUPERSEDES` | Decision → Decision | |
| `RELATES_TO` | any → any | Last resort; `note` mandatory (model-enforced, unchanged). |

Edge fields unchanged: `source_id`, `target_id`, `type`, `note`, `evidence`, `created_from`,
`verified`. Seed edges are `verified: true`.

### Domain vocabulary as data

`graph/domains.yaml` lists the ecosystem's domains (the 10 banking domains of kickoff §4,
unchanged in content). The loader validates every node's `domains[]` against it; `DOMAINS` is
removed from `models.py`. The vocabulary remains governed: changing it requires an ADR, but it
is now per-ecosystem data, not schema. Retrieval semantics (domain overlap as boost and
traversal bridge) are unchanged.

## 4. Seed shape (~72 nodes, all French, all fictional)

| Layer | Count | Content |
|---|---|---|
| Systems | 9 | the 7 already specified + `sys-gestion-beneficiaires` (BENEFGEST) + `sys-moteur-credit` (CREDIFLOW, needed by the BNPL story) |
| Features | 24 | 5 zoomed systems: BENEFGEST (5: ajout, modification, suppression, consultation, exposition API), MOBANK (5: ajout bénéficiaire, virement instantané, souscription crédit conso, consultation comptes, activation carte), FLUXINST (4: émission, réception, rappel de fonds, gestion plafonds), MONAUT (5: autorisation temps réel, gestion oppositions, contrôle plafonds, routage réseaux, tarification), REFCLI (5: création client, mise à jour KYC, screening périodique, fusion doublons, exposition référentiel). The 4 other systems stay coarse. |
| Business objects | 6 | bénéficiaire, virement instantané, dossier client KYC, transaction carte, contrat de crédit, alerte fraude |
| Projects | 7 | the 5 already specified + 1 done + 1 **cancelled** (refonte parcours bénéficiaire, abandoned 2023) |
| Decisions | 8 | the 5 already specified + 3 feature-grain (e.g. "toute création de bénéficiaire passe par l'API BENEFGEST, pas d'écriture directe") |
| Constraints | 12 | the 4 already specified + 8 shared fine-grain rules, among which: délai de carence 48 h, SCA à l'ajout de bénéficiaire, vérification sanctions à la création, plafonds virement instantané, durée de conservation RGPD, traçabilité des consultations du référentiel |
| Risks | 6 | the 3 already specified + 3: double saisie de bénéficiaires historique, modèle fraude non recalibré, indisponibilité du service de vérification sanctions |

Total: 9 + 24 + 6 + 7 + 8 + 12 + 6 = 72.

### Deliberate traps (7)

The four existing ones (alias MONAUT, superseded decision, unresolved contradiction,
2-hop monétique→TPE chain) plus three new:

5. **Inheritance via shared object** — the founding example: constraints reach a new project
   only through `OPERATES_ON obj-beneficiaire`, invisible to textual similarity.
6. **Non-uniform depth** — retrieval must work when a relevant system has no features.
7. **Cancelled project** — must be surfaced as history/warning, never as an inherited
   constraint or dependency.

Each trap gets an integration test in `tests/test_seed.py`.

## 5. Impacts

- **ADR 0001** is written from this spec (7+7 types, topology matrix, domains-as-data,
  cancelled-project rule). Then the schema freezes as planned.
- **W1 plan** to revise before execution: models (+2 node types, +2 edge types, topology
  validation, `PART_OF` single-parent), loader (load `domains.yaml`, validate vocabulary and
  endpoint kinds), seed (~72 YAML files), seed tests (7 traps), eval cases (6). Estimated
  +30–40 % W1 effort, concentrated in seed writing.
- **Retrieval (W2)** unchanged in design; it gains a richer graph to traverse.
- **README / demo**: BNPL scenario unchanged; beneficiary eval case added.

## 6. Out of scope

- Drift detection between duplicated rule definitions (the "copies to reconcile" variant) —
  a deliberate seed divergence may be added later as content, without engine change.
- Read/write distinction on `OPERATES_ON` as a typed field — the free-text `note` carries it
  for the MVP.
- Feature-level write-back granularity (scoped projects write back as `Project` nodes, as
  already specified; emitting `Feature` nodes at write-back is a later refinement).
