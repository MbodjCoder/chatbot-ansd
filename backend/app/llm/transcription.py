"""Transcription vocale côté serveur (#98) : repli de la saisie vocale.

La dictée passe d'abord par la reconnaissance vocale du navigateur (Web Speech
API : texte affiché en direct, aucun coût serveur). Certains navigateurs ne
l'offrent pas (Firefox) ou la bloquent (Brave, WebView d'applications) : le
frontend enregistre alors l'audio et l'envoie ici, puis on le transcrit par
Whisper via le fournisseur LLM déjà configuré (point d'accès
/audio/transcriptions compatible OpenAI).

Confidentialité : l'audio n'est ni stocké ni journalisé ; il ne fait que
transiter vers le fournisseur de transcription.
"""
import re

import httpx

from app.core.config import settings
from app.llm.client import PROVIDER_PRESETS

# Fournisseurs offrant Whisper derrière un point d'accès compatible OpenAI.
MODELES_WHISPER = {"groq": "whisper-large-v3-turbo", "openai": "whisper-1"}

# Indice de vocabulaire : Whisper s'en sert pour orthographier correctement
# les sigles et toponymes du domaine (sinon « RGPH 5 » -> « R.G.P.H. cinq »).
VOCABULAIRE = ("Question sur les statistiques du Sénégal : ANSD, RGPH-5, EHCVM, "
               "ENES, IHPC, PIB, ANADS, chômage, pauvreté, inflation, Dakar, "
               "Thiès, Diourbel, Fatick, Kaolack, Kaffrine, Kolda, Kédougou, "
               "Louga, Matam, Saint-Louis, Sédhiou, Tambacounda, Ziguinchor.")

TAILLE_MAX_OCTETS = 4 * 1024 * 1024   # ~60 s d'Opus : borne anti-abus

_EXTENSIONS = {"webm": "webm", "mp4": "m4a", "mpeg": "mp3", "ogg": "ogg",
               "wav": "wav", "x-wav": "wav"}

# Whisper « hallucine » des génériques de sous-titres sur un audio sans
# parole (biais de ses données d'entraînement) : ces phrases ne sont jamais
# une question d'usager, on les écarte.
_HALLUCINATIONS = re.compile(
    r"sous-titr|amara\.org|merci d'avoir regard|abonnez-vous|"
    r"merci de votre attention|^\W*merci\W*$", re.IGNORECASE)


def _fournisseur() -> str:
    return settings.llm_provider.lower().strip()


def _cle() -> str:
    return settings.llm_api_key or settings.deepseek_api_key


def disponible() -> bool:
    """Vrai si la transcription serveur peut répondre (fournisseur + clé)."""
    return (settings.mode == "production"
            and _fournisseur() in MODELES_WHISPER and bool(_cle()))


def nom_fichier(type_mime: str) -> str:
    sous_type = type_mime.split(";")[0].split("/")[-1].strip().lower()
    return "dictee." + _EXTENSIONS.get(sous_type, "webm")


async def transcrire(audio: bytes, type_mime: str) -> str:
    """Audio -> texte français. Lève httpx.HTTPStatusError si le fournisseur
    refuse (429 quota, 5xx) : l'appelant traduit en réponse neutre."""
    fournisseur = _fournisseur()
    base = (settings.llm_base_url or PROVIDER_PRESETS[fournisseur][0]).rstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {_cle()}"},
            files={"file": (nom_fichier(type_mime), audio,
                            type_mime.split(";")[0] or "audio/webm")},
            data={"model": MODELES_WHISPER[fournisseur], "language": "fr",
                  "temperature": "0", "response_format": "json",
                  "prompt": VOCABULAIRE})
        r.raise_for_status()
    texte = (r.json().get("text") or "").strip()
    return "" if _HALLUCINATIONS.search(texte) or _echo_indice(texte) else texte


def _echo_indice(texte: str) -> bool:
    """Sur un silence, Whisper peut recracher l'indice de vocabulaire : son
    début, ou une énumération de ses termes. Un mot isolé (« Dakar ») reste une
    vraie dictée."""
    t = texte.lower().strip(" .")
    indice = VOCABULAIRE.lower()
    return bool(t) and t in indice and (indice.startswith(t[:25]) or t.count(",") >= 2)
