const fs = require("fs");
const H = require("./gen_doc.js");
const { p, rich, h1, h2, bullet, table, espace, saut, garde, toc,
  Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType, LevelFormat,
  Footer, PageNumber, ENCRE, VERT, GRISF } = H;

const contenu = [];

/* ============ 1. CONTEXTE ET PROBLÉMATIQUE ============ */
contenu.push(
  h1("1. Contexte institutionnel et problématique"),
  p("L'Agence Nationale de la Statistique et de la Démographie (ANSD) est l'organisme officiel chargé de la coordination technique des activités statistiques au Sénégal (loi n° 2004-21 du 21 juillet 2004 et décrets d'application). Elle produit et diffuse des données démographiques, économiques, sociales et environnementales : recensements (RGPH), enquêtes auprès des ménages (EHCVM, ENES, EDS), indices de prix (IHPC), comptes nationaux."),
  p("La littérature en e-gouvernement documente un paradoxe persistant : la disponibilité croissante des données publiques ouvertes s'accompagne d'une difficulté d'accès pour les non-spécialistes. Janssen et al. (2012) ont montré que les portails de données ouvertes souffrent d'un défaut d'intermédiation entre les données brutes et les besoins informationnels des citoyens, constat confirmé par Zuiderwijk et al. (2021). Le site web de l'ANSD diffuse des milliers de documents et d'indicateurs, mais l'accès reste tributaire de la capacité de l'usager à naviguer une arborescence complexe et à interpréter des formats statistiques spécialisés."),
  h2("1.1 Formulation du problème"),
  rich([
    { text: "Comment concevoir un système conversationnel capable de fournir des réponses exactes, traçables et contextuellement pertinentes aux questions posées en langage naturel sur les données statistiques de l'ANSD, sachant que ces données sont distribuées entre des sources structurées (bases de données, tableaux) et non structurées (rapports, bulletins PDF) ?", italics: true, bold: true, color: ENCRE },
  ]),
  h2("1.2 Décomposition en sous-problèmes"),
  bullet(null, [{ text: "SP1 — Fiabilité : ", bold: true }, { text: "les grands modèles de langue (LLM) génèrent des affirmations factuellement incorrectes présentées avec une confiance apparente élevée (« hallucinations », Ji et al., 2023). Pour des statistiques officielles, tout taux d'hallucination supérieur à un seuil marginal est inacceptable (Principes fondamentaux de la statistique officielle, Nations Unies, 2014)." }]),
  bullet(null, [{ text: "SP2 — Hétérogénéité des sources : ", bold: true }, { text: "les données structurées exigent une traduction précise en SQL (benchmark Spider, Yu et al., 2018) ; les données non structurées exigent une recherche sémantique dont la performance dépend de la qualité des représentations vectorielles (Muennighoff et al., 2023)." }]),
  bullet(null, [{ text: "SP3 — Routage : ", bold: true }, { text: "aucun système existant ne résout de manière optimale la question « étant donné une requête, faut-il interroger une base de données ou rechercher dans des documents ? ». Ce verrou est identifié explicitement par la survey de référence sur le RAG (Gao et al., 2023)." }]),
  espace(),

  /* ============ 2. OBJECTIFS ============ */
  h1("2. Objectifs de l'étude"),
  p("Objectif général : concevoir, implémenter et évaluer un chatbot intelligent pour le site web de l'ANSD, capable de traiter des requêtes en français et de fournir des réponses fiables et traçables via une architecture hybride RAG + Text-to-SQL."),
  table(["Code", "Objectif spécifique", "Fondement"],
    [
      ["OS1", "Développer un pipeline RAG pour l'interrogation des documents non structurés de l'ANSD", "Lewis et al. (2020) : supériorité du RAG sur les LLM seuls pour les tâches à forte intensité de connaissances"],
      ["OS2", "Implémenter un module Text-to-SQL pour l'interrogation des données structurées", "Pourreza & Rafiei (2023) : la décomposition en contexte atteint 85,3 % d'Execution Accuracy sur Spider"],
      ["OS3", "Concevoir un orchestrateur de routage intelligent entre les deux voies", "Gao et al. (2023) : le routage adaptatif est une direction de recherche prioritaire"],
      ["OS4", "Intégrer des guardrails garantissant la fiabilité et le périmètre des réponses", "Rebedea et al. (2023) : framework programmable de contrôle des applications LLM"],
      ["OS5", "Évaluer le système avec des métriques standardisées et une étude utilisateur", "Es et al. (2024) : RAGAS ; Yu et al. (2018) : Execution Accuracy ; Brooke (1996) : SUS"],
    ],
    [700, 4600, 4700]),
  espace(),

  /* ============ 3. ÉTAT DE L'ART ============ */
  h1("3. État de l'art synthétique"),
  p("La revue a été conduite selon les lignes directrices de Kitchenham & Charters (2007) sur Google Scholar, ACL Anthology, arXiv (cs.CL) et IEEE Xplore, période 2017-2024. Ne sont présentés ici que les résultats structurants ; l'analyse complète figure au chapitre État de l'art du mémoire."),
  h2("3.1 Fondements : Transformer et grands modèles de langue"),
  p("L'architecture Transformer (Vaswani et al., 2017) fonde l'ensemble des composants du système : son mécanisme d'attention multi-tête permet la parallélisation de l'entraînement, la capture des dépendances longues et la transférabilité pré-entraînement/adaptation (Devlin et al., 2019). Les LLM contemporains en sont des instances autorégressives à grande échelle (Brown et al., 2020). DeepSeek-V3 (DeepSeek-AI, 2024) est retenu comme modèle génératif : architecture Mixture-of-Experts (Shazeer et al., 2017 ; Fedus et al., 2022) de 671 milliards de paramètres dont 37 milliards activés par token, MMLU 88,5 comparable à GPT-4, fenêtre de 128K tokens, poids ouverts (souveraineté et coût), performances documentées en français."),
  h2("3.2 Retrieval-Augmented Generation"),
  p("Le RAG (Lewis et al., 2020) conditionne la génération sur des documents récupérés : il réduit les hallucinations, permet l'actualisation des connaissances sans réentraînement et rend chaque réponse traçable vers sa source — trois propriétés indispensables à la statistique officielle. Le pipeline retenu suit les quatre étapes canoniques : segmentation (512 tokens, chevauchement 128, configuration validée par Gao et al., 2023), vectorisation (BGE-M3, Chen et al., 2024 : plus de 100 langues, représentations dense et sparse combinées), indexation (Qdrant, algorithme HNSW, Malkov & Yashunin, 2018), puis génération ancrée avec refus explicite hors contexte (Asai et al., 2023). Un filtrage des passages sous un seuil de pertinence, inspiré de CRAG (Yan et al., 2024), réduit le bruit injecté au modèle."),
  h2("3.3 Text-to-SQL"),
  table(["Approche", "Année", "EA (Spider)", "Référence"],
    [
      ["RAT-SQL (encodage relationnel)", "2020", "69,7 %", "Wang et al. (2020)"],
      ["PICARD (décodage contraint)", "2021", "79,3 %", "Scholak et al. (2021)"],
      ["DIN-SQL (décomposition + auto-correction)", "2023", "85,3 %", "Pourreza & Rafiei (2023)"],
      ["DAIL-SQL (prompting optimisé)", "2024", "86,6 %", "Gao et al. (2024)"],
      ["SQLCoder-8B (open source)", "2024", "76,2 %", "Defog (2024)"],
    ],
    [3900, 900, 1400, 3800]),
  p("La stratégie DIN-SQL est retenue : meilleur compromis performance / explicabilité / absence de fine-tuning. Elle est adaptée au domaine ANSD par un dictionnaire métier explicite (schema linking : « taux de chômage » → emploi.taux_chomage), des exemples few-shot spécifiques et une auto-correction par réinjection des erreurs d'exécution.", { para: { spacing: { before: 140, after: 140, line: 300 } } }),
  h2("3.4 Guardrails et routage"),
  p("Les Principes fondamentaux de la statistique officielle (Nations Unies, 2014) imposent qu'un assistant statistique ne puisse ni inventer des données, ni les interpréter politiquement, ni sortir de son périmètre. La taxonomie NeMo Guardrails (Rebedea et al., 2023) — rails topiques, de sûreté, factuels, anti-contournement — est retenue car programmable sans réentraînement, contrairement à l'alternative Constitutional AI (Bai et al., 2022) qui exige un fine-tuning coûteux. Pour le routage, quatre familles d'approches existent (classification supervisée, similarité d'embeddings, LLM-as-router, cascade) ; aucune n'a fait l'objet d'une évaluation comparative rigoureuse — c'est la lacune L2 exploitée par ce travail."),
  h2("3.5 Chatbots d'instituts de statistique : lacune applicative"),
  table(["Institution", "Système", "Type", "Limite"],
    [
      ["INSEE (France)", "FAQ interactive", "Règles", "Pas d'interrogation de données"],
      ["ONS (Royaume-Uni)", "Prototype NLP", "Hybride", "Non déployé en production"],
      ["Statistique Canada", "Assistant virtuel", "Règles", "Orientation uniquement"],
      ["Eurostat (UE)", "Chatbot documentation", "FAQ", "Pas d'accès aux datasets"],
    ],
    [2600, 2600, 1500, 3300]),
  p("Aucun institut de statistique n'a déployé de système interrogeant dynamiquement à la fois bases de données et documents via une interface conversationnelle unique (revue 2019-2024) — conformément au constat général d'Androutsopoulou et al. (2019) : 78 % des chatbots gouvernementaux restent à base de règles.", { para: { spacing: { before: 140, after: 140, line: 300 } } }),
  saut(),

  /* ============ 4. LACUNES, QUESTIONS, HYPOTHÈSES ============ */
  h1("4. Lacunes scientifiques, questions de recherche et hypothèses"),
  bullet(null, [{ text: "L1 : ", bold: true }, { text: "absence d'architecture hybride RAG + Text-to-SQL validée pour le domaine statistique." }]),
  bullet(null, [{ text: "L2 : ", bold: true }, { text: "problème du routage optimal entre sources structurées et non structurées sous-étudié (approches ad hoc, non comparées)." }]),
  bullet(null, [{ text: "L3 : ", bold: true }, { text: "aucun benchmark de question-réponse statistique en français, a fortiori en contexte africain francophone." }]),
  bullet(null, [{ text: "L4 : ", bold: true }, { text: "guardrails génériques non adaptés aux exigences de la statistique publique (principes ONU)." }]),
  espace(),
  table(["QR", "Question de recherche", "Origine"],
    [
      ["QR1", "Comment concevoir une architecture hybride RAG + Text-to-SQL garantissant la fiabilité des réponses pour des statistiques officielles ?", "L1, L4"],
      ["QR2", "Quelle stratégie de routage sélectionne la source la plus pertinente pour une requête donnée, et comment l'évaluer ?", "L2"],
      ["QR3", "Quelles adaptations sont nécessaires au contexte francophone et institutionnel sénégalais ?", "L3"],
      ["QR4", "Comment évaluer holistiquement un système hybride (métriques de génération + d'exactitude de requête + usabilité) ?", "L1, L3"],
    ],
    [700, 8000, 1300]),
  espace(),
  p("Chaque hypothèse est formulée de manière falsifiable (Popper, 1959) :"),
  table(["H", "Hypothèse", "Prédiction testable", "Condition de rejet"],
    [
      ["H1", "Un classifieur fine-tuné sur un corpus annoté de questions statistiques atteint une précision de routage > 90 %", "Accuracy en validation croisée", "Accuracy < 85 %"],
      ["H2", "L'architecture hybride produit des réponses plus fidèles que chaque voie isolée", "Faithfulness RAGAS > 0,85 vs < 0,80", "Différence non significative (test t apparié, p > 0,05)"],
      ["H3", "Les guardrails ramènent le taux d'affirmations non supportées sous 5 %", "Taux mesuré sur le jeu de test", "Taux > 5 %"],
      ["H4", "Le système atteint une usabilité satisfaisante auprès d'usagers réels", "Score SUS moyen > 70 (n = 15)", "SUS < 70"],
    ],
    [500, 3400, 3100, 3000]),
  saut(),

  /* ============ 5. ARCHITECTURE ============ */
  h1("5. Architecture proposée : RAMA-ANSD"),
  p("Le système, nommé RAMA-ANSD (Système d'Accès Guidé aux Statistiques), assemble quatre composants dont l'interaction est représentée ci-dessous. Chaque requête traverse successivement les guardrails d'entrée, l'orchestrateur de routage f(q) → {SQL, RAG, HYBRID}, la ou les voies de traitement, puis le guardrail de sortie ; la réponse est systématiquement accompagnée de sa voie, de la confiance du routeur, du SQL généré et des documents sources (transparence algorithmique, Code de bonnes pratiques de la statistique européenne, Eurostat, 2017)."),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(__dirname + "/architecture_rama_ansd.png"),
      transformation: { width: 640, height: 401 } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 180 },
    children: [new TextRun({ text: "Figure 1 — Architecture du système RAMA-ANSD (flux d'une requête).", size: 18, italics: true, color: GRISF, font: "Calibri" })] }),
  h2("5.1 Orchestrateur à deux niveaux (contribution centrale)"),
  p("Le routage combine (niveau 1) un classifieur supervisé léger — DeBERTa-v3 fine-tuné (He et al., 2021), latence de l'ordre de la milliseconde sur CPU — et (niveau 2) un fallback LLM déclenché uniquement lorsque la confiance du classifieur est inférieure à 0,85. Ce schéma réunit l'efficacité computationnelle de la classification supervisée et la flexibilité du LLM pour les cas ambigus, notamment la classe HYBRID."),
  h2("5.2 Défense en profondeur contre les hallucinations"),
  p("La fiabilité (SP1) est traitée par quatre mécanismes complémentaires plutôt que par un seul : (i) sur la voie SQL, la verbalisation des résultats est déterministe — le chiffre affiché provient toujours de la base de données, jamais du modèle génératif, rendant l'hallucination numérique structurellement impossible sur cette voie ; (ii) sur la voie RAG, la génération est contrainte au contexte récupéré avec refus explicite lorsque l'information est absente ; (iii) un rail de sortie vérifie de manière déterministe que chaque nombre de la réponse existe dans les éléments de preuve, doublé en production d'un juge LLM de fidélité (Self-RAG, Asai et al., 2023) ; (iv) l'exécution SQL est en lecture seule avec liste blanche SELECT (guardrail structurel)."),
  saut(),

  /* ============ 6. JUSTIFICATION DES CHOIX ============ */
  h1("6. Matrice de justification des choix techniques"),
  p("Chaque décision est traçable vers une alternative écartée et une référence — format exigé pour la soutenance."),
  table(["Décision", "Alternatives écartées", "Justification et référence"],
    [
      ["LLM : DeepSeek-V3", "GPT-4 (coût, souveraineté) ; Mistral-7B (capacité)", "MMLU 88,5 ; MoE 671B/37B activés ; 128K tokens ; poids ouverts ; français documenté (DeepSeek-AI, 2024)"],
      ["Température = 0", "Échantillonnage T > 0", "Déterminisme et reproductibilité exigés pour la statistique officielle (ONU, 2014)"],
      ["Embeddings : BGE-M3", "Ada (propriétaire) ; mE5 (dense seul)", "100+ langues ; dense + sparse combinés ; état de l'art multilingue open source (Chen et al., 2024)"],
      ["Chunking 512/128", "256 (perte de contexte) ; 1024 (dilution)", "Configuration validée par la survey de référence (Gao et al., 2023)"],
      ["Base vectorielle : Qdrant", "FAISS ; Pinecone (propriétaire)", "HNSW : meilleur compromis précision/latence (Malkov & Yashunin, 2018) ; filtrage vecteur + métadonnées ; auto-hébergeable"],
      ["Text-to-SQL : DIN-SQL", "RAT-SQL (fine-tuning lourd) ; PICARD", "85,3 % EA sans fine-tuning ; chaque étape traçable (Pourreza & Rafiei, 2023)"],
      ["Routeur : DeBERTa-v3 + fallback LLM", "LLM-as-router seul ; classifieur seul", "Latence ~ms + flexibilité sur les cas ambigus ; verrou identifié par Gao et al. (2023)"],
      ["Guardrails : taxonomie NeMo", "Constitutional AI", "Programmable sans réentraînement (Rebedea et al., 2023) ; adaptation aux principes ONU"],
      ["Évaluation : RAGAS + EA + SUS", "Évaluation humaine seule", "RAGAS corrèle 0,80 avec les juges humains (Es et al., 2024) ; EA standard Spider ; SUS validé (Brooke, 1996)"],
      ["Mode démo hors-ligne interchangeable", "Démo dépendante d'API externes", "Soutenance sans risque réseau ; substitution par inversion de dépendance ; les composants légers servent de baselines"],
    ],
    [2400, 2900, 4700]),
  saut(),

  /* ============ 7. MÉTHODOLOGIE ============ */
  h1("7. Méthodologie et protocole d'évaluation"),
  p("Recherche-action appliquée (Baskerville, 1999 ; cycle de Susman & Evered, 1978) en cinq phases : (1) analyse des besoins et cartographie des données ANSD — entretiens semi-directifs et analyse des logs du site ; (2) conception — modélisation UML, contrats d'interface OpenAPI, matrice de décision multicritères ; (3) implémentation itérative en cinq sprints (RAG ; Text-to-SQL ; orchestrateur + guardrails ; interface + API ; intégration) ; (4) évaluation ; (5) rédaction et valorisation (article court visé : AFRICOMM, CARI ou TALN)."),
  h2("7.1 Protocole d'évaluation multidimensionnel"),
  bullet(null, [{ text: "Évaluation intrinsèque RAG : ", bold: true }, { text: "RAGAS (faithfulness, answer relevancy, context precision) sur un corpus documentaire ANSD ; comparaison retrieval dense (BGE-M3) vs baseline lexicale (TF-IDF) selon Karpukhin et al. (2020)." }]),
  bullet(null, [{ text: "Évaluation Text-to-SQL : ", bold: true }, { text: "Execution Accuracy sur 50 requêtes de référence spécifiques au schéma ANSD, préférée à l'Exact Set Match car des SQL syntaxiquement différents peuvent être sémantiquement équivalents (Zhong et al., 2020)." }]),
  bullet(null, [{ text: "Évaluation du routage : ", bold: true }, { text: "accuracy, F1 macro et matrice de confusion en validation croisée stratifiée 5 plis (corpus réduit : un split unique aurait une variance élevée, Kohavi, 1995) ; test du χ² d'indépendance." }]),
  bullet(null, [{ text: "Évaluation de bout en bout : ", bold: true }, { text: "jeu de 120 questions (50 SQL, 50 RAG, 20 hybrides) avec réponses et sources de référence, inspiré de la méthodologie STaRK (Wu et al., 2024) ; test t de Student apparié hybride vs voies isolées (H2)." }]),
  bullet(null, [{ text: "Évaluation extrinsèque : ", bold: true }, { text: "étude utilisateur avec 15 participants (étudiants, chercheurs, agents ANSD), System Usability Scale (Brooke, 1996) et questionnaire adapté de Lund (2001), consentement éclairé." }]),
  h2("7.2 Considérations éthiques"),
  p("Aucune donnée personnelle n'est traitée (données ANSD publiques ; confidentialité des répondants garantie en amont par l'ANSD). Toute réponse est accompagnée de sa source (transparence algorithmique). Les participants à l'évaluation signent un formulaire de consentement."),
  saut(),

  /* ============ 8. PROTOTYPE ET RÉSULTATS PRÉLIMINAIRES ============ */
  h1("8. Prototype réalisé et résultats préliminaires"),
  p("Un prototype fonctionnel complet a été développé (environ 1 500 lignes de Python documentées, API FastAPI/OpenAPI, interface web, conteneurisation Docker). Il s'exécute dans deux modes strictement interchangeables par inversion de dépendance : un mode production (DeepSeek-V3, BGE-M3 + Qdrant, DeBERTa-v3) et un mode démonstration entièrement hors-ligne et déterministe (composants légers servant de baselines), garantissant une soutenance reproductible sans dépendance réseau. Neuf tests unitaires et d'intégration couvrent le chunking, les quatre rails, la sécurité SQL et les parcours de bout en bout."),
  table(["Composant", "Métrique", "Résultat (mode démo, reproductible)", "Cible production"],
    [
      ["Routage — baseline TF-IDF + rég. logistique (CV 5 plis, n = 91)", "Accuracy / F1 macro", "0,78 / 0,73 — χ² : p < 10⁻¹⁵", "> 0,90 avec DeBERTa-v3 (H1)"],
      ["Text-to-SQL (10 requêtes de référence)", "Execution Accuracy", "10/10", "≥ 0,85 sur 50 requêtes (OS2)"],
      ["RAG (5 questions documentaires)", "Fidélité lexicale (proxy)", "0,97", "Faithfulness RAGAS > 0,85 (H2)"],
      ["Guardrails (topique, politique, injection, fidélité, SQL)", "Tests unitaires", "5/5 rails validés", "Hallucination < 5 % (H3)"],
    ],
    [3300, 1900, 2600, 2200]),
  p("Résultat déjà exploitable scientifiquement : la matrice de confusion de la baseline concentre les erreurs sur la classe HYBRID (8/20 correctement classées). Ce constat justifie empiriquement — et non plus seulement théoriquement — les deux décisions d'architecture correspondantes : le fallback LLM du niveau 2 pour les cas ambigus et le fine-tuning de DeBERTa-v3 en production.", { para: { spacing: { before: 160, after: 140, line: 300 } } }),
  espace(),

  /* ============ 9. CONTRIBUTIONS ET CALENDRIER ============ */
  h1("9. Contributions attendues et plan de travail"),
  bullet(null, [{ text: "C1 — Conceptuelle : ", bold: true }, { text: "une architecture de référence pour les chatbots d'instituts de statistique, justifiée décision par décision." }]),
  bullet(null, [{ text: "C2 — Technique : ", bold: true }, { text: "un système open source complet (RAG français optimisé, Text-to-SQL adapté au schéma ANSD, orchestrateur à deux niveaux avec métrique de confiance, guardrails conformes aux principes ONU)." }]),
  bullet(null, [{ text: "C3 — Empirique : ", bold: true }, { text: "un protocole d'évaluation multidimensionnelle (RAGAS + Execution Accuracy + SUS) et le premier jeu de test de question-réponse statistique en français appliqué à un cas africain réel (réponse à L3)." }]),
  bullet(null, [{ text: "C4 — Méthodologique : ", bold: true }, { text: "un cadre reproductible (Docker, tests, baselines) de déploiement d'agents conversationnels fiables dans des administrations aux ressources limitées." }]),
  espace(),
  p("Plan sur 12 semaines (40 h/semaine, marge de 2 semaines) : S1-S2 analyse des besoins et architecture ; S3-S4 ingestion et pipeline RAG ; S5 Text-to-SQL ; S6 orchestrateur ; S7 guardrails ; S8 interface et API ; S9 tests ; S10 évaluation intrinsèque ; S11 évaluation utilisateur et tests statistiques ; S12 finalisation du mémoire et de la soutenance. L'existence du prototype (section 8) sécurise ce calendrier : les sprints consistent à substituer les composants de production aux baselines et à ingérer les données réelles de l'ANSD."),
  saut(),

  /* ============ 10. RÉFÉRENCES ============ */
  h1("10. Références bibliographiques"),
  p("Format APA 7. Les références ont été vérifiées et corrigées (attribution exacte des auteurs et des versions).", { run: { italics: true, color: GRISF } }),
);

const refs = [
  "Androutsopoulou, A., Karacapilidis, N., Loukis, E., & Charalabidis, Y. (2019). Transforming the communication between citizens and government through AI-guided chatbots. Government Information Quarterly, 36(2), 358-367.",
  "Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). Self-RAG: Learning to retrieve, generate, and critique through self-reflection. arXiv:2310.11511.",
  "Bai, Y., Kadavath, S., Kundu, S., et al. (2022). Constitutional AI: Harmlessness from AI feedback. arXiv:2212.08073.",
  "Baskerville, R. L. (1999). Investigating information systems with action research. Communications of the AIS, 2(3).",
  "Brooke, J. (1996). SUS: A quick and dirty usability scale. Usability Evaluation in Industry, 189-194.",
  "Brown, T. B., Mann, B., Ryder, N., et al. (2020). Language models are few-shot learners. NeurIPS.",
  "Chen, J., Xiao, S., Zhang, P., Luo, D., Lian, D., & Liu, Z. (2024). BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation. arXiv:2402.03216.",
  "DeepSeek-AI. (2024). DeepSeek-V3 technical report. arXiv:2412.19437.",
  "Defog. (2024). SQLCoder-8B. Hugging Face Model Card.",
  "Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. NAACL-HLT.",
  "Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024). RAGAS: Automated evaluation of retrieval augmented generation. EACL (System Demonstrations).",
  "Eurostat. (2017). Code de bonnes pratiques de la statistique européenne.",
  "Fedus, W., Zoph, B., & Shazeer, N. (2022). Switch Transformers: Scaling to trillion parameter models with simple and efficient sparsity. JMLR, 23(120), 1-39.",
  "Gao, D., Wang, H., Li, Y., et al. (2024). Text-to-SQL empowered by large language models: A benchmark evaluation (DAIL-SQL). Proceedings of the VLDB Endowment, 17(5).",
  "Gao, Y., Xiong, Y., Gao, X., et al. (2023). Retrieval-augmented generation for large language models: A survey. arXiv:2312.10997.",
  "He, P., Gao, J., & Chen, W. (2021). DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing. arXiv:2111.09543.",
  "Janssen, M., Charalabidis, Y., & Zuiderwijk, A. (2012). Benefits, adoption barriers and myths of open data and open government. Information Systems Management, 29(4), 258-268.",
  "Ji, Z., Lee, N., Frieske, R., et al. (2023). Survey of hallucination in natural language generation. ACM Computing Surveys, 55(12), 1-38.",
  "Karpukhin, V., Oguz, B., Min, S., et al. (2020). Dense passage retrieval for open-domain question answering. EMNLP.",
  "Kitchenham, B., & Charters, S. (2007). Guidelines for performing systematic literature reviews in software engineering. EBSE Technical Report.",
  "Kohavi, R. (1995). A study of cross-validation and bootstrap for accuracy estimation and model selection. IJCAI.",
  "Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. NeurIPS.",
  "Lund, A. M. (2001). Measuring usability with the USE questionnaire. Usability Interface, 8(2), 3-6.",
  "Malkov, Y. A., & Yashunin, D. A. (2018). Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs. IEEE TPAMI, 42(4), 824-836.",
  "Muennighoff, N., Tazi, N., Magne, L., & Reimers, N. (2023). MTEB: Massive text embedding benchmark. EACL.",
  "Nations Unies. (2014). Principes fondamentaux de la statistique officielle. Résolution A/RES/68/261.",
  "Popper, K. R. (1959). The logic of scientific discovery. Routledge.",
  "Pourreza, M., & Rafiei, D. (2023). DIN-SQL: Decomposed in-context learning of Text-to-SQL with self-correction. NeurIPS.",
  "Rebedea, T., Dinu, R., Sreedhar, M., Parisien, C., & Cohen, J. (2023). NeMo Guardrails: A toolkit for controllable and safe LLM applications with programmable rails. EMNLP (System Demonstrations).",
  "Salton, G., Wong, A., & Yang, C. S. (1975). A vector space model for automatic indexing. Communications of the ACM, 18(11), 613-620.",
  "Scholak, T., Schucher, N., & Bahdanau, D. (2021). PICARD: Parsing incrementally for constrained auto-regressive decoding from language models. EMNLP.",
  "Shazeer, N., Mirhoseini, A., Maziarz, K., et al. (2017). Outrageously large neural networks: The sparsely-gated mixture-of-experts layer. ICLR.",
  "Susman, G. I., & Evered, R. D. (1978). An assessment of the scientific merits of action research. Administrative Science Quarterly, 23(4), 582-603.",
  "Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention is all you need. NeurIPS.",
  "Wang, B., Shin, R., Liu, X., Polozov, O., & Richardson, M. (2020). RAT-SQL: Relation-aware schema encoding and linking for Text-to-SQL parsers. ACL.",
  "Wu, S., Zhao, S., Yasunaga, M., et al. (2024). STaRK: Benchmarking LLM retrieval on textual and relational knowledge bases. NeurIPS Datasets and Benchmarks.",
  "Yan, S.-Q., Gu, J.-C., Zhu, Y., & Ling, Z.-H. (2024). Corrective retrieval augmented generation. arXiv:2401.15884.",
  "Yu, T., Zhang, R., Yang, K., et al. (2018). Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and Text-to-SQL task. EMNLP.",
  "Zhong, R., Yu, T., & Klein, D. (2020). Semantic evaluation for Text-to-SQL with distilled test suites. EMNLP.",
  "Zuiderwijk, A., Janssen, M., & Dwivedi, Y. K. (2021). Acceptance and use predictors of open data technologies. Government Information Quarterly, 38(2).",
];
refs.forEach(r => contenu.push(new Paragraph({
  spacing: { after: 90, line: 270 }, indent: { left: 360, hanging: 360 },
  children: [new TextRun({ text: r, size: 19, font: "Calibri", color: "333333" })],
})));

/* ============ DOCUMENT ============ */
const doc = new Document({
  features: { updateFields: true },
  numbering: { config: [{ reference: "puces", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] }] },
  styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
  sections: [{
    properties: { page: { margin: { top: 1100, bottom: 1100, left: 1250, right: 1250 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "RAMA-ANSD — Document scientifique de présentation — page ", size: 16, color: GRISF }),
                 new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GRISF })] })] }) },
    children: [...garde, ...toc, ...contenu],
  }],
});

Packer.toBuffer(doc).then(b => {
  fs.writeFileSync(__dirname + "/RAMA-ANSD_Presentation_Scientifique.docx", b);
  console.log("docx OK");
});
