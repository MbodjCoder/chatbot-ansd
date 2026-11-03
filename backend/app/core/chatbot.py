"""
Service principal : assemblage des quatre composants + sessions + ressources.

Flux d'une requete (diagramme de sequence, memoire chap. Conception) :
  question -> [Contextualisation conversationnelle] -> [Guardrails entree]
           -> [Cache LRU] -> [Orchestrateur f(q)] -> SQL | RAG | HYBRID
           -> [Synthese (production) | concatenation (demo)]
           -> [Guardrails sortie : fidelite] -> reponse + sources + liens ANSD

Sessions conversationnelles : historique borne par session ; les questions de
suivi elliptiques ("Et en 2023 ?") sont reformulees :
  - demo       : concatenation deterministe avec le tour precedent ;
  - production : reecriture par LLM (question rewriting, Vakulenko et al. 2021),
                 avec repli deterministe en cas d'echec (meme interface).

En mode production, la voie HYBRID fait l'objet d'une synthese finale par LLM
(un texte unique et coherent) contrainte aux chiffres fournis ; le rail de
fidelite numerique reste applique en aval (defense en profondeur).

Chaque reponse comporte les liens vers les publications officielles ANSD
pertinentes (base data/resources.json, URLs verifiees) : c'est l'objectif
"acces a l'information et navigation" du memoire.
"""
from __future__ import annotations
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core import followups, smalltalk, telemetry, geo
from app.core.catalogue import CatalogueANADS
from app.core.resources import ResourceLinker
from app.guardrails.rails import check_input, check_output_faithfulness, _DOMAIN_STEMS
from app.llm.client import get_llm, MockLLM
from app.rag.pipeline import RAGPipeline
from app.router.orchestrator import Orchestrator
from app.sql.pipeline import TextToSQLPipeline

BASE_DOCS = Path(settings.database_path).parent / "documents"

SESSION_TTL_S = 3600          # duree de vie d'une session inactive
SESSION_MAX_TURNS = 8         # historique borne (fenetre glissante)
MAX_SESSIONS = 500            # protection memoire

# Indices d'une question de suivi elliptique (anaphore / ellipse).
# Regle volontairement restrictive : un faux positif contextualiserait a tort
# un message autonome (cause du bug historique "salut -> reponse precedente",
# desormais aussi intercepte en amont par la couche small talk).
_FOLLOWUP_PREFIXES = ("et ", "puis ", "ensuite", "quid")
_FOLLOWUP_PRONOUNS = re.compile(
    r"\b(cette?|ces|celui|celle|la[- ]bas|meme(s)?)\b|"
    r"\b(ce chiffre|cet indicateur|cette annee[- ]la|y en a)\b", re.I)

# Demande explicite de lien/document : "ou telecharger X", "donne le lien..."
# Cette classe de questions est servie DIRECTEMENT par la base de liens
# verifies (voie NAV) : la reponse est structurellement toujours juste,
# la ou une extraction de phrases peut confondre deux "rapports".
# Recherche dans le catalogue ANADS : "quelles enquetes sur la sante ?",
# "y a-t-il des microdonnees sur l'agriculture ?", "cherche des donnees sur..."
_CATALOG_INTENT = re.compile(
    r"(quelle?s?|liste|existe|y a[- ]t[- ]il|cherche|avez[- ]vous|dispose)"
    r".{0,40}\b(enquete|etude|microdonnee|jeu de donnee|dataset|donnee)s?\b"
    r".{0,20}\b(sur|concernant|portant|relative|a propos|de la|du|d')"
    r"|dans le catalogue|catalogue anads|\banads\b.{0,30}\bsur\b",
    re.I)

# Demande d'ACCES AUX DONNEES / DOCUMENTS (le coeur du service : faciliter
# l'acces). "je veux les donnees sur la peche", "statistiques de la peche",
# "chiffres sur le tourisme"... Ces formulations d'acquisition ne sont pas
# interrogatives : elles doivent mener directement aux FICHES et LIENS
# officiels (ANADS + Annuaire statistique + Open Data), jamais a une
# extraction RAG qui repondrait "information non disponible".
_DATA_ACCESS_INTENT = re.compile(
    r"\b(donnee|statistique|chiffre|data|microdonnee)s?\b"
    r"\s+(sur|de|du|de la|des|d|concernant|relati\w*|a propos|pour|portant)\b"
    r"|\b(je\s+(veux|voudrais|souhaite|cherche|aimerais|desire)|"
    r"donne(z|[- ]?moi)?|montre(z|[- ]?moi)?|"
    r"avoir|obtenir|acceder|trouver|telecharger|consulter)\b"
    r".{0,25}\b(donnee|statistique|chiffre|data|microdonnee|dataset)s?\b",
    re.I)

# Portails SPECIALISES par theme (partenaires officiels producteurs de la
# donnee). Ajoutes aux liens quand le theme est detecte, en plus des portails
# transversaux (SES, Annuaire, Open Data). URLs verifiees dans resources.json.
_THEME_PORTAILS = [
    (re.compile(r"\b(agricol\w*|agriculture|elevage|betail|cultur\w*|horticol\w*|"
                r"recolte|semence|rural|dapsa|arachide|cereal\w*|vivrier\w*)\b", re.I),
     ["dapsa", "ipar"]),
]

# Mots-outils français fréquents : servent à décider qu'une question est « déjà
# propre » (aucune faute probable) et qu'on peut SAUTER la normalisation LLM.
_MOTS_OUTILS = {
    "quel", "quelle", "quels", "quelles", "est", "sont", "etait", "etaient",
    "combien", "comment", "pourquoi", "quand", "que", "qui", "quoi", "dont",
    "les", "des", "une", "dans", "avec", "pour", "par", "sur", "sous", "aux",
    "entre", "plus", "moins", "vers", "chez", "cette", "cette", "leur", "leurs",
    "taux", "nombre", "moyenne", "total", "totale", "evolution", "donne",
    "donnez", "veux", "voudrais", "cherche", "liste", "dernier", "derniere",
    "dernieres", "recent", "recente", "actuel", "actuelle", "annee", "annees",
    "region", "regions", "national", "nationale", "senegalais", "senegalaise",
    "selon", "ainsi", "aussi", "meme", "tous", "toutes", "quelle", "existe",
    "trouver", "telecharger", "consulter", "acceder", "montre", "afficher",
    "svp", "merci", "bonjour", "salut", "peux", "peut", "veut", "faire",
}

_NAV_INTENT = re.compile(
    r"\b(ou|où)\s+(trouver|telecharger|t[ée]l[ée]charger|consulter|acc[ée]der|"
    r"voir|obtenir|lire)\b"
    r"|comment\s+(acc[ée]der|t[ée]l[ée]charger|obtenir|consulter)\b"
    r"|donne(z|[- ]moi)?\s+le\s+lien"
    r"|je\s+cherche\s+(le|la|les|un|une)\s+(rapport|document|publication|note|lien)",
    re.I)

REWRITE_SYSTEM = """REWRITE_QUESTION - Tu reformules une question de suivi en une
question autonome et complete, en francais, en t'appuyant sur l'historique de
conversation fourni. Reponds UNIQUEMENT avec la question reformulee, sans
commentaire. Conserve toutes les entites (annees, regions, indicateurs)."""

NORMALIZE_SYSTEM = """NORMALIZE_QUERY - Tu corriges une question posee a un assistant
statistique de l'ANSD (Senegal). Corrige UNIQUEMENT les fautes de frappe,
d'orthographe et de grammaire, et remets une ponctuation correcte. Regles :
- garde EXACTEMENT le sens et l'intention de l'utilisateur ;
- garde la langue d'origine (francais) ;
- n'ajoute AUCUNE information, ne reponds pas, n'explique pas ;
- conserve les entites (annees, regions, indicateurs, sigles comme RGPH, EHCVM) ;
- si la question est deja correcte, renvoie-la telle quelle.
Reponds UNIQUEMENT par la question corrigee, sans guillemets ni commentaire."""

SYNTHESIS_SYSTEM = """SYNTHESIS - Tu es RAMA, l'assistant statistique officiel de
l'ANSD. On te fournit (1) un resultat chiffre issu de la base de donnees
officielle et (2) un extrait documentaire methodologique. Redige UNE reponse
unique, fluide et structuree en francais qui repond a la question :
- commence par le chiffre demande (en **gras**) avec sa periode et sa source ;
- enchaine avec l'explication methodologique utile ;
- n'utilise AUCUN chiffre absent des elements fournis ;
- neutre et precis (Principe 1 de la statistique officielle)."""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().strip())
                   if unicodedata.category(c) != "Mn")


@dataclass
class ChatResponse:
    answer: str
    route: str = "-"
    confidence: float = 0.0
    router_level: str = "-"
    sql: str | None = None
    sources: list = field(default_factory=list)
    guardrail: str = "ok"
    latency_ms: int = 0
    session_id: str = ""
    message_id: str = ""
    data: dict | None = None   # resultat SQL structure (colonnes + lignes)
    links: list = field(default_factory=list)  # publications ANSD pertinentes
    suggestions: list = field(default_factory=list)  # questions de suivi proposees
    cached: bool = False


@dataclass
class _Session:
    history: list = field(default_factory=list)  # [(question, answer, route)]
    last_seen: float = field(default_factory=time.time)
    last_link_urls: frozenset = frozenset()
    shown_suggestions: set = field(default_factory=set)  # cles deja proposees


class ANSDChatbot:
    def __init__(self):
        self.llm = get_llm()
        self.is_mock = isinstance(self.llm, MockLLM)
        # Adaptation latence/qualite au fournisseur (decisions #40 et #43) :
        # sur une inference locale lente (Ollama/CPU), chaque appel LLM coute
        # 30 a 90 s — les variantes deterministes (substitution d'entites,
        # extraction ancree) prennent le relais ; sur une API distante rapide
        # (Groq, DeepSeek...), le LLM assure reecriture, redaction et synthese.
        fast_provider = settings.llm_provider != "ollama"
        self.use_llm_aux = (not self.is_mock
                            and (settings.llm_aux == "llm"
                                 or (settings.llm_aux == "auto" and fast_provider)))
        use_llm_gen = (not self.is_mock
                       and (settings.llm_gen == "llm"
                            or (settings.llm_gen == "auto" and fast_provider)))
        gen_llm = self.llm if use_llm_gen else MockLLM()
        self.gen_abstractive = use_llm_gen
        self.rag = RAGPipeline(gen_llm)
        n = self.rag.ingest_directory(BASE_DOCS)
        # Voie SQL : gabarits d'abord (#39). Le repli LLM (DIN-SQL) pour la
        # longue traine n'est active QUE sur un fournisseur rapide (gen_llm).
        # CORRECTIF LATENCE : sur un LLM local lent (Ollama), une question sans
        # gabarit (ex. "premier president du Senegal" = pas une statistique)
        # declenchait un appel Ollama de 60-90 s pour finir sur "aucune donnee".
        # En mode eclair, gen_llm = MockLLM (gabarits seuls) -> reponse immediate.
        self.sql = TextToSQLPipeline(gen_llm)
        self.router = Orchestrator(gen_llm)      # fallback de routage rapide
        self.linker = ResourceLinker()
        self.catalogue = CatalogueANADS()
        self.docs_indexed = n
        self._lexique = self._construire_lexique()
        self._sessions: dict[str, _Session] = {}
        self._cache: dict[str, tuple[float, ChatResponse]] = {}
        # Verrou d'etat partage (P0-1) : le serveur traite les requetes dans
        # un pool de threads ; sessions et cache sont donc accedes en
        # concurrence. RLock (reentrant) = exclusion mutuelle sans interblocage
        # si une section verrouillee en appelle une autre. Granularite fine :
        # on ne verrouille QUE les acces a l'etat, jamais le calcul de reponse,
        # pour ne pas serialiser tout le trafic. Voir docs/EXPLICATIONS.md P0-1.
        self._lock = threading.RLock()

    # ------------------------------------------------------------ sessions
    def _session(self, session_id: str | None) -> tuple[str, _Session]:
        now = time.time()
        with self._lock:
            # 1) purge des sessions expirees (TTL)
            if len(self._sessions) > MAX_SESSIONS:
                self._sessions = {k: s for k, s in self._sessions.items()
                                  if now - s.last_seen < SESSION_TTL_S}
            # 2) cap DUR (protection DoS memoire) : si un client inonde d'ID
            #    de session uniques dans le TTL, on evince les plus anciens
            #    (LRU) pour borner strictement l'empreinte memoire
            while len(self._sessions) >= MAX_SESSIONS:
                oldest = min(self._sessions, key=lambda k: self._sessions[k].last_seen)
                del self._sessions[oldest]
            # 3) validation de l'id fourni par le client (evite les cles
            #    aberrantes : longueur/charset bornes)
            if session_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
                session_id = None
            sid = session_id or telemetry.new_id()
            sess = self._sessions.get(sid)
            if sess is None or now - sess.last_seen > SESSION_TTL_S:
                sess = _Session()
                self._sessions[sid] = sess
            sess.last_seen = now
        return sid, sess

    def _remember(self, sess: _Session, question: str, answer: str,
                  route: str) -> None:
        """Mutation de l'historique de session sous verrou : deux requetes
        concurrentes sur la MEME session (double-clic, flux + requete) ne
        corrompent pas la liste."""
        with self._lock:
            sess.history.append((question, answer, route))
            if len(sess.history) > SESSION_MAX_TURNS:
                sess.history = sess.history[-SESSION_MAX_TURNS:]

    @staticmethod
    def _is_followup(question: str) -> bool:
        q = question.lower().strip()
        # signaux explicites : connecteur de suite, anaphore, ou message tres
        # court porteur d'une entite de restriction (annee, trimestre)
        return (q.startswith(_FOLLOWUP_PREFIXES)
                or bool(_FOLLOWUP_PRONOUNS.search(q))
                or (len(q.split()) <= 4
                    and bool(re.search(r"\b(19|20)\d{2}\b|trimestre|t[1-4]\b", q))))

    def _history_text(self, sess: _Session, turns: int = 4) -> str:
        return "\n".join(f"Q: {q}\nR: {a[:300]}"
                         for q, a, _ in sess.history[-turns:])

    def _construire_lexique(self) -> set:
        """Vocabulaire du domaine (corpus + régions + mots-outils) pour juger
        qu'une question est déjà bien écrite → éviter un appel LLM inutile."""
        lex = set()
        for p in Path(BASE_DOCS).glob("*.md"):
            try:
                lex.update(re.findall(r"[a-z]{4,}", _fold(p.read_text(encoding="utf-8"))))
            except Exception:
                pass
        try:
            from app.sql.templates import REGIONS
            lex |= {_fold(r) for r in REGIONS}
        except Exception:
            pass
        return lex | _MOTS_OUTILS

    def _looks_clean(self, question: str) -> bool:
        """Vrai si tous les mots « pleins » sont connus (corpus, domaine,
        régions, mots-outils) → aucune faute probable, normalisation inutile."""
        toks = re.findall(r"[a-z]{4,}", _fold(question))
        for t in toks:
            if t in self._lexique:
                continue
            if any(t.startswith(s) or s.startswith(t) for s in _DOMAIN_STEMS):
                continue
            return False
        return True

    def _normalize_query(self, question: str) -> str:
        """Correction des fautes (frappe, orthographe, grammaire) par le LLM,
        AVANT guardrail/routage : une question mal orthographiee ("kel é le to
        de chaumage a dakr") est ainsi comprise comme "Quel est le taux de
        chomage a Dakar ?". Active uniquement avec un fournisseur rapide
        (use_llm_aux) ; repli silencieux sur la question d'origine.
        Garde-fous : longueur plausible, pas de refus/meta injecte par le LLM.
        OPTIMISATION LATENCE : si la question est deja bien ecrite (tous les
        mots connus), on saute l'appel LLM -> reponse plus rapide et moins de
        charge sur le fournisseur (le gros du trafic legitime est deja propre)."""
        if not self.use_llm_aux or len(question) > 300:
            return question
        if self._looks_clean(question):
            return question
        try:
            resp = self.llm.complete(NORMALIZE_SYSTEM, question,
                                     temperature=0.0, max_tokens=120)
            corrige = resp.text.strip().strip('"').strip()
            # garde-fous : longueur du meme ordre, non vide, pas une phrase meta
            if (corrige and 0.5 * len(question) <= len(corrige) <= 2.5 * len(question) + 20
                    and not re.match(r"(je |desole|il semble|voici|la question)", corrige.lower())):
                return corrige
        except Exception:
            pass
        return question

    def _followups(self, question: str, answer: str, sql: str | None,
                   docs: list[str], sess: _Session, k: int = 3) -> list[str]:
        """Suggestions de suivi EVOLUTIVES et non redondantes.
        1. Sur fournisseur rapide : generation LLM ancree dans la reponse
           reelle (pertinence maximale, renouvelee a chaque tour).
        2. Complement / repli : gabarits deterministes par sujet.
        Dedoublonnage a l'echelle de la SESSION (`shown_suggestions`) : une
        meme suggestion n'est jamais reaffichee, ni une question deja posee."""
        avoid = {followups._fold(q)[:60] for q, _, _ in sess.history}
        avoid |= {followups._fold(question)[:60]} | set(sess.shown_suggestions)
        out: list[str] = []
        if self.use_llm_aux and answer and len(answer) > 40:
            try:
                out = followups.suggest_llm(self.llm.complete, question,
                                            answer, avoid, k)
            except Exception:
                out = []
        if len(out) < k:
            deja = avoid | {followups._fold(s)[:60] for s in out}
            for s in followups.suggest(question, sql, docs, [], k=8, avoid=deja):
                key = followups._fold(s)[:60]
                if followups._too_close(key, deja):
                    continue
                out.append(s)
                deja.add(key)
                if len(out) >= k:
                    break
        out = out[:k]
        sess.shown_suggestions |= {followups._fold(s)[:60] for s in out}
        # bornage memoire de la trace des suggestions montrees
        if len(sess.shown_suggestions) > 60:
            sess.shown_suggestions = set(list(sess.shown_suggestions)[-40:])
        return out

    @staticmethod
    def _sujet_phrase(question: str) -> str:
        """Extrait « sur la pêche » d'une demande d'accès, pour une réponse
        naturelle. Repli neutre si rien d'exploitable."""
        m = (re.search(r"\bsur\s+(.{3,55})$", question.strip(), re.I)
             or re.search(r"\b(?:concernant|portant sur|à propos d[e']|de la|du|des|de l')\s+(.{3,55})$",
                          question.strip(), re.I))
        if m:
            suj = re.sub(r"[\s?.!,;:]+$", "", m.group(1)).strip()
            if suj:
                return f"sur {suj}"
        return "correspondant à votre demande"

    @staticmethod
    def _theme_portail_ids(question: str) -> list[str]:
        """Ids de portails spécialisés selon le thème détecté (ex. agriculture
        -> DAPSA, IPAR)."""
        for rx, ids in _THEME_PORTAILS:
            if rx.search(question):
                return ids
        return []

    def _acces_donnees_links(self, question: str, etudes: list[dict]) -> list[dict]:
        """Cartes de liens : fiches ANADS pertinentes + portails spécialisés du
        thème (DAPSA, IPAR…) + portails transversaux (SES, Bases = Annuaire +
        Open Data, ANADS, Publications). Uniquement des URLs vérifiées."""
        out, seen = [], set()
        for e in etudes[:4]:
            if e["url"] in seen:
                continue
            seen.add(e["url"])
            out.append({"titre": e["titre"][:70], "url": e["url"],
                        "type": "catalogue"})
        ordre = self._theme_portail_ids(question) + \
            ["ses_nationales", "ansd_bases", "anads", "ansd_publications"]
        for rid in ordre:
            r = self.linker.resources.get(rid)
            if r and r["url"] not in seen:
                seen.add(r["url"])
                out.append({"titre": r["titre"], "url": r["url"],
                            "type": r.get("type", "page")})
        return out[:8]

    def _acces_donnees_answer(self, question: str, etudes: list[dict]) -> str:
        """Réponse d'accès aux données : fiches ANADS cliquables (grounding
        structurel) + portails Annuaire/Open Data/Publications, toujours liés.
        Jamais « information non disponible »."""
        R = self.linker.resources
        bases = R.get("ansd_bases")
        anads = R.get("anads")
        pubs = R.get("ansd_publications")
        ses = R.get("ses_nationales")
        sujet = self._sujet_phrase(question)
        if etudes:
            lignes = []
            for e in etudes[:5]:
                annees = e["annee_debut"] or "?"
                if e["annee_fin"] and e["annee_fin"] != e["annee_debut"]:
                    annees += f"-{e['annee_fin']}"
                prod = (e["producteur"] or "").split(",")[0][:55]
                lignes.append(f"- **[{e['titre']}]({e['url']})** ({annees}"
                              + (f", {prod}" if prod else "") + ")")
            tete = (f"Voici les données officielles {sujet}. "
                    "Dans l’**archive nationale des microdonnées (ANADS)** — "
                    "chaque titre ouvre la fiche complète (documentation, "
                    "questionnaires, demande d’accès aux fichiers, tous "
                    "formats) :\n" + "\n".join(lignes))
        else:
            tete = (f"Je n’ai pas de microdonnées précises indexées {sujet}, "
                    "mais l’information est accessible directement via les "
                    "portails officiels ci-dessous.")
        portails = []
        if ses:
            portails.append(f"la **[Situation Économique et Sociale du Sénégal (SES)]"
                            f"({ses['url']})**, qui couvre tous les secteurs")
        if bases:
            portails.append(f"l’**[Annuaire statistique du Sénégal]({bases['url']})**")
            portails.append(f"la **[plateforme Open Data du Sénégal (ODP)]({bases['url']})**")
        # portails spécialisés du thème (producteurs de la donnée)
        for rid in self._theme_portail_ids(question):
            r = R.get(rid)
            if r:
                portails.append(f"le portail **[{r['titre'].split('—')[0].strip()}]"
                                f"({r['url']})**")
        if anads:
            portails.append(f"l’archive **[ANADS]({anads['url']})** (microdonnées)")
        if pubs:
            portails.append(f"les **[publications de l’ANSD]({pubs['url']})**")
        if portails:
            tete += ("\n\nPour des séries agrégées ou d’autres formats, "
                     "consultez aussi " + " ; ".join(portails) + ".")
        return tete

    def _geo_intercept(self, question: str, sid: str, sess: "_Session",
                       message_id: str, t0: float) -> "ChatResponse | None":
        """Garde géographique (P1, « incontestable ») : on ne substitue JAMAIS
        un chiffre d'une autre entité à celle demandée. N'intervient que pour
        une ZONE naturelle (agrégat) ou un LIEU non résoluble ; sinon None
        (le pipeline normal traite région/national)."""
        from app.sql.pipeline import _fr
        sc = geo.scope(question)
        if sc["kind"] not in ("zone", "unknown"):
            return None

        def _fin(answer: str, links: list, sugg: list, level: str,
                 data: dict | None = None) -> "ChatResponse":
            sess.last_link_urls = frozenset(l["url"] for l in links)
            resp = ChatResponse(
                answer=answer, route="GEO", confidence=1.0, router_level=level,
                guardrail="ok", links=links, suggestions=sugg, data=data,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                session_id=sid, message_id=message_id)
            self._remember(sess, question, answer, "GEO")
            self._log(question, question, resp)
            return resp

        # -- lieu non résoluble : réponse honnête, sans chiffre substitué -----
        if sc["kind"] == "unknown":
            place = sc["place"]
            answer = (
                f"Je ne dispose pas de données pour « **{place}** ». L’ANSD "
                "publie ces statistiques au niveau **national** et pour les "
                f"**14 régions administratives** du Sénégal ({geo.regions_examples()}…). "
                "Précisez l’une de ces régions (ou « Sénégal » pour le total "
                "national), ou consultez les publications officielles ci-dessous.")
            links = [self.linker.fallback("ansd_publications")]
            sugg = ["Quelle est la population du Sénégal en 2023 ?",
                    "Quelle est la population de Dakar en 2023 ?"]
            return _fin(answer, links, sugg, "geo-inconnu")

        # -- zone naturelle : agrégation VALIDE (population, superficie) -------
        zone_nom = sc["zone"].replace("-", " ").title()
        membres = sc["regions"]
        noms = [geo.display(r) for r in membres]
        liste = (" et ".join([", ".join(noms[:-1]), noms[-1]])
                 if len(noms) > 1 else noms[0])
        ind = geo.indicator(question)
        inlist = ",".join("'%s'" % r for r in membres)

        if ind in ("population", "superficie"):
            if ind == "population":
                sql = ("SELECT r.nom, d.population FROM demographie d JOIN regions r "
                       f"ON r.id = d.region_id WHERE lower(r.nom) IN ({inlist}) "
                       "AND d.annee = (SELECT MAX(annee) FROM demographie) "
                       "ORDER BY d.population DESC;")
            else:
                sql = ("SELECT nom, superficie_km2 FROM regions "
                       f"WHERE lower(nom) IN ({inlist}) ORDER BY superficie_km2 DESC;")
            try:
                res = self.sql.source.execute(sql)
                rows, cols = res.rows, res.columns
            except Exception:
                rows, cols = [], []
            if rows and len(rows) == len(membres):
                total = sum(row[1] for row in rows)
                if ind == "population":
                    detail = " ; ".join(f"{r[0]} : {_fr(r[1])}" for r in rows)
                    answer = (
                        f"La **{zone_nom}** (zone naturelle regroupant les régions "
                        f"de {liste}) comptait **{_fr(total)} habitants** au RGPH-5 "
                        f"(2023). Détail par région : {detail}. *(La {zone_nom} "
                        "n’est pas une région administrative ; ce total agrège les "
                        "régions qui la composent.)*")
                else:
                    detail = " ; ".join(f"{r[0]} : {_fr(r[1])} km²" for r in rows)
                    answer = (
                        f"La **{zone_nom}** (régions de {liste}) couvre "
                        f"**{_fr(total)} km²**, somme des superficies régionales. "
                        f"Détail : {detail}.")
                data = {"columns": cols, "rows": [list(r) for r in rows]}
                links = [self.linker.fallback("ansd_indicateurs")]
                sugg = [f"Quelle est la population de {n} en 2023 ?"
                        for n in noms[:2]]
                return _fin(answer, links, sugg, "geo-zone", data)

        # -- zone + taux (pauvreté, densité, Gini) : NON agrégeable -----------
        # additionner des taux serait faux : on l'explique et on oriente.
        answer = (
            f"La **{zone_nom}** est une zone naturelle regroupant les régions de "
            f"{liste} ; ce n’est pas une région administrative, et cet indicateur "
            "(un taux) ne s’additionne pas entre régions. Je peux en revanche vous "
            f"le donner pour chacune de ces régions ({liste}).")
        links = [self.linker.fallback("ansd_indicateurs")]
        sugg = [f"Quel est le taux de pauvreté à {n} ?" for n in noms[:2]]
        return _fin(answer, links, sugg, "geo-zone-taux")

    def _contextualize(self, question: str, sess: _Session) -> str:
        """Reformulation d'une question de suivi.
        1. Substitution d'entites (annee, region) : si le suivi apporte une
           nouvelle valeur d'une entite presente dans la question precedente,
           on substitue -> reformulation EXACTE, routage identique a
           l'original (slot filling, technique standard du QA conversationnel).
        2. Sinon, reecriture LLM (si activee) avec repli concatenation."""
        if not sess.history:
            return question
        last_q = sess.history[-1][0]
        # -- substitution d'annee : "Et en 2023 ?" --------------------------
        ny = re.search(r"\b(19|20)\d{2}\b", question)
        if ny and re.search(r"\b(19|20)\d{2}\b", last_q):
            return re.sub(r"\b(19|20)\d{2}\b", ny.group(0), last_q, count=1)
        # -- substitution de region : "Et a Thies ?" ------------------------
        from app.sql.templates import REGIONS
        def find_region(text: str) -> str | None:
            t = text.lower()
            for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")]:
                t = t.replace(a, b)
            t = t.replace("saint louis", "saint-louis")
            return next((r for r in REGIONS if r in t), None)
        nr, lr = find_region(question), find_region(last_q)
        if nr and lr and nr != lr:
            # motif tolerant aux accents ("Thiès"/"Thies") et aux traits d'union
            pattern = re.sub(r"[eaio]", lambda m: {"e": "[eéèê]", "a": "[aà]",
                             "i": "[iî]", "o": "[oô]"}[m.group(0)],
                             lr.replace("-", "[- ]"))
            substituted = re.sub(pattern, nr, last_q, flags=re.I)
            if substituted != last_q:
                return substituted
        # -- reecriture LLM (fournisseur rapide) ----------------------------
        if self.use_llm_aux:
            try:
                resp = self.llm.complete(
                    REWRITE_SYSTEM,
                    f"<historique>{self._history_text(sess)}</historique>\n"
                    f"<question_de_suivi>{question}</question_de_suivi>",
                    temperature=0.0, max_tokens=150)
                rewritten = resp.text.strip().strip('"')
                if 3 <= len(rewritten.split()) <= 60:
                    return rewritten
            except Exception:
                pass  # repli deterministe ci-dessous
        return f"{question} (dans le contexte de la question precedente : {last_q})"

    # ------------------------------------------------------------ cache
    def _cache_get(self, key: str) -> ChatResponse | None:
        if not settings.cache_enabled:
            return None
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < settings.cache_ttl_s:
                return hit[1]
            self._cache.pop(key, None)
        return None

    def _cache_put(self, key: str, resp: ChatResponse) -> None:
        if not settings.cache_enabled or resp.guardrail != "ok":
            return
        with self._lock:
            if len(self._cache) >= settings.cache_max_entries:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                self._cache.pop(oldest)
            self._cache[key] = (time.time(), resp)

    # ------------------------------------------------------------ requete
    def ask(self, question: str, session_id: str | None = None,
            on_delta=None) -> ChatResponse:
        """Traite une question et renvoie la reponse complete tracee.

        `on_delta` (P0-2) : callback optionnel appele avec chaque fragment de
        texte des que le LLM le produit, sur la voie documentaire abstractive
        (fournisseur rapide). Permet un vrai streaming des tokens tout en
        conservant un unique chemin de code (pas de duplication). Sur les voies
        deterministes (instantanees), il n'est pas sollicite."""
        t0 = time.perf_counter()
        sid, sess = self._session(session_id)
        message_id = telemetry.new_id()

        # -1. Actes sociaux ("salut", "merci", "qui es-tu ?"...) : reponse
        # directe, ni contextualisation ni routage — corrige le defaut ou une
        # salutation re-declenchait la reponse precedente. Variante choisie
        # selon l'avancement de la conversation (pas d'effet perroquet).
        cat = smalltalk.detect(question)
        if cat:
            sugg = (followups.SUGGESTIONS["accueil"][:3]
                    if cat in ("greet", "help", "howru") else [])
            resp = ChatResponse(
                answer=smalltalk.respond(cat, seed=len(sess.history)),
                route="CHAT", confidence=1.0, router_level="smalltalk",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                session_id=sid, message_id=message_id, suggestions=sugg)
            self._log(question, question, resp)
            return resp
        # salutation en tete d'une vraie question -> on la retire
        question = smalltalk.strip_greeting(question)

        # 0a. Normalisation : correction des fautes de frappe/orthographe/
        # grammaire par le LLM (fournisseur rapide uniquement). Rend le systeme
        # robuste aux questions mal ecrites, en amont de tout le pipeline.
        question = self._normalize_query(question)

        # 0. Contextualisation conversationnelle (suivi elliptique)
        effective_q = question
        followup = self._is_followup(question) and bool(sess.history)
        if followup:
            effective_q = self._contextualize(question, sess)

        # 1. Rails d'entree (sur la question contextualisee)
        verdict = check_input(effective_q)
        if not verdict.allowed:
            resp = ChatResponse(answer=verdict.message, guardrail=verdict.reason,
                                latency_ms=int((time.perf_counter() - t0) * 1000),
                                session_id=sid, message_id=message_id)
            self._log(question, effective_q, resp)
            return resp

        # 1bis. Cache (questions autonomes uniquement : jamais les suivis)
        cache_key = _fold(effective_q)
        if not followup:
            hit = self._cache_get(cache_key)
            if hit is not None:
                resp = ChatResponse(**{**hit.__dict__,
                                       "session_id": sid, "message_id": message_id,
                                       "latency_ms": int((time.perf_counter() - t0) * 1000),
                                       "cached": True})
                self._remember(sess, question, resp.answer, resp.route)
                self._log(question, effective_q, resp)
                return resp

        # Les intentions se detectent sur le texte plie (sans accents) :
        # "enquête" et "enquete" doivent matcher identiquement.
        q_fold = _fold(effective_q)

        # 1ter-a. Voie ACCES AUX DONNEES / CATALOGUE. Le service existe d'abord
        # pour FACILITER L'ACCES : toute demande de donnees/documents sur un
        # theme (« je veux les donnees sur la peche », « statistiques du
        # tourisme »...) est resolue en LIENS OFFICIELS DIRECTS — les fiches
        # ANADS correspondantes (avec leur URL verifiee), plus l'Annuaire
        # statistique et la plateforme Open Data (ODP) pour les series
        # agregees. Jamais « information non disponible ». Grounding structurel
        # (chaque element provient du catalogue verifie, meme garantie que #10).
        if _CATALOG_INTENT.search(q_fold) or _DATA_ACCESS_INTENT.search(q_fold):
            etudes = self.catalogue.search(effective_q, k=5)
            answer = self._acces_donnees_answer(effective_q, etudes)
            nav_links = self._acces_donnees_links(effective_q, etudes)
            sess.last_link_urls = frozenset(l["url"] for l in nav_links)
            resp = ChatResponse(
                answer=answer, route="CATALOG", confidence=1.0,
                router_level="acces-donnees", links=nav_links,
                suggestions=self._followups(effective_q, answer, None,
                                            ["operations_enquetes_ansd.md"], sess),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                session_id=sid, message_id=message_id)
            self._remember(sess, effective_q, answer, "CATALOG")
            self._log(question, effective_q, resp)
            return resp

        # 1ter. Voie NAVIGATION : demande explicite de lien ou de document.
        # Reponse composee directement depuis la base de liens verifies —
        # jamais d'extraction hasardeuse pour cette classe de questions.
        if _NAV_INTENT.search(q_fold):
            nav_links = self.linker.links_for(effective_q, [], relax=True)
            if nav_links:
                premier = nav_links[0]
                if premier["type"] == "pdf":
                    answer = (f"Le document officiel que vous cherchez est "
                              f"**{premier['titre']}**, téléchargeable "
                              "directement ci-dessous.")
                else:
                    answer = (f"Vous trouverez cela sur la page officielle "
                              f"**{premier['titre']}**, accessible ci-dessous.")
                if len(nav_links) > 1:
                    answer += " D'autres ressources utiles sont également proposées."
                urls = frozenset(l["url"] for l in nav_links)
                sess.last_link_urls = urls
                resp = ChatResponse(
                    answer=answer, route="NAV", confidence=1.0,
                    router_level="navigation", links=nav_links,
                    suggestions=self._followups(effective_q, answer, None, [], sess),
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    session_id=sid, message_id=message_id)
                self._remember(sess, effective_q, answer, "NAV")
                self._log(question, effective_q, resp)
                return resp

        # 1quater. Garde GÉOGRAPHIQUE (P1, « incontestable ») : une question sur
        # une ZONE naturelle (Casamance…) est agrégée correctement ; un LIEU non
        # résoluble reçoit une réponse honnête — JAMAIS un chiffre national (ou
        # d'une autre entité) substitué à celle demandée. Placée avant le routage
        # -> couvre à la fois la voie SQL et la voie RAG.
        geo_resp = self._geo_intercept(effective_q, sid, sess, message_id, t0)
        if geo_resp is not None:
            if not followup:
                self._cache_put(cache_key, geo_resp)
            return geo_resp

        # 2. Routage
        decision = self.router.route(effective_q)

        # 3. Execution de la voie choisie
        parts, sources, evidence, sql_used, data = [], [], "", None, None
        history = self._history_text(sess) if sess.history else ""
        if decision.route in ("SQL", "HYBRID"):
            r = self.sql.answer(effective_q)
            parts.append(r.answer)
            sql_used = r.sql
            # « ; » entre cellules : le contrôle ne doit pas fusionner deux nombres voisins
            evidence += " ; ".join(str(x) for row in r.rows for x in row) + " ; " + " ".join(r.columns)
            sources.append({"type": "base_de_donnees", "sql": r.sql})
            if r.rows and r.columns:
                data = {"columns": r.columns, "rows": [list(row) for row in r.rows[:50]]}
        if decision.route in ("RAG", "HYBRID"):
            # streaming reel (P0-2) : uniquement la voie documentaire
            # abstractive (fournisseur rapide), jamais un chiffre non valide.
            # En HYBRID, la synthese finale re-emet le texte complet -> on ne
            # streame les tokens que sur le RAG pur.
            stream_cb = (on_delta if (on_delta and self.gen_abstractive
                                      and decision.route == "RAG") else None)
            r = self.rag.answer(effective_q, history=history, on_delta=stream_cb)
            parts.append(r.answer)
            # preuve pour le rail factuel = passages effectivement utilises,
            # renvoyes par answer() -> plus de second retrieval (P1-3)
            for c in r.chunks:
                evidence += " " + c.text
            sources += [{"type": "document", **s} for s in r.sources]

        # 3bis. Synthese finale (production, voie HYBRID) : un texte unique
        if decision.route == "HYBRID" and self.use_llm_aux and len(parts) == 2:
            try:
                synth = self.llm.complete(
                    SYNTHESIS_SYSTEM,
                    f"<question>{effective_q}</question>\n"
                    f"<resultat_base>{parts[0]}</resultat_base>\n"
                    f"<extrait_documentaire>{parts[1]}</extrait_documentaire>",
                    temperature=settings.llm_temperature)
                if synth.text.strip():
                    parts = [synth.text.strip()]
            except Exception:
                pass  # repli : concatenation
        answer = "\n\n".join(p for p in parts if p)

        # 4. Rail de sortie (fidelite numerique)
        fv = check_output_faithfulness(answer, evidence)
        if not fv.allowed:
            answer, guard = fv.message, fv.reason
        else:
            guard = "ok"

        # 5. Liens vers les publications officielles ANSD (navigation).
        # Si la reponse documentaire est un echec ("Information non
        # disponible..."), le document retenu n'etait PAS pertinent : on
        # n'en derive aucun lien (correctif du lien hors sujet constate).
        # L'appariement thematique de la QUESTION reste possible.
        echec_rag = answer.strip().startswith("Information non disponible")
        doc_sources = ([] if echec_rag else
                       [s["document"] for s in sources if s.get("type") == "document"])
        links = self.linker.links_for(effective_q, doc_sources, sql=sql_used)
        # Promesse P2 : TOUTE reponse factuelle porte au moins un lien source,
        # quel qu'en soit le type. Si aucun lien specifique n'a ete derive
        # (indicateur transversal, rail de fidelite declenche, theme non
        # apparie), on rattache une source officielle verifiee de secours.
        # On n'efface plus les liens quand ils repetent le tour precedent : la
        # source doit rester visible a chaque reponse.
        if not links and decision.route in ("SQL", "RAG", "HYBRID"):
            links = [self.linker.fallback(
                "ansd_indicateurs" if data else "ansd_publications")]
        sess.last_link_urls = frozenset(l["url"] for l in links)

        # 5ter. Liens INLINE (#78) : les mentions de ressources officielles
        # dans le texte deviennent cliquables (sur une reponse valide). On lie
        # AUSSI les titres d'etudes ANADS cites par le LLM (#86) -> chaque
        # etude nommee pointe vers sa fiche, dans n'importe quelle reponse.
        if guard == "ok":
            answer = self.linker.autolink(answer)
            answer = self.catalogue.autolink_titles(answer)

        # 5bis. Suggestions de suivi EVOLUTIVES, ancrees dans la reponse et
        # jamais redondantes (dedoublonnage a l'echelle de la session)
        sugg = self._followups(effective_q, answer, sql_used, doc_sources, sess) \
            if guard == "ok" else []

        resp = ChatResponse(
            answer=answer, route=decision.route,
            confidence=round(decision.confidence, 3),
            router_level=decision.level, sql=sql_used, sources=sources,
            guardrail=guard,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            session_id=sid, message_id=message_id, data=data, links=links,
            suggestions=sugg,
        )

        # 6. Historique + cache + journalisation
        # on memorise la question CONTEXTUALISEE : un suivi de suivi
        # ("Et a Thies ?" puis "Et a Ziguinchor ?") se resout alors par
        # substitution sur une question complete, jamais sur une ellipse
        self._remember(sess, effective_q, answer, decision.route)
        if not followup:
            self._cache_put(cache_key, resp)
        self._log(question, effective_q, resp)
        return resp

    def _log(self, question: str, effective_q: str, resp: ChatResponse) -> None:
        telemetry.log_interaction({
            "message_id": resp.message_id, "session_id": resp.session_id,
            "question": question,
            "contextualized": effective_q if effective_q != question else None,
            "route": resp.route, "confidence": resp.confidence,
            "router_level": resp.router_level, "guardrail": resp.guardrail,
            "latency_ms": resp.latency_ms, "sql": resp.sql,
            "n_sources": len(resp.sources), "n_links": len(resp.links),
            "cached": resp.cached,
        })
