"""API du Chatbot ANSD (documentation interactive : /docs).

  POST /api/chat         question -> réponse complète et tracée
  POST /api/chat/stream  même réponse, envoyée au fil de l'eau (SSE)
  POST /api/transcribe   dictée vocale -> texte (navigateurs sans reconnaissance)
  POST /api/feedback     avis de l'usager sur une réponse
  GET  /api/health       état du service
  GET  /api/metrics      indicateurs d'usage

Débit limité par adresse IP (en mémoire, une seule instance).
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
    title="Chatbot ANSD",
    description="Assistant d'accès aux statistiques du Sénégal : "
                "recherche documentaire et requêtes sur une base de données.",
    version="2.0.0",
)
# Origines autorisées : ANSD_CORS_ORIGINS="https://www.ansd.sn,https://ansd.sn"
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins or ["*"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# Dernier filet : l'usager reçoit un message neutre, le détail reste au serveur
@app.exception_handler(Exception)
async def _on_error(request: Request, exc: Exception):
    print(f"[chatbot] erreur non gérée sur {request.url.path} : "
          f"{type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"answer": "Le service a rencontré une difficulté temporaire. "
                 "Veuillez réessayer dans un instant.",
                 "route": "-", "guardrail": "error"})


_PAGE_404 = (
    "<!doctype html><html lang=fr><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<link rel=icon type=image/svg+xml href=/logo.svg>"
    "<title>Page introuvable — Chatbot ANSD</title>"
    "<style>body{font-family:system-ui,Segoe UI,sans-serif;background:#fff;"
    "color:#0a2440;display:flex;min-height:100vh;align-items:center;"
    "justify-content:center;text-align:center;margin:0}"
    "@media(prefers-color-scheme:dark){body{background:#08121f;color:#e6f0fb}}"
    ".b{max-width:420px;padding:24px}h1{font-size:3rem;color:#0e79c4;margin:0}"
    "p{color:#3f5972}a{display:inline-block;margin-top:18px;background:#0e79c4;"
    "color:#fff;padding:10px 18px;border-radius:11px;text-decoration:none;"
    "font-weight:600}</style></head><body><div class=b><h1>404</h1>"
    "<p>Cette page n'existe pas.</p>"
    "<a href=/>← Retour au chatbot</a></div></body></html>"
)


@app.exception_handler(StarletteHTTPException)
async def _on_http(request: Request, exc: StarletteHTTPException):
    # page inconnue : page HTML ; API : réponse JSON
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return HTMLResponse(_PAGE_404, status_code=404)
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail})

bot = ANSDChatbot()

# état du modèle de langage affiché au démarrage
if bot.is_mock:
    if settings.mode == "production":
        print("[chatbot] Mode production sans clé API : repli sur le mode démonstration. "
              "Renseignez ANSD_LLM_API_KEY dans backend/.env puis redémarrez.")
    else:
        print("[chatbot] Mode démonstration hors ligne (déterministe).")
else:
    print(f"[chatbot] Modèle actif : {settings.llm_provider} / {bot.llm.model}")

# ------------------------------------------------------------ limitation de débit
# Fenêtre glissante par IP ; compteur partagé entre threads, donc verrouillé.
RATE_WINDOW_S = 60
RATE_MAX_REQ = 30
RATE_MAX_IPS = 10_000            # plafond mémoire
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # X-Forwarded-For n'est lu que derrière un proxy de confiance
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
        # purge des IP inactives
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
    try:
        return bot.ask(q.question, q.session_id).__dict__
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[chatbot] erreur /api/chat : {type(e).__name__}: {e}")
        return {"answer": "Le service a rencontré une difficulté temporaire. "
                "Veuillez réessayer.", "route": "-", "guardrail": "error"}


@app.post("/api/chat/stream", summary="Poser une question (réponse en flux)")
async def chat_stream(q: Question, request: Request):
    """Réponse en flux SSE.

      event delta : fragment de texte, au fil de la rédaction (voie documentaire)
      event done  : réponse complète et validée, qui fait foi
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
        except Exception as e:  # noqa: BLE001
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
                       + json.dumps({"answer": "Le service a rencontré une "
                                     "erreur. Veuillez réessayer.", "route": "-",
                                     "guardrail": "error"}, ensure_ascii=False)
                       + "\n\n")
                break
            else:
                yield f"event: done\ndata: {json.dumps(val, ensure_ascii=False)}\n\n"
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/feedback", summary="Évaluer une réponse")
def feedback(f: Feedback, request: Request):
    _rate_limit(request)
    telemetry.log_feedback(f.model_dump())
    return {"status": "merci"}


RATE_MAX_VOIX = 40   # transcriptions par minute et par IP (partielles comprises)


@app.post("/api/transcribe", summary="Transcrire une dictée vocale (repli serveur)")
async def transcribe(request: Request):
    """Corps : audio brut (webm/opus, mp4…), Content-Type : son type MIME.
    Réponse : {"texte": "..."}."""
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


@app.get("/api/metrics", summary="Indicateurs d'usage")
def metrics():
    """Volume, répartition des voies, latence, taux de refus, satisfaction."""
    return telemetry.metrics()


@app.get("/api/popular", summary="Questions les plus recherchees, par categorie")
def popular():
    """Questions les plus posées, par thème (journal d'usage)."""
    from app.core import popular as _popular
    return _popular.compute()


@app.get("/api/health", summary="État du service")
def health():
    # état du modèle exposé en booléen : aucun détail interne
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


# Chargement rapide : HTML revalidé à chaque visite, images gardées 7 jours,
# compression gzip (sauf le flux SSE, envoyé fragment par fragment).
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
    """GZip sauf pour le flux SSE et les images (déjà compressées)."""

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
