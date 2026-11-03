"""
Couche d'abstraction LLM multi-fournisseurs.

Justification (memoire, sect. 4.1.2) : DeepSeek-V3 (DeepSeek-AI, 2024) est le
modele de reference retenu (MMLU 88,5 ~ GPT-4 ; MoE 671B/37B actives -> cout
d'inference modere ; 128K tokens ; francais documente ; poids ouverts).
Son API etant compatible OpenAI, l'abstraction `LLMClient` accepte N'IMPORTE
QUEL fournisseur expose au format OpenAI (principe d'inversion de dependance) :
DeepSeek, OpenAI, Groq, Mistral, OpenRouter, ou un modele local via Ollama.
La substitution ne change ni les prompts, ni le protocole d'evaluation.

Robustesse production :
  - nouvelles tentatives avec backoff exponentiel sur 429 / 5xx / timeout ;
  - streaming SSE (`complete_stream`) pour l'affichage progressif ;
  - degradation controlee vers MockLLM si aucune cle n'est configuree.

`MockLLM` fournit un mode demonstration hors-ligne, deterministe et
reproductible : indispensable pour les tests unitaires et la soutenance
(aucune dependance reseau le jour J).
"""
from __future__ import annotations
import json
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

# Presets des fournisseurs compatibles OpenAI (base_url, modele par defaut)
PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "deepseek":   ("https://api.deepseek.com/v1",           "deepseek-chat"),
    "openai":     ("https://api.openai.com/v1",             "gpt-4o-mini"),
    # llama-3.3-70b-versatile retiré par Groq (404 model_not_found, nov. 2026) -> #100
    "groq":       ("https://api.groq.com/openai/v1",        "openai/gpt-oss-120b"),
    "mistral":    ("https://api.mistral.ai/v1",             "mistral-large-latest"),
    "openrouter": ("https://openrouter.ai/api/v1",          "deepseek/deepseek-chat"),
    "ollama":     ("http://localhost:11434/v1",             "llama3.1"),
}


@dataclass
class LLMResponse:
    text: str
    model: str
    usage: dict | None = None


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 1024) -> LLMResponse: ...

    def complete_stream(self, system: str, user: str, temperature: float = 0.0,
                        max_tokens: int = 1024) -> Iterator[str]:
        """Par defaut : decoupe la reponse complete (les clients reseau
        surchargent avec un vrai flux de tokens)."""
        text = self.complete(system, user, temperature, max_tokens).text
        for i in range(0, len(text), 24):
            yield text[i:i + 24]


class OpenAICompatClient(LLMClient):
    """Client generique pour toute API compatible OpenAI (chat/completions).

    Gere les erreurs transitoires (429, 5xx, timeout) par nouvelles tentatives
    avec backoff exponentiel — comportement indispensable pour un service
    public expose (OWASP API Security ; bonnes pratiques d'integration LLM).
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 20.0, max_retries: int = 1,
                 max_concurrency: int = 6):
        import httpx
        # httpx.Client est thread-safe (pool de connexions) : partage entre
        # threads sans risque. Limites de pool explicites pour la charge.
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout,
            limits=httpx.Limits(max_connections=max_concurrency * 4,
                                max_keepalive_connections=max_concurrency),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
        self.model = model
        self.max_retries = max_retries
        # semaphore : borne le nb d'appels distants simultanes (protege le
        # quota du fournisseur, evite une tempete de 429 sous forte charge)
        self._sem = threading.BoundedSemaphore(max_concurrency)

    # ------------------------------------------------------------ interne
    def _post(self, payload: dict, stream: bool = False):
        import httpx
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                if stream:
                    req = self._http.build_request("POST", "/chat/completions",
                                                   json=payload)
                    resp = self._http.send(req, stream=True)
                else:
                    resp = self._http.post("/chat/completions", json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    resp.close() if stream else None
                    raise httpx.HTTPStatusError("retryable", request=resp.request,
                                                response=resp)
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                is_retryable = isinstance(e, httpx.TimeoutException) or (
                    getattr(e, "response", None) is not None
                    and e.response.status_code in (429, 500, 502, 503, 504))
                if attempt >= self.max_retries or not is_retryable:
                    raise
                time.sleep(delay)
                delay *= 2

    def _payload(self, system, user, temperature, max_tokens, stream=False):
        return {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

    def _acquire(self):
        # sous saturation, on n'attend pas indefiniment : echec -> FallbackLLM
        # bascule sur le moteur local (disponibilite preservee)
        if not self._sem.acquire(timeout=10):
            raise RuntimeError("LLM saturation (concurrence max atteinte)")

    # ------------------------------------------------------------ API
    def complete(self, system, user, temperature=0.0, max_tokens=1024):
        self._acquire()
        try:
            resp = self._post(self._payload(system, user, temperature, max_tokens))
            data = resp.json()
        finally:
            self._sem.release()
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )

    def complete_stream(self, system, user, temperature=0.0, max_tokens=1024):
        self._acquire()
        resp = self._post(self._payload(system, user, temperature, max_tokens,
                                        stream=True), stream=True)
        try:
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"]
                    if delta.get("content"):
                        yield delta["content"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        finally:
            resp.close()
            self._sem.release()


class MockLLM(LLMClient):
    """
    LLM simule pour le mode demonstration : genere des reponses par
    extraction/synthese deterministe a partir du contexte fourni.
    Il rend le pipeline complet executable et testable hors-ligne ;
    en production il est remplace par OpenAICompatClient (meme interface).
    """
    model = "mock-llm-demo"

    def complete(self, system, user, temperature=0.0, max_tokens=1024):
        # 1) Routage (fallback LLM de l'orchestrateur)
        if "ROUTE_CLASSIFICATION" in system:
            label = self._route(user)
            return LLMResponse(json.dumps({"route": label, "confidence": 0.9}), self.model)
        # 2) Generation SQL (module Text-to-SQL)
        if "SQL_GENERATION" in system:
            return LLMResponse(self._sql(user), self.model)
        # 3) Generation RAG ancree sur le contexte
        if "GROUNDED_ANSWER" in system:
            return LLMResponse(self._grounded(user), self.model)
        # 4) Verification de fidelite (Self-RAG simplifie)
        if "FAITHFULNESS_CHECK" in system:
            return LLMResponse(json.dumps({"faithful": True, "score": 0.95}), self.model)
        # 5) Prompts propres au mode production (reecriture, synthese) :
        # reponse vide -> l'appelant applique son repli deterministe
        if "REWRITE_QUESTION" in system or "SYNTHESIS" in system:
            return LLMResponse("", self.model)
        return LLMResponse("Je ne peux repondre qu'aux questions portant sur les "
                           "statistiques officielles du Senegal (ANSD).", self.model)

    # --- heuristiques deterministes du mode demo ---
    def _route(self, user: str) -> str:
        q = user.lower()
        sql_cues = ["combien", "taux", "population de", "evolution", "moyenne",
                    "quel est le", "quelle est la", "chiffre", "compare"]
        rag_cues = ["methodologie", "definition", "qu'est-ce", "comment est",
                    "rapport", "enquete", "explique", "pourquoi", "moteur",
                    "facteur", "cause", "signifie", "comment l'", "ou trouver"]
        s = sum(c in q for c in sql_cues)
        r = sum(c in q for c in rag_cues)
        if s > 0 and r > 0:
            return "HYBRID"
        return "SQL" if s >= r else "RAG"

    def _sql(self, user: str) -> str:
        # delegation au generateur par gabarits (module partage avec le
        # pipeline SQL de production)
        from app.sql.templates import template_sql
        return template_sql(user) or "SELECT 1;"

    def _grounded(self, user: str) -> str:
        """Synthese extractive deterministe : selection des phrases du contexte
        les plus proches de la question (recouvrement lexical normalise),
        restituees dans leur ordre d'origine. Les lignes de structure
        (titres markdown, mentions de source) sont ecartees du candidat."""
        ctx = re.search(r"<contexte>(.*?)</contexte>", user, re.S)
        qst = re.search(r"<question>(.*?)</question>", user, re.S)
        if not ctx:
            return "Information non disponible dans les sources ANSD."
        text = ctx.group(1)
        # retirer marqueurs de source et symboles de titre
        text = re.sub(r"\[Source:[^\]]*\]", " ", text)
        text = re.sub(r"#+", " ", text)
        # supprimer le pied de page "Source : ..." jusqu'a la fin (metadonnee,
        # jamais une reponse) et les URLs residuelles
        text = re.sub(r"Source\s*:.*", " ", text, flags=re.S)
        text = re.sub(r"(www\.|https?://)\S+", " ", text)   # URLs
        # rejoindre les lignes coupees par la mise en forme (markdown wrap) :
        # sans cela "se trouve a\nDakar" est scinde et la reponse est tronquee.
        # On ne segmente ensuite QUE sur la ponctuation de fin de phrase.
        text = re.sub(r"\s+", " ", text)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        # ecarter les phrases INTERROGATIVES : dans une FAQ, les titres sont des
        # questions ("Ou se trouve l'ANSD ?") qui matchent fortement la requete
        # mais ne contiennent PAS la reponse. On ne garde que les phrases
        # declaratives (l'information reelle).
        sents = [s for s in sents if len(s.split()) >= 5
                 and not s.lower().startswith("source")
                 and not s.rstrip().endswith("?")
                 and "page officielle ansd" not in s.lower()]  # titres de docs web
        qnorm = (qst.group(1) if qst else "").lower()
        for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o"), ("î", "i"), ("ç", "c")]:
            qnorm = qnorm.replace(a, b)
        qwords = set(re.findall(r"\w{4,}", qnorm))
        definitional = bool(re.search(
            r"qu'est[- ]ce que|que signifie|definis|definition|c'est quoi", qnorm))
        # ponderation IDF locale : un mot present dans peu de phrases du
        # contexte (ex. "gini") discrimine bien mieux qu'un mot frequent
        # (ex. "indice") — principe TF-IDF applique a l'echelle des phrases
        import math
        def fold_words(s: str) -> set:
            sl = s.lower()
            for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"),
                         ("ô", "o"), ("î", "i"), ("ç", "c")]:
                sl = sl.replace(a, b)
            return set(re.findall(r"\w{4,}", sl))
        sent_words = [fold_words(s) for s in sents]
        n = len(sents) or 1
        idf = {w: math.log(1 + n / (1 + sum(1 for sw in sent_words if w in sw)))
               for w in qwords}
        def score(i: int) -> float:
            sw = sent_words[i]
            if not sw:
                return 0.0
            # une phrase quasi identique a la question (titre repris tel
            # quel) n'apporte aucune information : ecartee
            if len(qwords & sw) >= max(1, int(0.9 * len(qwords))) \
                    and len(sw) <= len(qwords) + 2:
                return 0.0
            base = sum(idf.get(w, 0) for w in qwords & sw) / (len(sw) ** 0.5)
            if definitional and base > 0:
                sl = sents[i].lower()
                # bonus MULTIPLICATIF : n'amplifie que les phrases deja
                # pertinentes (un bonus additif promouvait des copules
                # hors sujet)
                if re.search(r"\best (le|la|l'|un|une)\b|designe|correspond|mesure l", sl):
                    base *= 1.5
                if len(re.findall(r"\d", sents[i])) > 30:  # listes de chiffres
                    base *= 0.6
            return base
        ranked = sorted(range(len(sents)), key=lambda i: -score(i))
        if not ranked or score(ranked[0]) <= 0:
            return "Information non disponible dans les sources ANSD."
        # seuil RELATIF au meilleur score : n'accompagner la meilleure phrase
        # que de phrases presque aussi pertinentes (une phrase faiblement
        # liee degrade la reponse plus qu'elle ne l'enrichit)
        smax = score(ranked[0])
        # la phrase la MIEUX notee ouvre la reponse (reponse directe
        # d'abord) ; les complements suivent par pertinence decroissante
        keep = [i for i in ranked[:3] if score(i) >= 0.45 * smax]
        # deduplication : le chevauchement des chunks (512/128) fait
        # apparaitre la meme phrase dans deux chunks voisins — ne jamais
        # restituer deux fois un contenu identique
        vus, uniques = set(), []
        for i in keep:
            cle = " ".join(sorted(sent_words[i]))[:120]
            if cle not in vus:
                vus.add(cle)
                uniques.append(i)
        return " ".join(sents[i] for i in uniques)


class FallbackLLM(LLMClient):
    """Enrobage de resilience : tente le LLM reel, et en cas d'echec de
    l'API (solde epuise 402, quota 429 persistant, reseau coupe, timeout)
    bascule silencieusement sur le moteur deterministe local pour CETTE
    requete — le service ne renvoie JAMAIS une erreur 500 a l'usager.

    Justification : un service public doit degrader sa qualite, pas sa
    disponibilite (fault tolerance by graceful degradation, Avizienis et
    al. 2004). L'incident est journalise et expose dans /api/health.
    """

    def __init__(self, primary: LLMClient, backup: LLMClient | None = None):
        self.primary = primary
        self.backup = backup or MockLLM()
        self.model = primary.model
        self.last_error: str | None = None

    def _note(self, e: Exception) -> None:
        self.last_error = f"{type(e).__name__}: {e}"
        print(f"[RAMA] LLM reel indisponible ({self.last_error[:120]}) "
              "-> repli local pour cette requete.")

    def complete(self, system, user, temperature=0.0, max_tokens=1024):
        try:
            resp = self.primary.complete(system, user, temperature, max_tokens)
            self.last_error = None
            return resp
        except Exception as e:
            self._note(e)
            return self.backup.complete(system, user, temperature, max_tokens)

    def complete_stream(self, system, user, temperature=0.0, max_tokens=1024):
        try:
            yielded = False
            for chunk in self.primary.complete_stream(system, user,
                                                      temperature, max_tokens):
                yielded = True
                yield chunk
            self.last_error = None
        except Exception as e:
            self._note(e)
            if not yielded:   # rien emis : on peut rejouer sur le repli
                yield from self.backup.complete_stream(system, user,
                                                       temperature, max_tokens)


def get_llm() -> LLMClient:
    """Fabrique du client LLM.

    production + cle configuree -> client reseau du fournisseur choisi,
    protege par FallbackLLM (repli local par requete en cas d'echec API) ;
    sinon -> MockLLM (degradation controlee, memes interfaces).
    Ollama (modele local) n'exige pas de cle.
    """
    from app.core.config import settings
    provider = settings.llm_provider.lower().strip()
    api_key = settings.llm_api_key or settings.deepseek_api_key
    if settings.mode == "production" and provider in PROVIDER_PRESETS:
        preset_url, preset_model = PROVIDER_PRESETS[provider]
        base_url = settings.llm_base_url or preset_url
        model = settings.llm_model or preset_model
        if api_key or provider == "ollama":
            return FallbackLLM(OpenAICompatClient(
                base_url, api_key, model,
                timeout=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
                max_concurrency=settings.llm_max_concurrency))
    return MockLLM()
