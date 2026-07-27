"""
Journalisation des interactions et des retours utilisateurs (JSONL).

Justification (memoire, protocole d'evaluation) : l'evaluation de l'usabilite
(SUS, Brooke 1996) et l'analyse des erreurs en conditions reelles exigent une
trace persistante de chaque interaction : question, route choisie, confiance,
latence, verdict des guardrails, et retour explicite de l'utilisateur
(pouce haut/bas). Le format JSONL (une ligne JSON par evenement) est
directement exploitable par pandas pour l'analyse quantitative du memoire.

Confidentialite (Principe 6, Nations Unies 2014) : aucune donnee personnelle
n'est collectee ; seuls la question, les metadonnees techniques et un
identifiant de session anonyme sont enregistres.
"""
from __future__ import annotations
import json
import threading
import time
import uuid
from pathlib import Path

from app.core.config import settings

LOG_DIR = Path(settings.database_path).parent / "logs"
_lock = threading.Lock()


def _append(filename: str, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": round(time.time(), 3), **record}
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(LOG_DIR / filename, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def log_interaction(record: dict) -> None:
    _append("interactions.jsonl", record)


def log_feedback(record: dict) -> None:
    _append("feedback.jsonl", record)


def _read(filename: str) -> list[dict]:
    path = LOG_DIR / filename
    if not path.exists():
        return []
    out = []
    with _lock:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def metrics() -> dict:
    """Agregation de la telemetrie pour le pilotage du service et
    l'evaluation quantitative du memoire (P2-7). Un service se pilote par la
    mesure : volume, repartition des voies, latence, taux de refus, satisfaction.
    Aucune donnee personnelle (Principe 6)."""
    inter = _read("interactions.jsonl")
    fb = _read("feedback.jsonl")
    n = len(inter)
    routes: dict[str, int] = {}
    guardrails: dict[str, int] = {}
    latences = []
    caches = 0
    for r in inter:
        routes[r.get("route", "-")] = routes.get(r.get("route", "-"), 0) + 1
        g = r.get("guardrail", "ok")
        if g != "ok":
            guardrails[g] = guardrails.get(g, 0) + 1
        if isinstance(r.get("latency_ms"), (int, float)):
            latences.append(r["latency_ms"])
        if r.get("cached"):
            caches += 1
    latences.sort()

    def pct(p: float) -> float:
        return round(latences[min(len(latences) - 1, int(p * len(latences)))], 1) \
            if latences else 0.0

    # latence médiane par voie (observabilité : repérer une voie qui dérive)
    lat_par_voie: dict[str, list] = {}
    for r in inter:
        if isinstance(r.get("latency_ms"), (int, float)):
            lat_par_voie.setdefault(r.get("route", "-"), []).append(r["latency_ms"])
    lat_voie_med = {v: round(sorted(xs)[len(xs) // 2], 1)
                    for v, xs in lat_par_voie.items()}

    up = sum(1 for f in fb if f.get("rating") == "up")
    down = sum(1 for f in fb if f.get("rating") == "down")
    return {
        "interactions": n,
        "sessions_distinctes": len({r.get("session_id") for r in inter}),
        "repartition_voies": dict(sorted(routes.items(), key=lambda x: -x[1])),
        "taux_refus_guardrails": round(sum(guardrails.values()) / n, 4) if n else 0.0,
        "detail_refus": guardrails,
        "latence_ms": {"mediane": pct(0.5), "p90": pct(0.9), "p95": pct(0.95),
                       "p99": pct(0.99), "par_voie_mediane": lat_voie_med},
        "taux_cache": round(caches / n, 4) if n else 0.0,
        "feedback": {"positifs": up, "negatifs": down,
                     "satisfaction": round(up / (up + down), 3) if (up + down) else None},
    }
