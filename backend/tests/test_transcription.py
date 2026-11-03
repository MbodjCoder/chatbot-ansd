"""Saisie vocale, repli serveur (#98) : contrat du point d'accès /api/transcribe
et filtres de la transcription. Aucun appel réseau : le fournisseur est simulé."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.llm import transcription


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def test_indisponible_sans_fournisseur(client, monkeypatch):
    monkeypatch.setattr(transcription, "disponible", lambda: False)
    r = client.post("/api/transcribe", content=b"\x00" * 100,
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503
    assert client.get("/api/health").json()["voix_serveur"] is False


def test_audio_vide_et_trop_long_refuses(client, monkeypatch):
    monkeypatch.setattr(transcription, "disponible", lambda: True)
    r = client.post("/api/transcribe", content=b"", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 400
    trop = b"\x00" * (transcription.TAILLE_MAX_OCTETS + 1)
    r = client.post("/api/transcribe", content=trop, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 413


def test_quota_fournisseur_traduit_en_429(client, monkeypatch):
    monkeypatch.setattr(transcription, "disponible", lambda: True)

    async def refuse(audio, type_mime):
        req = httpx.Request("POST", "https://exemple/audio/transcriptions")
        raise httpx.HTTPStatusError("quota", request=req,
                                    response=httpx.Response(429, request=req))
    monkeypatch.setattr(transcription, "transcrire", refuse)
    r = client.post("/api/transcribe", content=b"\x01" * 100,
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 429


def test_texte_transcrit_renvoye(client, monkeypatch):
    monkeypatch.setattr(transcription, "disponible", lambda: True)

    async def transcrit(audio, type_mime):
        assert type_mime.startswith("audio/webm")
        return "Quel est le taux de chômage à Dakar ?"
    monkeypatch.setattr(transcription, "transcrire", transcrit)
    r = client.post("/api/transcribe", content=b"\x01" * 100,
                    headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200
    assert r.json() == {"texte": "Quel est le taux de chômage à Dakar ?"}


def test_quota_voix_separe_du_chat(client, monkeypatch):
    """La dictée (plusieurs partielles par question) ne consomme pas le quota
    des questions : un canal par usage."""
    main._hits.clear()
    monkeypatch.setattr(transcription, "disponible", lambda: True)

    async def transcrit(audio, type_mime):
        return "ok"
    monkeypatch.setattr(transcription, "transcrire", transcrit)
    for _ in range(main.RATE_MAX_VOIX):
        assert client.post("/api/transcribe", content=b"\x01",
                           headers={"Content-Type": "audio/webm"}).status_code == 200
    assert client.post("/api/transcribe", content=b"\x01",
                       headers={"Content-Type": "audio/webm"}).status_code == 429
    assert client.get("/api/health").status_code == 200
    r = client.post("/api/chat", json={"question": "Quelle est la population du Sénégal ?"})
    assert r.status_code == 200
    main._hits.clear()


@pytest.mark.parametrize("bruit", [
    "Sous-titres réalisés par la communauté d'Amara.org",
    "Merci d'avoir regardé cette vidéo !",
    "Merci.",
    "Dakar, Thiès, Diourbel",             # écho de l'indice de vocabulaire
    "Question sur les statistiques du Sénégal",
])
def test_hallucinations_whisper_ecartees(monkeypatch, bruit):
    monkeypatch.setattr(transcription, "_fournisseur", lambda: "groq")
    monkeypatch.setattr(transcription, "_cle", lambda: "cle-test")

    def repond(request):
        return httpx.Response(200, json={"text": bruit})
    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(transcription.httpx, "AsyncClient",
                        lambda **kw: vrai_client(transport=httpx.MockTransport(repond), **kw))
    assert asyncio.run(transcription.transcrire(b"\x01", "audio/webm")) == ""


def test_mot_isole_conserve(monkeypatch):
    """« Dakar » seul est une vraie dictée (suivi de conversation), pas un écho."""
    monkeypatch.setattr(transcription, "_fournisseur", lambda: "groq")
    monkeypatch.setattr(transcription, "_cle", lambda: "cle-test")
    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(transcription.httpx, "AsyncClient", lambda **kw: vrai_client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "Dakar."})), **kw))
    assert asyncio.run(transcription.transcrire(b"", "audio/webm")) == "Dakar."


def test_requete_fournisseur_conforme(monkeypatch):
    monkeypatch.setattr(transcription, "_fournisseur", lambda: "groq")
    monkeypatch.setattr(transcription, "_cle", lambda: "cle-test")
    vu = {}

    def repond(request):
        vu["url"] = str(request.url)
        vu["auth"] = request.headers["authorization"]
        vu["corps"] = request.content
        return httpx.Response(200, json={"text": " Quel est le PIB du Sénégal ? "})
    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(transcription.httpx, "AsyncClient",
                        lambda **kw: vrai_client(transport=httpx.MockTransport(repond), **kw))
    texte = asyncio.run(transcription.transcrire(b"\x01\x02", "audio/mp4"))
    assert texte == "Quel est le PIB du Sénégal ?"
    assert vu["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert vu["auth"] == "Bearer cle-test"
    assert b"whisper-large-v3-turbo" in vu["corps"] and b'filename="dictee.m4a"' in vu["corps"]
    assert b'name="language"' in vu["corps"]
