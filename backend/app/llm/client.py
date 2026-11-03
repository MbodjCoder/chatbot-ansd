"""Accès au modèle de langage, quel que soit le fournisseur.

Tout fournisseur compatible avec l'API OpenAI convient (Groq, Mistral,
DeepSeek, OpenAI, OpenRouter, Ollama en local) sans changer le reste du code.

- OpenAICompatClient : appels réseau, nouvelles tentatives, flux de texte.
- MockLLM : mode démonstration hors ligne, déterministe (tests).
- FallbackLLM : bascule sur MockLLM si l'API échoue ; jamais d'erreur à l'usager.
"""
from __future__ import annotations
import json
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

# Fournisseurs préconfigurés : (adresse de l'API, modèle par défaut)
PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "deepseek":   ("https://api.deepseek.com/v1",           "deepseek-chat"),
    "openai":     ("https://api.openai.com/v1",             "gpt-4o-mini"),
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
        """Par défaut, découpe la réponse complète en fragments."""
        text = self.complete(system, user, temperature, max_tokens).text
        for i in range(0, len(text), 24):
            yield text[i:i + 24]


class OpenAICompatClient(LLMClient):
    """Client pour toute API compatible OpenAI (chat/completions).

    Les erreurs passagères (429, 5xx, délai dépassé) sont retentées avec un
    délai croissant."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 20.0, max_retries: int = 1,
                 max_concurrency: int = 6):
        import httpx
        # client partagé entre threads (pool de connexions)
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout,
            limits=httpx.Limits(max_connections=max_concurrency * 4,
                                max_keepalive_connections=max_concurrency),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
        self.model = model
        self.max_retries = max_retries
        # nombre d'appels simultanés borné, pour ménager le quota du fournisseur
        self._sem = threading.BoundedSemaphore(max_concurrency)

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
        # saturation : échec rapide, FallbackLLM prend le relais
        if not self._sem.acquire(timeout=10):
            raise RuntimeError("LLM saturation (concurrence max atteinte)")

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
    """Modèle simulé, déterministe, pour le mode démonstration et les tests."""
    model = "mock-llm-demo"

    def complete(self, system, user, temperature=0.0, max_tokens=1024):
        # choix de la voie
        if "ROUTE_CLASSIFICATION" in system:
            label = self._route(user)
            return LLMResponse(json.dumps({"route": label, "confidence": 0.9}), self.model)
        # génération SQL
        if "SQL_GENERATION" in system:
            return LLMResponse(self._sql(user), self.model)
        # réponse documentaire
        if "GROUNDED_ANSWER" in system:
            return LLMResponse(self._grounded(user), self.model)
        # vérification de fidélité
        if "FAITHFULNESS_CHECK" in system:
            return LLMResponse(json.dumps({"faithful": True, "score": 0.95}), self.model)
        # consignes propres à la production : réponse vide, l'appelant se replie
        if "REWRITE_QUESTION" in system or "SYNTHESIS" in system:
            return LLMResponse("", self.model)
        return LLMResponse("Je ne peux repondre qu'aux questions portant sur les "
                           "statistiques officielles du Senegal (ANSD).", self.model)

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
        from app.sql.templates import template_sql
        return template_sql(user) or "SELECT 1;"

    def _grounded(self, user: str) -> str:
        """Réponse extractive : les phrases du contexte les plus proches de la
        question, la meilleure en premier."""
        ctx = re.search(r"<contexte>(.*?)</contexte>", user, re.S)
        qst = re.search(r"<question>(.*?)</question>", user, re.S)
        if not ctx:
            return "Information non disponible dans les sources ANSD."
        text = ctx.group(1)
        # marqueurs de source et titres retirés
        text = re.sub(r"\[Source:[^\]]*\]", " ", text)
        text = re.sub(r"#+", " ", text)
        # mentions « Source : ... » et adresses web retirées
        text = re.sub(r"Source\s*:.*", " ", text, flags=re.S)
        text = re.sub(r"(www\.|https?://)\S+", " ", text)
        # lignes coupées rejointes ; découpage sur la ponctuation de fin de phrase
        text = re.sub(r"\s+", " ", text)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        # phrases interrogatives écartées (titres de FAQ sans la réponse)
        sents = [s for s in sents if len(s.split()) >= 5
                 and not s.lower().startswith("source")
                 and not s.rstrip().endswith("?")
                 and "page officielle ansd" not in s.lower()]
        qnorm = (qst.group(1) if qst else "").lower()
        for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o"), ("î", "i"), ("ç", "c")]:
            qnorm = qnorm.replace(a, b)
        qwords = set(re.findall(r"\w{4,}", qnorm))
        definitional = bool(re.search(
            r"qu'est[- ]ce que|que signifie|definis|definition|c'est quoi", qnorm))
        # pondération IDF : un mot rare dans le contexte compte davantage
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
            # phrase quasi identique à la question : écartée
            if len(qwords & sw) >= max(1, int(0.9 * len(qwords))) \
                    and len(sw) <= len(qwords) + 2:
                return 0.0
            base = sum(idf.get(w, 0) for w in qwords & sw) / (len(sw) ** 0.5)
            if definitional and base > 0:
                sl = sents[i].lower()
                # bonus multiplicatif : n'amplifie que les phrases déjà pertinentes
                if re.search(r"\best (le|la|l'|un|une)\b|designe|correspond|mesure l", sl):
                    base *= 1.5
                if len(re.findall(r"\d", sents[i])) > 30:      # listes de chiffres
                    base *= 0.6
            return base
        ranked = sorted(range(len(sents)), key=lambda i: -score(i))
        if not ranked or score(ranked[0]) <= 0:
            return "Information non disponible dans les sources ANSD."
        # seuil relatif au meilleur score
        smax = score(ranked[0])
        # la meilleure phrase d'abord, puis les compléments
        keep = [i for i in ranked[:3] if score(i) >= 0.45 * smax]
        # doublons retirés (les passages se chevauchent)
        vus, uniques = set(), []
        for i in keep:
            cle = " ".join(sorted(sent_words[i]))[:120]
            if cle not in vus:
                vus.add(cle)
                uniques.append(i)
        return " ".join(sents[i] for i in uniques)


class FallbackLLM(LLMClient):
    """Appelle le vrai modèle ; en cas d'échec de l'API (quota, réseau, délai),
    répond avec le moteur local pour cette requête. L'incident est journalisé
    et visible dans /api/health."""

    def __init__(self, primary: LLMClient, backup: LLMClient | None = None):
        self.primary = primary
        self.backup = backup or MockLLM()
        self.model = primary.model
        self.last_error: str | None = None

    def _note(self, e: Exception) -> None:
        self.last_error = f"{type(e).__name__}: {e}"
        print(f"[chatbot] modèle indisponible ({self.last_error[:120]}) "
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
            if not yielded:      # rien émis : rejeu possible sur le repli
                yield from self.backup.complete_stream(system, user,
                                                       temperature, max_tokens)


def get_llm() -> LLMClient:
    """Production avec clé (ou Ollama) : client réseau protégé par FallbackLLM.
    Sinon : MockLLM."""
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
