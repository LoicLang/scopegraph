"""Ground truth for the real-model benches — single source, hand-derived from seed
edges; hermetic data, no imports."""

# Ground truth derived from the seed's DEPENDS_ON / CONSTRAINS / SUPERSEDES edges
# (see docs/eval/cases.md for the narrative version of cases 1-6).
SCENARIOS: list[tuple[str, str, set[str], str]] = [
    (
        "S1 BNPL mobile",
        "Ajouter une option de paiement en 3 fois dans l'app mobile.",
        {
            "feat-mobile-souscription-credit", "sys-moteur-credit", "obj-contrat-credit",
            "con-credit-conso-kyc", "sys-app-mobile", "sys-moteur-autorisation",
            "sys-logiciel-tpe", "dec-releases-tpe-trimestrielles", "dec-scoring-unique",
        },
        "TPE @2 hops (zero textual sim) + buried scoring decision",
    ),
    (
        "S2 Benef entreprise",
        "Permettre aux clients entreprise de creer des beneficiaires depuis leur portail.",
        {
            "obj-beneficiaire", "con-carence-beneficiaire-48h", "con-sca-ajout-beneficiaire",
            "con-verif-sanctions-creation", "dec-ecriture-via-api-benef", "feat-benef-api",
            "proj-refonte-parcours-beneficiaire", "risk-doublons-beneficiaires",
        },
        "inheritance via business object + CANCELLED project as warning",
    ),
    (
        "S3 Cash-back",
        "Proposer un programme de cash-back lors des paiements chez les commercants partenaires.",
        {
            "sys-moteur-autorisation", "dec-gel-evolutions-monetique", "con-pci-dss",
            "sys-scoring-fraude", "dec-scoring-unique", "obj-transaction-carte",
        },
        "dated governance freeze + scope collision",
    ),
    (
        "S4 Plafonds IP premium",
        "Relever les plafonds de virement instantane pour les clients premium.",
        {
            "feat-ip-gestion-plafonds", "dec-plafond-ip-defaut", "con-plafonds-virement-ip",
            "con-lcb-ft-screening", "risk-contournement-plafonds-ip", "dec-scoring-unique",
            "sys-passerelle-ip",
        },
        "burst risk buried in a risk node",
    ),
    (
        "S5 IA reclamations",
        "Mettre en place un assistant IA qui redige les reponses aux reclamations clients.",
        {
            "con-ai-act", "sys-referentiel-client", "feat-ref-exposition",
            "con-tracabilite-consultations", "risk-kyc-obsolete", "con-standard-api-interne",
            "con-rgpd-conservation",
        },
        "AI Act + 2-hop traceability; 'reclamations' absent from graph",
    ),
    (
        "S6 Onboarding digital",
        "Refondre le parcours d'entree en relation 100% digital.",
        {
            "feat-ref-creation-client", "obj-dossier-client-kyc", "con-verif-sanctions-creation",
            "risk-kyc-obsolete", "proj-programme-dsp2", "dec-reutilisation-sca",
            "risk-indispo-service-sanctions",
        },
        "VOCABULARY BRIDGE: 'entree en relation' != 'creation de client' for MiniLM "
        "(0% recall single-turn on 2026-06-11; recovers to 5/7 after one T1 answer)",
    ),
    (
        "S7 Fraude temps reel",
        "Ameliorer la detection de fraude en temps reel sur les paiements par carte.",
        {
            "sys-scoring-fraude", "sys-moteur-autorisation", "dec-scoring-unique",
            "dec-scoring-par-canal-2021", "con-ai-act", "risk-modele-fraude-derive",
            "feat-aut-temps-reel", "proj-refonte-scoring-fraude",
        },
        "SUPERSEDED decision must surface as history",
    ),
    (
        "S8 VI pros",
        "Ouvrir l'emission de virements instantanes aux clients professionnels.",
        {
            "sys-passerelle-ip", "feat-ip-emission", "con-plafonds-virement-ip",
            "dec-double-validation-entreprise", "con-lcb-ft-screening", "dec-scoring-unique",
            "risk-contournement-plafonds-ip", "obj-virement-instantane",
        },
        "enterprise double validation + LCB-FT via gateway",
    ),
    (
        "S9 Self-service plafonds carte",
        "Permettre aux clients de modifier eux-memes leurs plafonds de carte dans l'app.",
        {
            "feat-aut-controle-plafonds", "sys-moteur-autorisation",
            "dec-gel-evolutions-monetique", "con-pci-dss", "sys-app-mobile",
        },
        "monetique freeze BLOCKS the project — the pivot question missed it on 2026-06-11",
    ),
    (
        "S10 Oppositions digitales",
        "Digitaliser le parcours d'opposition de carte bancaire pour les clients.",
        {
            "feat-aut-oppositions", "sys-moteur-autorisation", "dec-gel-evolutions-monetique",
            "con-pci-dss", "sys-app-mobile",
        },
        "precise business term + freeze",
    ),
    (
        "S11 Archivage alertes fraude",
        "Mettre en place un nouvel outil d'archivage reglementaire des alertes de fraude.",
        {"obj-alerte-fraude", "con-archivage-alertes-fraude", "sys-scoring-fraude"},
        "niche domain, tiny neighborhood",
    ),
]
