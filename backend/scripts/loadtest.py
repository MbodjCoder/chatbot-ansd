"""
Test de charge de l'API RAMA : envoie N requêtes avec une concurrence C et
mesure débit, latences (p50/p95/p99) et robustesse (200 servies, 429 limitées,
5xx = erreurs qui NE DOIVENT PAS exister). Cible les voies déterministes
(SQL/CATALOG, sans appel LLM) pour mesurer le serveur lui-même, pas le
fournisseur distant.

Usage :
    python scripts/loadtest.py --url http://127.0.0.1:8000 --n 120 --concurrency 40
"""
from __future__ import annotations
import argparse
import asyncio
import time

import httpx

QUESTIONS = [
    "Quelle est la population du Sénégal en 2023 ?",
    "Classe les régions par taux de pauvreté décroissant",
    "je veux les données sur la pêche au Sénégal",
    "Où télécharger le rapport EHCVM ?",
    "qui es-tu ?",
]


async def worker(client, url, q, sink):
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{url}/api/chat", json={"question": q}, timeout=30)
        dt = (time.perf_counter() - t0) * 1000
        sink.append((r.status_code, dt))
    except Exception:  # réseau/timeout : compté comme échec réseau
        sink.append(("ERR", (time.perf_counter() - t0) * 1000))


async def run(url: str, n: int, concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    sink: list = []

    async with httpx.AsyncClient() as client:
        async def guarded(i):
            async with sem:
                await worker(client, url, QUESTIONS[i % len(QUESTIONS)], sink)

        t0 = time.perf_counter()
        await asyncio.gather(*(guarded(i) for i in range(n)))
        wall = time.perf_counter() - t0
    return sink, wall


def pct(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--concurrency", type=int, default=40)
    a = ap.parse_args()

    sink, wall = asyncio.run(run(a.url, a.n, a.concurrency))
    ok = [dt for code, dt in sink if code == 200]
    r429 = [dt for code, dt in sink if code == 429]
    r5xx = [dt for code, dt in sink if isinstance(code, int) and code >= 500]
    errs = [dt for code, dt in sink if code == "ERR"]

    print("=" * 60)
    print(f"CHARGE : {a.n} requêtes, concurrence {a.concurrency}, {a.url}")
    print("=" * 60)
    print(f"  Servies (200)        : {len(ok)}")
    print(f"  Limitées (429)       : {len(r429)}   (rate-limit = comportement voulu)")
    print(f"  Erreurs serveur (5xx): {len(r5xx)}   <-- doit être 0")
    print(f"  Exceptions réseau    : {len(errs)}")
    print(f"  Débit                : {a.n / wall:.1f} req/s sur {wall:.2f}s")
    if ok:
        print(f"  Latence 200  p50/p95/p99 : {pct(ok,.5):.0f} / {pct(ok,.95):.0f} / "
              f"{pct(ok,.99):.0f} ms")
    verdict = "OK" if (len(r5xx) == 0 and len(errs) == 0) else "ÉCHEC (erreurs serveur)"
    print(f"  Verdict robustesse   : {verdict}")
    return 0 if (len(r5xx) == 0 and len(errs) == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
