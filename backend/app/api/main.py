"""API REST FastAPI (documentee OpenAPI /docs) - exigence methodologique
de contrats d'interface explicites entre modules.

Endpoints :
  POST /api/chat        : question -> reponse + tracabilite complete
  POST /api/chat/stream : meme contrat, reponse en flux SSE (affichage
                          progressif : evenements meta / delta / done)
  POST /api/transcribe  : dictée vocale -> texte (repli serveur Whisper, #98)
  POST /api/feedback    : retour utilisateur (pouce haut/bas) -> journal JSONL
                          (necessaire au protocole d'evaluation SUS du memoire)
  GET  /api/health      : etat du systeme
Protection : limitation de debit en memoire (fenetre glissante par IP),
suffisante pour un deploiement mono-instance ; en production multi-instances,
la substituer par une passerelle (nginx / API gateway).
"""
import asyncio
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field

from app.core import telemetry
from app.core.chatbot import ANSDChatbot
from app.core.config import settings
from app.llm import transcription

app = FastAPI(
    title="RAMA-ANSD",
    description="Systeme d'Acces Guide aux Statistiques - chatbot hybride "
                "RAG + Text-to-SQL pour l'ANSD (memoire de master).",
    version="2.0.0",
)
# CORS configurable (S6) : "*" en dev ; en production, lister le domaine ANSD
# via ANSD_CORS_ORIGINS="https://www.ansd.sn,https://ansd.sn".
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins or ["*"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# Gestionnaire d'exception global (S4) : aucune requete ne renvoie de trace
# interne ni de 500 brut. L'usager recoit un message neutre, l'incident est
# journalise cote serveur. Defense en profondeur (les voies ont deja leurs
# replis, ceci est le dernier filet).
@app.exception_handler(Exception)
async def _on_error(request: Request, exc: Exception):
    print(f"[RAMA] erreur non geree sur {request.url.path} : "
          f"{type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"answer": "Le service a rencontré une difficulté temporaire. "
                 "Veuillez réessayer dans un instant.",
                 "route": "-", "guardrail": "error"})


_PAGE_404 = (
    "<!doctype html><html lang=fr><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<link rel=icon type=image/svg+xml href=/rama.svg>"
    "<title>Page introuvable — RAMA</title>"
    "<style>body{font-family:'Inter',Segoe UI,sans-serif;background:#f4f8fc;"
    "color:#0a2440;display:flex;min-height:100vh;align-items:center;"
    "justify-content:center;text-align:center;margin:0}"
    "@media(prefers-color-scheme:dark){body{background:#08121f;color:#e6f0fb}}"
    ".b{max-width:420px;padding:24px}h1{font-size:3rem;color:#0e79c4;margin:0}"
    "p{color:#3f5972}a{display:inline-block;margin-top:18px;background:#0e79c4;"
    "color:#fff;padding:10px 18px;border-radius:11px;text-decoration:none;"
    "font-weight:600}</style></head><body><div class=b><h1>404</h1>"
    "<p>Cette page n'existe pas. Revenez poser votre question à RAMA.</p>"
    "<a href=/>← Retour à RAMA</a></div></body></html>"
)


@app.exception_handler(StarletteHTTPException)
async def _on_http(request: Request, exc: StarletteHTTPException):
    # 404 sur une page -> page HTML soignée ; sur l'API -> JSON neutre.
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return HTMLResponse(_PAGE_404, status_code=404)
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail})

bot = ANSDChatbot()

# Etat du LLM affiche au demarrage : l'operateur sait immediatement si le
# modele reel est actif ou si le systeme est en repli demonstration.
if bot.is_mock:
    if settings.mode == "production":
        print("[RAMA] ATTENTION : mode production demande mais aucune cle API "
              "trouvee -> repli demonstration hors-ligne.\n"
              "[RAMA] Collez votre cle DeepSeek dans backend/.env "
              "(ANSD_LLM_API_KEY=sk-...) puis redemarrez.")
    else:
        print("[RAMA] Mode demonstration hors-ligne (deterministe).")
else:
    print(f"[RAMA] LLM reel actif : {settings.llm_provider} / {bot.llm.model}")

# ------------------------------------------------------------ rate limiting
# Fenetre glissante par IP. Protege chat ET feedback (P2-8). Le compteur est
# un etat partage entre threads -> verrou (P0-1). OWASP API Security.
RATE_WINDOW_S = 60
RATE_MAX_REQ = 30
RATE_MAX_IPS = 10_000            # borne DoS memoire du dictionnaire (S2)
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # Derriere un proxy de confiance (nginx), l'IP reelle est dans
    # X-Forwarded-For ; sinon on ne s'y fie PAS (usurpation possible). S6.
    if settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_limit(request: Request, max_req: int = RATE_MAX_REQ,
                canal: str = "chat") -> None:
    # Un compteur par canal : la dictée vocale (plusieurs transcriptions
    # partielles par question) ne consomme pas le quota des questions.
    ip = _client_ip(request)
    now = time.time()
    with _hits_lock:
        dq = _hits[ip if canal == "chat" else f"{canal}|{ip}"]
        while dq and now - dq[0] > RATE_WINDOW_S:
            dq.popleft()
        if len(dq) >= max_req:
            raise HTTPException(status_code=429,
                                detail="Trop de requetes : reessayez dans une minute.")
        dq.append(now)
        # purge des IP inactives : empeche la croissance non bornee du
        # dictionnaire (fuite memoire / DoS) sous un grand nombre d'IP
        if len(_hits) > RATE_MAX_IPS:
            for k in [k for k, d in _hits.items()
                      if not d or now - d[-1] > RATE_WINDOW_S]:
                del _hits[k]


# ------------------------------------------------------------ modeles
class Question(BaseModel):
    question: str = Field(..., min_length=1, max_length=settings.max_query_length,
                          examples=["Quelle est la population de Dakar en 2023 ?"])
    session_id: str | None = Field(None, description="Identifiant de session "
                                   "pour les conversations multi-tours")


class Feedback(BaseModel):
    message_id: str = Field(..., max_length=32)
    session_id: str | None = Field(None, max_length=32)
    rating: str = Field(..., pattern="^(up|down)$")
    comment: str | None = Field(None, max_length=500)


# ------------------------------------------------------------ endpoints
@app.post("/api/chat", summary="Poser une question au chatbot")
def chat(q: Question, request: Request):
    _rate_limit(request)
    # bot.ask est robuste (FallbackLLM) ; ce filet garantit qu'aucune erreur
    # inattendue ne renvoie de 500/trace a l'usager (S4).
    try:
        return bot.ask(q.question, q.session_id).__dict__
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[RAMA] erreur /api/chat : {type(e).__name__}: {e}")
        return {"answer": "Le service a rencontré une difficulté temporaire. "
                "Veuillez réessayer.", "route": "-", "guardrail": "error"}


@app.post("/api/chat/stream", summary="Poser une question (reponse en flux SSE)")
async def chat_stream(q: Question, request: Request):
    """Reponse en flux SSE avec VRAI streaming des tokens (P0-2).

    Le calcul tourne dans un thread ; un pont thread->async (asyncio.Queue)
    transmet chaque fragment du LLM des qu'il est produit, sur la voie
    documentaire abstractive (fournisseur rapide). Les voies deterministes
    (SQL, NAV, CATALOG, cache) n'emettent pas de fragment : seul l'evenement
    final `done` porte la reponse, deja validee.
      event delta -> fragment de texte en temps reel (streaming optimiste)
      event done  -> charge utile complete et validee (source de verite)
    Le rail de fidelite s'applique au texte assemble ; si le `done.answer`
    differe des fragments streames, le client remplace le texte (repli).
    """
    _rate_limit(request)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_delta(frag: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("delta", frag))

    def work() -> None:
        try:
            r = bot.ask(q.question, q.session_id, on_delta=on_delta)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", r.__dict__))
        except Exception as e:  # noqa: BLE001 -> jamais de 500 silencieux
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

    async def gen():
        loop.run_in_executor(None, work)
        while True:
            kind, val = await queue.get()
            if kind == "delta":
                yield ("event: delta\ndata: "
                       + json.dumps(val, ensure_ascii=False) + "\n\n")
            elif kind == "error":
                yield ("event: done\ndata: "
                       + json.dumps({"answer": "Le service a rencontre une "
                                     "erreur. Veuillez reessayer.", "route": "-",
                                     "guardrail": "error"}, ensure_ascii=False)
                       + "\n\n")
                break
            else:  # done
                yield f"event: done\ndata: {json.dumps(val, ensure_ascii=False)}\n\n"
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/feedback", summary="Evaluer une reponse (pouce haut/bas)")
def feedback(f: Feedback, request: Request):
    _rate_limit(request)   # P2-8 : meme protection anti-spam que /api/chat
    telemetry.log_feedback(f.model_dump())
    return {"status": "merci"}


RATE_MAX_VOIX = 40   # transcriptions/min/IP (partielles comprises, ~3 s d'écart)


@app.post("/api/transcribe", summary="Transcrire une dictée vocale (repli serveur)")
async def transcribe(request: Request):
    """Corps = audio brut (webm/opus, mp4…), Content-Type = son type MIME.
    Utilisé seulement quand le navigateur n'a pas de reconnaissance vocale
    intégrée (#98). Réponse : {"texte": "..."}."""
    _rate_limit(request, max_req=RATE_MAX_VOIX, canal="voix")
    if not transcription.disponible():
        raise HTTPException(status_code=503, detail="Saisie vocale indisponible.")
    taille = int(request.headers.get("content-length") or 0)
    if taille > transcription.TAILLE_MAX_OCTETS:
        raise HTTPException(status_code=413, detail="Enregistrement trop long.")
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio vide.")
    if len(audio) > transcription.TAILLE_MAX_OCTETS:
        raise HTTPException(status_code=413, detail="Enregistrement trop long.")
    try:
        texte = await transcription.transcrire(
            audio, request.headers.get("content-type", "audio/webm"))
    except httpx.HTTPStatusError as e:
        code = 429 if e.response.status_code == 429 else 502
        raise HTTPException(status_code=code, detail="Transcription indisponible.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Transcription indisponible.")
    return {"texte": texte}


@app.get("/api/metrics", summary="Metriques d'usage agregees (observabilite)")
def metrics():
    """Indicateurs de pilotage (P2-7) : volume, repartition des voies,
    latence (mediane/p90/p99), taux de refus des guardrails, satisfaction.
    Alimente l'evaluation quantitative du memoire."""
    return telemetry.metrics()


@app.get("/api/popular", summary="Questions les plus recherchees, par categorie")
def popular():
    """Initiative mixte (Horvitz 1999) : par categorie thematique, les questions
    reellement les plus posees, classees sur la telemetrie du service (hors
    salutations et refus). Alimente les categories cliquables de l'accueil."""
    from app.core import popular as _popular
    return _popular.compute()


@app.get("/api/health", summary="Etat du systeme")
def health():
    # S7 : on expose un BOOLEEN de sante du LLM, pas le detail de l'erreur
    # interne (pas de fuite d'information : URL, pile, etc. restent au serveur).
    return {"status": "ok", "mode": settings.mode,
            "llm": bot.llm.__class__.__name__,
            "llm_actif": not bot.is_mock,
            "modele": getattr(bot.llm, "model", "?"),
            "llm_ok": getattr(bot.llm, "last_error", None) is None,
            "documents_indexes": bot.docs_indexed,
            "voix_serveur": transcription.disponible()}


frontend = Path(__file__).resolve().parents[3] / "frontend"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")


# Performance de chargement (#96) : l'interface doit s'ouvrir vite sur tout
# appareil, y compris en 3G. Deux leviers sans dépendance :
#  - cache navigateur : HTML revalidé à chaque visite (ETag -> 304, jamais de
#    version périmée), ressources statiques (images, icônes) gardées 7 jours ;
#  - compression gzip (~4x sur le HTML), sauf le flux SSE qui doit partir
#    fragment par fragment (une compression tamponnerait l'affichage progressif).
_CACHE_LONG = (".jpg", ".png", ".svg", ".webp", ".ico", ".webmanifest")


@app.middleware("http")
async def _cache_statique(request: Request, call_next):
    reponse = await call_next(request)
    chemin = request.url.path
    if not chemin.startswith("/api/"):
        if chemin.endswith(_CACHE_LONG):
            reponse.headers["Cache-Control"] = "public, max-age=604800"
        else:
            reponse.headers["Cache-Control"] = "no-cache"
    return reponse


class _GzipSaufFlux:
    """GZip pour les réponses textuelles, sauf le flux SSE et les images
    (formats déjà compressés : les recompresser coûte du CPU pour rien)."""

    def __init__(self, application):
        self.brut = application
        self.compresse = GZipMiddleware(application, minimum_size=800)

    async def __call__(self, scope, receive, send):
        chemin = scope.get("path", "")
        if scope["type"] == "http" and (chemin == "/api/chat/stream"
                                        or chemin.endswith((".jpg", ".png", ".webp"))):
            await self.brut(scope, receive, send)
        else:
            await self.compresse(scope, receive, send)


app.add_middleware(_GzipSaufFlux)
