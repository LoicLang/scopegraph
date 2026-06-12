---
summary: scripted W3 demo — cash-back walkthrough with live LLM (Mistral), expected behavior at each step
read_when:
  - rehearsing or giving the W3 demo
  - smoke-checking the LLM layer end-to-end after a change
---

# Demo W3 — cash-back walkthrough (spec §8)

North star: the user must feel they are **talking to someone who knows the company**.
Every step below names what must appear on screen; if it doesn't, stop and debug —
don't improvise around it.

## Setup

```bash
pip install -e ".[embeddings,llm]"
export MISTRAL_API_KEY=...           # demo default provider
export SCOPEGRAPH_LLM_PROVIDER=mistral
uvicorn --factory web.app:create_app
# open http://127.0.0.1:8000
```

Template-only rehearsal (no key, no network): `SCOPEGRAPH_LLM_PROVIDER=none` —
same flow, template questions, no enrichment chips, no challenge.

## Script

1. **Brief.** Type:
   > Proposer un programme de cash-back lors des paiements chez les commerçants partenaires.

   Expected: the Context Map populates (anchors highlighted, expansions dashed);
   **enrichment chips** appear under the input (≤4 vocabulary terms, each removable
   with ×); the EDB pane shows the 12 sections, all « — », badge « N section(s) à
   remplir ».

2. **Woven question.** The assistant asks ONE question in natural French that mixes
   graph context with an EDB section — no slug, no jargon. (If the LLM picks a
   graph ambiguity, it sounds like « Le cash-back doit-il fonctionner aussi en
   magasin, via les terminaux de paiement ? »)

3. **Free answer filling two sections at once.** Answer with something rich, e.g.:
   > En magasin uniquement dans un premier temps ; l'objectif est d'augmenter la
   > fréquence d'achat chez les partenaires d'ici fin d'année.

   Expected: **extraction cards** appear in the chat (« Élément d'EDB proposé »,
   one per section — perimetre, objectifs/jalons) with Accepter / Modifier /
   Refuser. Accept them → the EDB sections fill with a « vous » badge, the
   completeness badge decreases.

4. **Challenge.** After the graph ambiguities are exhausted (answer the remaining
   questions), the challenge fires on a stable map. Expected, in order:
   - the map **shrinks** — rejected nodes leave the canvas and appear in the
     collapsible « Rejetés (N) » list with the model's one-line reason each,
     each with a Restaurer button;
   - **the monetique freeze comes back**: `dec-gel-evolutions-monetique` was
     pulled by the deterministic governance pull (amber double border, role
     « ramené via … »), justified by the model, and named in the challenge
     statement;
   - the **challenge statement** lands in the chat AND in the EDB section
     « Challenge & arbitrages ouverts » (badge IA);
   - **claim cards** appear (« Affirmation à valider ») citing node ids toward
     dependances/contraintes/risques — accept them → sections fill with a
     « claim » badge;
   - if the runtime rejected any ungrounded claim, the amber strip under the map
     says « N réclamation(s) de l'IA rejetée(s) par le runtime » — that's a
     feature, show it.

5. **Close the loop.** The remaining questions are EDB gaps (jalons, exigences…).
   Answer them; when nothing is left the assistant says
   « EDB complet — prêt pour la rédaction (W4) ».

## Talking points

- The LLM never wrote a single fact into the EDB without consent: every entry came
  from a card (Accepter) or your own answers.
- Remove an enrichment chip live (×) → the map re-runs without that term:
  the AI's query vocabulary is revocable, never a hidden rewrite.
- Restore a rejected node live → it returns to the map with provenance
  « restauré par l'utilisateur » — the runtime, not the model, owns the map.
