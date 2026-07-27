"""
Adaptateur ODP — Plateforme Open Data de l'ANSD (preuve de concept).

Démontre, dans le code, la promesse de la décision #94 : brancher une source réelle
de l'ANSD revient à ajouter un adaptateur derrière le port `SourceStatistique`, sans
toucher au reste. Cet adaptateur interroge en direct la Plateforme Open Data
(senegal.opendataforafrica.org, moteur Knoema/Open Data for Africa, API REST JSON)
pour les séries qu'elle sert, et **renvoie une valeur avec sa provenance** (P1).

Résilience (même contrat que le client LLM) : toute indisponibilité — API injoignable,
délai dépassé, protection anti-robot, format inattendu — lève `SourceIncapable`, ce qui
fait basculer la `SourceComposite` sur l'entrepôt curaté (repli toujours disponible,
hors ligne). Le service ne tombe jamais à cause d'une dépendance distante.

Note d'intégration : l'hôte et l'identifiant de dataset sont configurables (le portail
cible et ses jeux de données varient) ; ils sont laissés en paramètres afin que
l'adaptateur soit pointé sur la bonne série au déploiement.
"""
from __future__ import annotations

import json
import re
import urllib.request

from app.sql.sources import Resultat, SourceIncapable

# Hôte de la Plateforme Open Data de l'ANSD (moteur Knoema).
ODP_HOST = "https://nso-senegal.opendataforafrica.org"
# Séries que cet adaptateur sait servir : forme SQL reconnue -> (dataset, requête API).
# Pour la preuve de concept, une série : l'inflation annuelle (IHPC).
_TIMEOUT = 6  # s — court : au-delà, on préfère le repli local à l'attente


class AdaptateurODP:
    """Adaptateur distant : lit une série sur la Plateforme Open Data de l'ANSD.

    Ne prétend PAS servir toute requête : il reconnaît les formes qu'il couvre
    (ici la série d'inflation) et lève `SourceIncapable` pour tout le reste —
    la source composite passe alors à l'adaptateur suivant (l'entrepôt curaté)."""

    def __init__(self, host: str = ODP_HOST, dataset: str | None = None,
                 timeout: int = _TIMEOUT):
        self.host = host.rstrip("/")
        self.dataset = dataset  # identifiant de jeu de données Knoema (à configurer)
        self.timeout = timeout

    def provenance(self) -> str:
        return f"Plateforme Open Data ANSD ({self.host})"

    def execute(self, sql: str) -> Resultat:
        s = sql.lower()
        # forme reconnue : série temporelle d'inflation
        if "from inflation" in s and "taux_inflation" in s:
            series = self._fetch_serie_temporelle()
            if not series:
                raise SourceIncapable("ODP : série vide ou indisponible")
            return Resultat(columns=["annee", "taux_inflation"],
                            rows=[(an, val) for an, val in series],
                            provenance=self.provenance())
        # tout le reste : hors périmètre de cet adaptateur
        raise SourceIncapable("ODP : forme non couverte par cet adaptateur")

    # -- appel API réel (Knoema / Open Data for Africa) -------------------
    def _fetch_serie_temporelle(self) -> list[tuple[int, float]]:
        """Interroge l'API JSON de l'ODP. Toute anomalie -> SourceIncapable
        (le consommateur bascule sur l'entrepôt curaté)."""
        url = f"{self.host}/api/1.0/data/details"
        body = json.dumps(self._pivot_request()).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "RAMA-ANSD/1.0 (assistant statistique)"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read().decode())
        except Exception as e:  # réseau, timeout, HTTP, JSON, anti-robot…
            raise SourceIncapable(f"ODP injoignable : {e}") from e
        return self._parse_pivot(payload)

    def _pivot_request(self) -> dict:
        """Requête « pivot » standard de l'API Knoema (structure documentée).
        Le dataset et les membres de dimension dépendent du portail cible ;
        laissés paramétrables pour l'intégration."""
        return {"Dataset": self.dataset or "", "Dimensions": [], "Frozen": []}

    @staticmethod
    def _parse_pivot(payload: dict) -> list[tuple[int, float]]:
        """Extrait (année, valeur) de la réponse pivot Knoema.
        Tolérant : renvoie [] si la forme n'est pas exploitable."""
        out: list[tuple[int, float]] = []
        data = payload.get("data") if isinstance(payload, dict) else None
        for point in (data or []):
            time = str(point.get("Time", ""))
            m = re.search(r"(19|20)\d{2}", time)
            val = point.get("Value")
            if m and isinstance(val, (int, float)):
                out.append((int(m.group(0)), float(val)))
        return sorted(set(out))
