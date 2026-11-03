"""Adaptateur de la Plateforme Open Data de l'ANSD (preuve de concept).

Lit une série en direct (API Knoema, senegal.opendataforafrica.org). Toute
indisponibilité lève `SourceIncapable` : la base locale prend le relais.
L'hôte et le jeu de données sont des paramètres, à fixer au déploiement.
"""
from __future__ import annotations

import json
import re
import urllib.request

from app.sql.sources import Resultat, SourceIncapable

ODP_HOST = "https://nso-senegal.opendataforafrica.org"
_TIMEOUT = 6  # secondes ; au-delà, repli sur la base locale


class AdaptateurODP:
    """Sert la série d'inflation ; lève `SourceIncapable` pour le reste."""

    def __init__(self, host: str = ODP_HOST, dataset: str | None = None,
                 timeout: int = _TIMEOUT):
        self.host = host.rstrip("/")
        self.dataset = dataset  # identifiant du jeu de données Knoema
        self.timeout = timeout

    def provenance(self) -> str:
        return f"Plateforme Open Data ANSD ({self.host})"

    def execute(self, sql: str) -> Resultat:
        s = sql.lower()
        # série d'inflation
        if "from inflation" in s and "taux_inflation" in s:
            series = self._fetch_serie_temporelle()
            if not series:
                raise SourceIncapable("ODP : série vide ou indisponible")
            return Resultat(columns=["annee", "taux_inflation"],
                            rows=[(an, val) for an, val in series],
                            provenance=self.provenance())
        raise SourceIncapable("ODP : forme non couverte par cet adaptateur")

    def _fetch_serie_temporelle(self) -> list[tuple[int, float]]:
        """Interroge l'API ; toute anomalie lève SourceIncapable."""
        url = f"{self.host}/api/1.0/data/details"
        body = json.dumps(self._pivot_request()).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "Chatbot-ANSD/1.0 (assistant statistique)"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read().decode())
        except Exception as e:  # réseau, délai, HTTP, format, protection anti-robot
            raise SourceIncapable(f"ODP injoignable : {e}") from e
        return self._parse_pivot(payload)

    def _pivot_request(self) -> dict:
        """Requête « pivot » de l'API Knoema."""
        return {"Dataset": self.dataset or "", "Dimensions": [], "Frozen": []}

    @staticmethod
    def _parse_pivot(payload: dict) -> list[tuple[int, float]]:
        """Extrait les couples (année, valeur) ; [] si la réponse est inexploitable."""
        out: list[tuple[int, float]] = []
        data = payload.get("data") if isinstance(payload, dict) else None
        for point in (data or []):
            time = str(point.get("Time", ""))
            m = re.search(r"(19|20)\d{2}", time)
            val = point.get("Value")
            if m and isinstance(val, (int, float)):
                out.append((int(m.group(0)), float(val)))
        return sorted(set(out))
