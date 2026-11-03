"""Sources de chiffres interrogeables, derrière un contrat commun.

La voie chiffrée ne connaît que `SourceStatistique`. Brancher une source de
l'ANSD (Plateforme Open Data, base interne) revient à ajouter un adaptateur,
sans toucher au reste du code. Chaque résultat porte sa provenance.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.core.config import settings


@dataclass
class Resultat:
    """Colonnes, lignes et provenance."""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    provenance: str = ""


class SourceIncapable(Exception):
    """Levée quand un adaptateur ne sait pas servir la requête."""


@runtime_checkable
class SourceStatistique(Protocol):
    """Contrat : `execute` reçoit une requête SELECT déjà validée. Un adaptateur
    qui ne parle pas SQL sert les formes qu'il connaît et lève `SourceIncapable`
    pour le reste."""

    def execute(self, sql: str) -> Resultat: ...

    def provenance(self) -> str: ...


class DataMartCurate:
    """Base statistique locale (SQLite, lecture seule), construite par scripts/seed_db.py."""

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
    """Adaptateurs essayés dans l'ordre : par exemple la Plateforme Open Data,
    puis la base locale en repli."""

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
            except Exception as e:  # panne d'un adaptateur distant
                derniere_erreur = e
                continue
        # aucune source n'a répondu : la dernière (base locale) fait foi
        raise derniere_erreur or SourceIncapable("aucune source disponible")

    def provenance(self) -> str:
        return " → ".join(s.provenance() for s in self.sources)
