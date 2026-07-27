"""
Port « source statistique » et ses adaptateurs (architecture hexagonale).

Justification (mémoire §4.2, décision #94) : l'écosystème d'information de l'ANSD est
*fédéré* — Plateforme Open Data (API JSON/CSV), répertoire des localités, portails
sectoriels, archive ANADS, et des chiffres « phares » publiés d'abord dans des rapports.
La voie numérique ne doit donc pas être couplée à un stockage figé : elle dépend d'un
**contrat** (port) `SourceStatistique`, dont l'entrepôt curaté (SQLite, ETL rejouable) est
la première réalisation. Brancher une source réelle de l'ANSD = ajouter un adaptateur
derrière le même contrat, sans toucher au reste de l'architecture.

Chaque adaptateur renvoie une valeur ET sa provenance : la garantie P1 (ancrage numérique
vérifiable) est ainsi préservée quel que soit le stockage sous-jacent.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.core.config import settings


@dataclass
class Resultat:
    """Résultat d'une interrogation : colonnes, lignes, et provenance citable."""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    provenance: str = ""


class SourceIncapable(Exception):
    """Levée par un adaptateur qui ne sait pas servir cette requête — le
    consommateur (source composite) passe alors à la source suivante."""


@runtime_checkable
class SourceStatistique(Protocol):
    """Contrat d'une source de chiffres officiels interrogeable.

    Le consommateur (la voie Text-to-SQL) ne connaît que ce contrat, jamais le
    stockage réel derrière. `execute` reçoit une requête SQL SELECT (déjà validée
    en amont) ; un adaptateur qui ne parle pas SQL (API distante) reconnaît les
    formes qu'il sait servir et lève `SourceIncapable` pour le reste."""

    def execute(self, sql: str) -> Resultat: ...

    def provenance(self) -> str: ...


class DataMartCurate:
    """Adaptateur EN PLACE : entrepôt statistique curaté (SQLite, lecture seule).

    Les chiffres publiés par l'ANSD sont extraits une fois par un ETL rejouable
    (`seed_db.py`, assertions sur les totaux officiels) et structurés en tables.
    Déterministe, hors-ligne, chaque valeur sourcée : le socle sûr de la voie
    numérique (P1)."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.database_path

    def execute(self, sql: str) -> Resultat:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(200)
            return Resultat(columns=cols, rows=list(rows), provenance=self.provenance())
        finally:
            con.close()

    def provenance(self) -> str:
        return "Entrepôt statistique curaté ANSD (ansd_stats.db, ETL rejouable)"


class SourceComposite:
    """Fédération d'adaptateurs, essayés dans l'ordre. Le premier qui sait servir
    la requête répond ; sinon on passe au suivant (dégradation gracieuse — même
    principe que le client LLM). Permet de brancher une source distante (ODP) en
    tête tout en gardant l'entrepôt curaté comme repli toujours disponible."""

    def __init__(self, sources: list[SourceStatistique]):
        if not sources:
            raise ValueError("SourceComposite exige au moins une source")
        self.sources = sources

    def execute(self, sql: str) -> Resultat:
        derniere_erreur: Exception | None = None
        for src in self.sources:
            try:
                return src.execute(sql)
            except SourceIncapable as e:
                derniere_erreur = e
                continue
            except Exception as e:  # panne réseau/API d'un adaptateur distant
                derniere_erreur = e
                continue
        # aucune source n'a pu répondre : on relaie à la dernière (repli mart)
        raise derniere_erreur or SourceIncapable("aucune source disponible")

    def provenance(self) -> str:
        return " → ".join(s.provenance() for s in self.sources)
