"""Service principal du chatbot : traite une question de bout en bout.

question -> correction -> contexte de la conversation -> contrôle d'entrée
         -> cache -> voie (CATALOG, NAV, GEO, SQL, RAG, HYBRID)
         -> contrôle de fidélité des chiffres -> réponse, liens et suggestions
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

SESSION_TTL_S = 3600          # durée de vie d'une session inactive (s)
SESSION_MAX_TURNS = 8         # tours conservés par session
MAX_SESSIONS = 500            # plafond mémoire

# Indices d'une question de suivi (« Et en 2023 ? »). Règle volontairement
# stricte : un message autonome ne doit pas être rattaché au tour précédent.
_FOLLOWUP_PREFIXES = ("et ", "puis ", "ensuite", "quid")
_FOLLOWUP_PRONOUNS = re.compile(
    r"\b(cette?|ces|celui|celle|la[- ]bas|meme(s)?)\b|"
    r"\b(ce chiffre|cet indicateur|cette annee[- ]la|y en a)\b", re.I)

# Recherche dans le catalogue ANADS : « quelles enquêtes sur la santé ? »
_CATALOG_INTENT = re.compile(
    r"(quelle?s?|liste|existe|y a[- ]t[- ]il|cherche|avez[- ]vous|dispose)"
    r".{0,40}\b(enquete|etude|microdonnee|jeu de donnee|dataset|donnee)s?\b"
    r".{0,20}\b(sur|concernant|portant|relative|a propos|de la|du|d')"
    r"|dans le catalogue|catalogue anads|\banads\b.{0,30}\bsur\b",
    re.I)

# Demande d'accès à des données (« je veux les données sur la pêche ») :
# servie par les fiches ANADS et les portails officiels.
_DATA_ACCESS_INTENT = re.compile(
    r"\b(donnee|statistique|chiffre|data|microdonnee)s?\b"
    r"\s+(sur|de|du|de la|des|d|concernant|relati\w*|a propos|pour|portant)\b"
    r"|\b(je\s+(veux|voudrais|souhaite|cherche|aimerais|desire)|"
    r"donne(z|[- ]?moi)?|montre(z|[- ]?moi)?|"
    r"avoir|obtenir|acceder|trouver|telecharger|consulter)\b"
    r".{0,25}\b(donnee|statistique|chiffre|data|microdonnee|dataset)s?\b",
    re.I)

# Portails spécialisés ajoutés aux liens selon le thème détecté
_THEME_PORTAILS = [
    (re.compile(r"\b(agricol\w*|agriculture|elevage|betail|cultur\w*|horticol\w*|"
                r"recolte|semence|rural|dapsa|arachide|cereal\w*|vivrier\w*)\b", re.I),
     ["dapsa", "ipar"]),
]

# Mots courants : une question composée de mots connus n'a pas besoin de correction
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

# Demande explicite de lien ou de document (« où télécharger le RGPH-5 ? »)
_NAV_INTENT = re.compile(
    r"\b(ou|où)\s+(trouver|telecharger|t[ée]l[ée]charger|consulter|acc[ée]der|"
    r"voir|obtenir|lire)\b"
    r"|comment\s+(acc[ée]der|t[ée]l[ée]charger|obtenir|consulter)\b"
    r"|donne(z|[- ]moi)?\s+le\s+lien"
    r"|je\s+cherche\s+(le|la|les|un|une)\s+(rapport|document|publication|note|lien)",
    re.I)

REWRITE_SYSTEM = """REWRITE_QUESTION - Tu reformules une question de suivi en une
question autonome et complète, en français, à partir de l'historique fourni.
Réponds uniquement par la question reformulée. Conserve toutes les entités
(années, régions, indicateurs)."""

NORMALIZE_SYSTEM = """NORMALIZE_QUERY - Tu corriges une question posée à un assistant
statistique sur le Sénégal. Corrige uniquement les fautes de frappe,
d'orthographe et de grammaire, et la ponctuation. Règles :
- garde exactement le sens et la langue (français) ;
- n'ajoute aucune information, ne réponds pas, n'explique pas ;
- conserve les entités (années, régions, indicateurs, sigles comme RGPH, EHCVM) ;
- si la question est déjà correcte, renvoie-la telle quelle.
Réponds uniquement par la question corrigée, sans guillemets."""

SYNTHESIS_SYSTEM = """SYNTHESIS - Tu es l'assistant statistique du Chatbot ANSD.
On te fournit (1) un résultat chiffré issu de la base de données et (2) un
extrait documentaire. Rédige une réponse unique et fluide en français :
- commence par le chiffre demandé (en **gras**) avec sa période et sa source ;
- enchaîne avec l'explication utile ;
- n'utilise aucun chiffre absent des éléments fournis ;
- reste neutre et précis."""


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
    data: dict | None = None                          # résultat SQL (colonnes, lignes)
    links: list = field(default_factory=list)         # publications ANSD liées
    suggestions: list = field(default_factory=list)   # questions de suivi
    cached: bool = False


@dataclass
class _Session:
    history: list = field(default_factory=list)   # [(question, réponse, voie)]
    last_seen: float = field(default_factory=time.time)
    last_link_urls: frozenset = frozenset()
    shown_suggestions: set = field(default_factory=set)


class ANSDChatbot:
    def __init__(self):
        self.llm = get_llm()
        self.is_mock = isinstance(self.llm, MockLLM)
        # Modèle local lent (Ollama) : étapes déterministes. API rapide :
        # le modèle de langage corrige, reformule et rédige.
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
        self.sql = TextToSQLPipeline(gen_llm)
        self.router = Orchestrator(gen_llm)
        self.linker = ResourceLinker()
        self.catalogue = CatalogueANADS()
        self.docs_indexed = n
        self._lexique = self._construire_lexique()
        self._sessions: dict[str, _Session] = {}
        self._cache: dict[str, tuple[float, ChatResponse]] = {}
        # Sessions et cache sont partagés entre threads : seul leur accès est
        # verrouillé, jamais le calcul d'une réponse.
        self._lock = threading.RLock()

    # ------------------------------------------------------------ sessions
    def _session(self, session_id: str | None) -> tuple[str, _Session]:
        now = time.time()
        with self._lock:
            # purge des sessions expirées
            if len(self._sessions) > MAX_SESSIONS:
                self._sessions = {k: s for k, s in self._sessions.items()
                                  if now - s.last_seen < SESSION_TTL_S}
            # plafond strict : éviction des sessions les plus anciennes
            while len(self._sessions) >= MAX_SESSIONS:
                oldest = min(self._sessions, key=lambda k: self._sessions[k].last_seen)
                del self._sessions[oldest]
            # identifiant fourni par le client : format contrôlé
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
        """Ajoute un tour à l'historique (sous verrou)."""
        with self._lock:
            sess.history.append((question, answer, route))
            if len(sess.history) > SESSION_MAX_TURNS:
                sess.history = sess.history[-SESSION_MAX_TURNS:]

    @staticmethod
    def _is_followup(question: str) -> bool:
        q = question.lower().strip()
        # connecteur de suite, pronom de rappel, ou message court avec une année
        return (q.startswith(_FOLLOWUP_PREFIXES)
                or bool(_FOLLOWUP_PRONOUNS.search(q))
                or (len(q.split()) <= 4
                    and bool(re.search(r"\b(19|20)\d{2}\b|trimestre|t[1-4]\b", q))))

    def _history_text(self, sess: _Session, turns: int = 4) -> str:
        return "\n".join(f"Q: {q}\nR: {a[:300]}"
                         for q, a, _ in sess.history[-turns:])

    def _construire_lexique(self) -> set:
        """Vocabulaire du domaine (corpus, régions, mots courants)."""
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
        """Vrai si tous les mots de la question sont connus : rien à corriger."""
        toks = re.findall(r"[a-z]{4,}", _fold(question))
        for t in toks:
            if t in self._lexique:
                continue
            if any(t.startswith(s) or s.startswith(t) for s in _DOMAIN_STEMS):
                continue
            return False
        return True

    def _normalize_query(self, question: str) -> str:
        """Corrige les fautes (« kel é le to de chaumage a dakr ») par le modèle
        de langage. Ignorée si la question est déjà propre ; en cas de doute,
        la question d'origine est conservée."""
        if not self.use_llm_aux or len(question) > 300:
            return question
        if self._looks_clean(question):
            return question
        try:
            resp = self.llm.complete(NORMALIZE_SYSTEM, question,
                                     temperature=0.0, max_tokens=120)
            corrige = resp.text.strip().strip('"').strip()
            # rejet des sorties de longueur aberrante ou des commentaires
            if (corrige and 0.5 * len(question) <= len(corrige) <= 2.5 * len(question) + 20
                    and not re.match(r"(je |desole|il semble|voici|la question)", corrige.lower())):
                return corrige
        except Exception:
            pass
        return question

    def _followups(self, question: str, answer: str, sql: str | None,
                   docs: list[str], sess: _Session, k: int = 3) -> list[str]:
        """Questions de suivi : générées par le modèle de langage, complétées par
        des gabarits ; jamais deux fois la même dans une session."""
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
        if len(sess.shown_suggestions) > 60:
            sess.shown_suggestions = set(list(sess.shown_suggestions)[-40:])
        return out

    @staticmethod
    def _sujet_phrase(question: str) -> str:
        """Extrait « sur la pêche » d'une demande d'accès à des données."""
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
        """Portails spécialisés du thème (agriculture : DAPSA, IPAR)."""
        for rx, ids in _THEME_PORTAILS:
            if rx.search(question):
                return ids
        return []

    def _acces_donnees_links(self, question: str, etudes: list[dict]) -> list[dict]:
        """Liens : fiches ANADS, portails du thème, puis portails généraux."""
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
        """Réponse à une demande de données : fiches ANADS et portails officiels."""
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
        """Zone naturelle (Casamance…) ou lieu inconnu : jamais le chiffre d'une
        autre entité. Renvoie None pour une région ou le niveau national."""
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

        # lieu inconnu : réponse honnête, sans chiffre
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

        # zone naturelle : seules population et superficie s'additionnent
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

        # un taux ne s'additionne pas entre régions : on l'explique
        answer = (
            f"La **{zone_nom}** est une zone naturelle regroupant les régions de "
            f"{liste} ; ce n’est pas une région administrative, et cet indicateur "
            "(un taux) ne s’additionne pas entre régions. Je peux en revanche vous "
            f"le donner pour chacune de ces régions ({liste}).")
        links = [self.linker.fallback("ansd_indicateurs")]
        sugg = [f"Quel est le taux de pauvreté à {n} ?" for n in noms[:2]]
        return _fin(answer, links, sugg, "geo-zone-taux")

    def _contextualize(self, question: str, sess: _Session) -> str:
        """Rend une question de suivi autonome : substitution de l'année ou de la
        région dans la question précédente, sinon reformulation par le modèle."""
        if not sess.history:
            return question
        last_q = sess.history[-1][0]
        # « Et en 2023 ? »
        ny = re.search(r"\b(19|20)\d{2}\b", question)
        if ny and re.search(r"\b(19|20)\d{2}\b", last_q):
            return re.sub(r"\b(19|20)\d{2}\b", ny.group(0), last_q, count=1)
        # « Et à Thiès ? »
        from app.sql.templates import REGIONS
        def find_region(text: str) -> str | None:
            t = text.lower()
            for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")]:
                t = t.replace(a, b)
            t = t.replace("saint louis", "saint-louis")
            return next((r for r in REGIONS if r in t), None)
        nr, lr = find_region(question), find_region(last_q)
        if nr and lr and nr != lr:
            # motif tolérant aux accents et aux traits d'union
            pattern = re.sub(r"[eaio]", lambda m: {"e": "[eéèê]", "a": "[aà]",
                             "i": "[iî]", "o": "[oô]"}[m.group(0)],
                             lr.replace("-", "[- ]"))
            substituted = re.sub(pattern, nr, last_q, flags=re.I)
            if substituted != last_q:
                return substituted
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
                pass
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
        """Traite une question et renvoie la réponse complète.

        `on_delta` reçoit chaque fragment de texte au fil de la rédaction
        (voie documentaire uniquement)."""
        t0 = time.perf_counter()
        sid, sess = self._session(session_id)
        message_id = telemetry.new_id()

        # Échanges courants (« salut », « merci ») : réponse directe
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
        # salutation en tête d'une vraie question : retirée
        question = smalltalk.strip_greeting(question)

        # 1. Correction des fautes
        question = self._normalize_query(question)

        # 2. Question de suivi rendue autonome
        effective_q = question
        followup = self._is_followup(question) and bool(sess.history)
        if followup:
            effective_q = self._contextualize(question, sess)

        # 3. Contrôle d'entrée
        verdict = check_input(effective_q)
        if not verdict.allowed:
            resp = ChatResponse(answer=verdict.message, guardrail=verdict.reason,
                                latency_ms=int((time.perf_counter() - t0) * 1000),
                                session_id=sid, message_id=message_id)
            self._log(question, effective_q, resp)
            return resp

        # 4. Cache (questions autonomes uniquement)
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

        # intentions détectées sur le texte sans accents
        q_fold = _fold(effective_q)

        # 5. Demande de données : fiches ANADS et portails officiels
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

        # 6. Demande de lien ou de document : registre de liens vérifiés
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

        # 7. Zone naturelle ou lieu inconnu
        geo_resp = self._geo_intercept(effective_q, sid, sess, message_id, t0)
        if geo_resp is not None:
            if not followup:
                self._cache_put(cache_key, geo_resp)
            return geo_resp

        # 8. Choix de la voie : SQL, RAG ou HYBRID
        decision = self.router.route(effective_q)

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
            # flux de texte en direct sur la voie documentaire seule
            stream_cb = (on_delta if (on_delta and self.gen_abstractive
                                      and decision.route == "RAG") else None)
            r = self.rag.answer(effective_q, history=history, on_delta=stream_cb)
            parts.append(r.answer)
            # preuve du contrôle de fidélité : passages utilisés
            for c in r.chunks:
                evidence += " " + c.text
            sources += [{"type": "document", **s} for s in r.sources]

        # voie HYBRID : synthèse en un seul texte
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
                pass
        answer = "\n\n".join(p for p in parts if p)

        # 9. Contrôle de fidélité : chaque nombre doit figurer dans la preuve
        fv = check_output_faithfulness(answer, evidence)
        if not fv.allowed:
            answer, guard = fv.message, fv.reason
        else:
            guard = "ok"

        # 10. Liens sources (aucun lien tiré d'un document jugé non pertinent)
        echec_rag = answer.strip().startswith("Information non disponible")
        doc_sources = ([] if echec_rag else
                       [s["document"] for s in sources if s.get("type") == "document"])
        links = self.linker.links_for(effective_q, doc_sources, sql=sql_used)
        # toute réponse factuelle porte au moins un lien source
        if not links and decision.route in ("SQL", "RAG", "HYBRID"):
            links = [self.linker.fallback(
                "ansd_indicateurs" if data else "ansd_publications")]
        sess.last_link_urls = frozenset(l["url"] for l in links)

        # mentions de publications et d'études rendues cliquables
        if guard == "ok":
            answer = self.linker.autolink(answer)
            answer = self.catalogue.autolink_titles(answer)

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

        # 11. Historique (question complète, pour les suivis suivants), cache, journal
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
