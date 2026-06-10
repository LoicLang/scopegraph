---
summary: 6 eval cases (French) where scopegraph must beat a naive well-written LLM prompt
read_when:
  - running or extending the evaluation (W4)
  - checking what the retrieval and challenge steps must catch
---

# Cas d'évaluation — scopegraph vs prompt naïf

Méthode : la même entrée est donnée (a) à un prompt naïf bien écrit (« tu es un assistant de
cadrage expérimenté… ») et (b) à scopegraph. Réussite = scopegraph cite la dépendance critique
avec son node ID ; le prompt naïf ne peut pas la connaître ou ne la déduit pas.

## Cas 1 — BNPL mobile (le scénario démo)

Entrée : « Ajouter une option de paiement en 3 fois dans l'app mobile. »

Dépendances critiques attendues :
- dec-reutilisation-sca — tout nouveau flux de paiement hérite de l'orchestration SCA du programme DSP2
- dec-scoring-unique — l'éligibilité BNPL ne peut pas embarquer son propre scoring parallèle
- con-credit-conso-kyc via obj-contrat-credit — le paiement fractionné est juridiquement un crédit ; il exige un dossier KYC à jour
- sys-moteur-credit — l'octroi passe par le moteur de crédit, pas par la logique de l'app
- sys-logiciel-tpe + dec-releases-tpe-trimestrielles — à 2 sauts via la monétique : si l'acceptation en magasin entre au périmètre, le calendrier hérite des releases trimestrielles TPE
- risk-kyc-obsolete — décisions d'éligibilité fragiles sur un stock KYC vieillissant

Piège pour le naïf : la chaîne TPE à 2 sauts et la décision de scoring enfouie dans une décision de 2024.

## Cas 2 — Bénéficiaires depuis l'espace entreprise (le cas fondateur du grain feature)

Entrée : « Permettre aux clients entreprise de créer des bénéficiaires depuis leur portail. »

Dépendances critiques attendues :
- con-carence-beneficiaire-48h, con-sca-ajout-beneficiaire, con-verif-sanctions-creation — héritées via obj-beneficiaire : les règles valent pour TOUT canal qui opère sur l'objet
- dec-ecriture-via-api-benef + feat-benef-api — passage obligé : pas d'écriture directe, le portail doit consommer l'API BENEFGEST
- dec-double-validation-entreprise — spécificité du canal entreprise
- proj-refonte-parcours-beneficiaire — averti : déjà tenté en 2022-2023 et abandonné (migration du stock infaisable sans gel) ; à restituer comme avertissement, PAS comme contrainte
- risk-doublons-beneficiaires — le stock historique en double fausse les contrôles

Piège pour le naïf : les règles partagées sont à 2 sauts via l'objet métier ; le projet annulé est invisible hors du graphe ; il doit être restitué comme avertissement, pas comme contrainte héritée.

## Cas 3 — Cash-back commerçants

Entrée : « Proposer un programme de cash-back aux clients lors de leurs paiements chez les commerçants partenaires. »

Dépendances critiques attendues :
- sys-moteur-autorisation — toute logique transactionnelle carte passe par MONAUT ; le cash-back devra être calculé et déclenché sur le chemin d'autorisation
- dec-gel-evolutions-monetique — le gel actif depuis janvier 2026 bloque toute évolution non réglementaire de MONAUT pendant la migration TPE ; le projet ne peut pas livrer tant que le gel est actif
- con-pci-dss — tout composant qui traite les données de transaction carte (PAN, données de piste) entre dans le périmètre PCI DSS, ce qui impose un audit RSSI et un cloisonnement réseau supplémentaires
- sys-scoring-fraude — les nouveaux schémas transactionnels de cash-back introduisent des patterns inconnus de FRAUDSCORE qui doit être recalibré avant mise en production
- dec-scoring-unique — aucun scoring parallèle n'est permis ; le cash-back ne peut pas embarquer sa propre logique de décision risque en dehors de FRAUDSCORE
- collision de périmètre avec le cas 1 après write-back — les deux projets (BNPL et cash-back) touchent la chaîne monétique pendant le gel ; une livraison simultanée est impossible tant que dec-gel-evolutions-monetique est actif

Piège pour le naïf : le gel monétique est une décision de gouvernance interne datée, invisible sans le graphe ; et la collision avec un autre projet en cours sur la même chaîne n'est détectable qu'en parcourant les voisins de sys-moteur-autorisation.

## Cas 4 — Relèvement des plafonds de virement instantané

Entrée : « Relever les plafonds de virement instantané pour les clients premium. »

Dépendances critiques attendues :
- feat-ip-gestion-plafonds + dec-plafond-ip-defaut — le plafond par défaut (15 000 €) est défini par décision de gouvernance et modifiable uniquement via la fonctionnalité dédiée de FLUXINST ; tout relèvement doit passer par ce point de modification unique pour rester traçable
- con-plafonds-virement-ip — la contrainte réglementaire encadre les limites autorisées ; un relèvement au-delà de certains seuils requiert une validation Direction des paiements
- con-lcb-ft-screening — un relèvement de plafond augmente mécaniquement la surface d'exposition LCB-FT ; le criblage temps réel sur FLUXINST doit couvrir les nouveaux montants sans dégradation de performance
- risk-contournement-plafonds-ip — relever les plafonds unitaires aggrave le scénario de rafales : des acteurs frauduleux peuvent émettre plusieurs virements sous le nouveau seuil élevé ; FLUXINST ne disposant pas nativement de contrôle de cumul glissant, ce risque monte en criticité
- dec-scoring-unique via sys-passerelle-ip — FRAUDSCORE est l'unique point de décision risque sur la passerelle ; le profil de risque des clients premium doit être intégré dans FRAUDSCORE, pas dans une logique dédiée

Piège pour le naïf : le risque de rafales est documenté dans le graphe comme risque résiduel non couvert nativement par FLUXINST ; aucune analyse générique de « relèvement de plafond » ne peut l'identifier sans lire le nœud risk-contournement-plafonds-ip.

## Cas 5 — Assistant IA de réponse aux réclamations

Entrée : « Mettre en place un assistant IA qui rédige les réponses aux réclamations clients. »

Dépendances critiques attendues :
- con-ai-act — tout composant IA doit faire l'objet d'une classification par niveau de risque selon le règlement européen AI Act ; un assistant qui accède aux données client et rédige des réponses formelles est potentiellement à risque limité ou élevé, et sa mise en production sans classification est interdite
- sys-referentiel-client + feat-ref-exposition + con-tracabilite-consultations — l'assistant devra lire les données client dans REFCLI via l'API d'exposition ; chaque accès sera individuellement journalisé et associé à l'identifiant du service demandeur, conformément à la politique de traçabilité
- risk-kyc-obsolete — les réponses aux réclamations s'appuient sur les données du référentiel client ; si le dossier KYC sous-jacent est périmé, l'assistant peut produire des réponses incorrectes ou non conformes basées sur des informations obsolètes
- con-standard-api-interne — l'assistant devra consommer les APIs internes (REFCLI, gestion des réclamations) en respectant le standard OAuth2 + versionnage + contrat OpenAPI publié ; un composant non conforme ne pourra pas être référencé par les autres équipes
- con-rgpd-conservation — les échanges avec l'assistant (prompts, réponses générées, données client citées) constituent un traitement de données personnelles soumis aux durées de conservation maximales du registre RGPD ; le pipeline de purge doit être prévu dès la conception

Piège pour le naïf : la classification AI Act est une obligation réglementaire récente et spécifique à l'UE que le prompt naïf peut citer en général, mais sans identifier le nœud con-ai-act ni ses implications concrètes sur le processus d'approbation interne ; la contrainte de traçabilité sur chaque accès REFCLI est enfouie à deux sauts (sys-referentiel-client → feat-ref-exposition → con-tracabilite-consultations).

## Cas 6 — Refonte de l'onboarding client digital

Entrée : « Refondre le parcours d'entrée en relation 100 % digital. »

Dépendances critiques attendues :
- feat-ref-creation-client + obj-dossier-client-kyc — le cœur du parcours crée le dossier client dans REFCLI et constitue le dossier KYC initial ; toute refonte du parcours modifie directement cette fonctionnalité et l'objet métier qui conditionne l'ensemble de la relation bancaire
- con-verif-sanctions-creation — le criblage des listes de sanctions est obligatoire à l'entrée en relation ; il doit être intégré en synchrone dans le nouveau parcours digital, sans possibilité de le différer
- risk-kyc-obsolete — la refonte introduit un nouveau parcours de collecte des données KYC mais ne résout pas le stock existant de dossiers anciens et incomplets ; la coexistence des deux états du stock crée un risque de traitement inégal entre nouveaux et anciens clients
- proj-programme-dsp2 + dec-reutilisation-sca — l'authentification forte à l'entrée en relation est pilotée par le programme DSP2 ; le nouveau parcours digital doit réutiliser l'orchestration SCA existante et ne peut pas implémenter une authentification propriétaire parallèle
- risk-indispo-service-sanctions — le parcours 100 % digital dépend du service externe de criblage des sanctions pour chaque création de client ; une indisponibilité de ce service bloque l'intégralité du parcours digital sans fallback documenté, risque aggravé par l'absence de stratégie de mode dégradé

Piège pour le naïf : le risque d'indisponibilité du service de criblage externe est invisible sans le graphe ; il bloque entièrement un parcours digital synchrone, ce qu'aucune analyse générique d'onboarding ne peut anticiper ; la dépendance SCA via proj-programme-dsp2 est à deux sauts et enfouie dans la gouvernance du programme.
