"""Voie chiffrée : question -> requête SQL -> réponse rédigée.

1. Gabarits déterministes pour les questions fréquentes (app/sql/templates.py).
2. Sinon, génération par le modèle de langage, avec correction automatique en
   cas d'erreur d'exécution (approche DIN-SQL, Pourreza et Rafiei 2023).

Sécurité : lecture seule, requêtes SELECT uniquement.
Les chiffres de la réponse viennent toujours de la base, jamais du modèle.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from app.core.config import settings
from app.llm.client import LLMClient
from app.sql.sources import DataMartCurate, SourceStatistique

SCHEMA_DESCRIPTION = """Tables disponibles (base statistique ANSD) :
- regions(id, nom, chef_lieu, superficie_km2) : les 14 régions du Sénégal
- demographie(region_id, annee, population) : population par région aux recensements (2013, 2023)
- population_nationale(annee, population) : population totale aux recensements 1976 à 2023
- population_2025(region_id, hommes, femmes, population, urbaine, rurale, part_urbaine) : projection ANSD 2025 par région
- structure_age_2025(region_id, groupe_age, age_min, hommes, femmes, population) : projection ANSD 2025 par région et groupe d'âges ('0-4' ... '80+')
- emploi(annee, trimestre, taux_chomage_elargi, taux_chomage_bit, taux_activite) : ENES trimestrielle (%, 2023-2025)
- inflation(annee, taux_inflation) : variation annuelle moyenne de l'IHPC (%, 2019-2024)
- pauvrete(region_id, taux_pauvrete, profondeur, severite, gini, conso_moyenne_fcfa) : EHCVM II 2021/2022 par région
- pib(annee, croissance_reelle) : croissance du PIB réel (%, 2022-2024)
- indicateurs_nationaux(code, libelle, valeur, unite, annee, source) : indicateurs de référence

Correspondances :
- chômage -> emploi.taux_chomage_elargi ; inflation, prix -> inflation.taux_inflation
- population -> demographie (régions, recensements), population_nationale (pays), population_2025 (projection)
- hommes, femmes, urbain, rural -> population_2025 ; tranches d'âge -> structure_age_2025
- pauvreté -> pauvrete.taux_pauvrete ou indicateurs_nationaux code='pauvrete_nationale'
- noms de régions sans accents, comparés avec lower(r.nom), ex. lower(r.nom)='thies'
"""

FEW_SHOTS = """Exemples :
Q: Quelle était la population de Dakar en 2023 ?
SQL: SELECT r.nom, d.annee, d.population FROM demographie d JOIN regions r ON r.id=d.region_id WHERE lower(r.nom)='dakar' AND d.annee=2023;
Q: Quel est le taux de chômage le plus récent ?
SQL: SELECT annee, trimestre, taux_chomage_elargi FROM emploi ORDER BY annee DESC, trimestre DESC LIMIT 1;
Q: Classe les régions par taux de pauvreté décroissant.
SQL: SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r ON r.id=p.region_id ORDER BY p.taux_pauvrete DESC;
Q: Combien de femmes vivent à Kolda ?
SQL: SELECT r.nom, 2025 AS annee, p.hommes, p.femmes, p.population FROM population_2025 p JOIN regions r ON r.id=p.region_id WHERE lower(r.nom)='kolda';
Q: Comment la population du Sénégal a-t-elle évolué depuis 1976 ?
SQL: SELECT annee, population FROM population_nationale ORDER BY annee;
"""

SQL_SYSTEM = f"""SQL_GENERATION - Tu traduis une question en une requête SQLite.
{SCHEMA_DESCRIPTION}
{FEW_SHOTS}
Règles : une seule requête SELECT valide, sans commentaire ni explication."""

# Noms de régions affichés avec leurs accents (la base les stocke sans)
NOMS_AFFICHES = {"Thies": "Thiès", "Kedougou": "Kédougou", "Sedhiou": "Sédhiou"}


@dataclass
class SQLResult:
    answer: str
    sql: str = ""
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    error: str | None = None
    retries: int = 0


class TextToSQLPipeline:
    def __init__(self, llm: LLMClient, source: SourceStatistique | None = None,
                 db_path: str | None = None):
        self.llm = llm
        self.db_path = db_path or settings.database_path
        # La voie dépend d'un contrat de source : une source distante
        # (Plateforme Open Data) se branche en la passant ici.
        self.source: SourceStatistique = source or DataMartCurate(self.db_path)

    @staticmethod
    def _is_safe(sql: str) -> bool:
        s = sql.strip().rstrip(";").lower()
        if not s.startswith("select"):
            return False
        interdits = ["insert", "update", "delete", "drop", "alter", "attach",
                     "pragma", "create", ";"]
        return not any(f in s for f in interdits)

    def _execute(self, sql: str):
        r = self.source.execute(sql)
        lignes = r.rows
        if "nom" in r.columns:
            i = r.columns.index("nom")
            lignes = [tuple(NOMS_AFFICHES.get(v, v) if j == i else v for j, v in enumerate(ligne))
                      for ligne in lignes]
        return r.columns, lignes

    @staticmethod
    def _extract_sql(text: str) -> str:
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S)
        sql = (m.group(1) if m else text).strip()
        return sql.split(";")[0].strip() + ";"

    def answer(self, question: str) -> SQLResult:
        from app.sql.templates import template_sql
        gabarit = template_sql(question)
        if gabarit is not None:
            try:
                cols, rows = self._execute(gabarit)
                if rows:
                    return SQLResult(answer=self._verbalize(question, cols, rows),
                                     sql=gabarit, rows=rows, columns=cols)
            except sqlite3.Error:
                pass
        prompt, derniere_erreur = question, None
        for essai in range(settings.sql_max_retries + 1):
            resp = self.llm.complete(SQL_SYSTEM, prompt, temperature=settings.llm_temperature)
            sql = self._extract_sql(resp.text)
            if not self._is_safe(sql):
                return SQLResult(answer="Requête refusée : seules les lectures (SELECT) sont autorisées.",
                                 sql=sql, error="unsafe", retries=essai)
            try:
                cols, rows = self._execute(sql)
                return SQLResult(answer=self._verbalize(question, cols, rows),
                                 sql=sql, rows=rows, columns=cols, retries=essai)
            except sqlite3.Error as e:
                derniere_erreur = str(e)
                prompt = (f"{question}\nLa requête précédente `{sql}` a échoué "
                          f"avec l'erreur : {derniere_erreur}. Corrige-la.")
        return SQLResult(answer="La requête n'a pas pu être exécutée sur la base.",
                         error=derniere_erreur, retries=settings.sql_max_retries)

    @staticmethod
    def _verbalize(question: str, cols: list, rows: list) -> str:
        if cols == ["1"]:                     # requête de repli « SELECT 1 »
            return ("Je n'ai pas trouvé cette information dans la base de données. "
                    "Reformulez votre question, ou consultez les publications proposées ci-dessous.")
        if not rows:
            return "Aucune donnée ne correspond à cette question dans la base."
        if len(rows) == 1:
            phrase = _humanize_row(question, dict(zip(cols, rows[0])))
            if phrase:
                return phrase
            paires = ", ".join(f"{_LIBELLES.get(c, c)} : {_fr(v)}"
                               for c, v in zip(cols, rows[0]) if v is not None)
            return f"Selon les données de l'ANSD, {paires}." if paires else _INDISPONIBLE
        if not any(v is not None for r in rows for v in r):
            return _INDISPONIBLE
        if cols and cols[0] == "nom" and len(cols) >= 2:
            phrase = _classement_regions(cols, rows)
            if phrase:
                return phrase
        lignes = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows[:15]]
        suite = f"\n... ({len(rows)} lignes au total)" if len(rows) > 15 else ""
        return "Résultats (base ANSD) :\n" + "\n".join(lignes) + suite


# ---------------------------------------------------------------- rédaction
_INDISPONIBLE = ("Cette donnée précise n'est pas disponible dans la base chiffrée. "
                 "Elle figure peut-être dans une publication de l'ANSD : voyez les "
                 "sources proposées ci-dessous, ou reformulez votre question.")

_LIBELLES = {
    "annee": "année", "trimestre": "trimestre", "nom": "région",
    "population": "population", "taux_chomage_elargi": "taux de chômage élargi",
    "taux_chomage_bit": "taux de chômage (BIT)", "taux_activite": "taux d'activité",
    "taux_inflation": "taux d'inflation", "croissance_reelle": "croissance du PIB",
    "taux_pauvrete": "taux de pauvreté", "gini": "indice de Gini",
    "superficie_km2": "superficie", "densite_hab_km2": "densité",
    "libelle": "indicateur", "valeur": "valeur", "unite": "unité",
    "source": "source", "conso_moyenne_fcfa": "consommation moyenne",
    "hommes": "hommes", "femmes": "femmes", "part_urbaine": "population urbaine (%)",
    "tranche": "tranche d'âge", "effectif": "effectif", "part": "part (%)",
}


def _fr(v) -> str:
    """Nombre à la française : espace des milliers, virgule décimale."""
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    if isinstance(v, float):
        return f"{v:,.10g}".replace(",", " ").replace(".", ",")
    return str(v)


def _sup(question: str) -> str | None:
    """« plus » = maximum, « moins » = minimum ; « le plus faible » inverse le sens."""
    m = re.search(r"\b(plus|moins)\s*(\w*)", question.lower())
    if not m:
        return None
    direction = m.group(1)
    if m.group(2) in {"faible", "faibles", "bas", "basse", "petit", "petite"}:
        direction = "moins" if direction == "plus" else "plus"
    return direction


_RANK_META = {
    "population": ("population", " habitants", "RGPH-5, 2023"),
    "taux_pauvrete": ("taux de pauvreté", " %", "EHCVM II"),
    "gini": ("indice de Gini", "", "EHCVM II"),
    "superficie_km2": ("superficie", " km²", ""),
    "densite_hab_km2": ("densité", " habitants/km²", "RGPH-5, 2023"),
    "part_urbaine": ("part de population urbaine", " %", "projection ANSD 2025"),
}


def _classement_regions(cols: list, rows: list) -> str | None:
    """Phrase d'introduction d'un classement ; le détail s'affiche en tableau.

    Aucun nombre absent des résultats ne doit y figurer (contrôle de fidélité)."""
    meta = _RANK_META.get(cols[-1])
    if not meta:
        return None
    libelle, unite, source = meta
    try:
        v0, vN = rows[0][-1], rows[-1][-1]
    except (IndexError, TypeError):
        return None
    if v0 is None or vN is None:
        return None
    if cols[-1] == "population":
        sens = "de la plus peuplée à la moins peuplée" if v0 >= vN else "de la moins peuplée à la plus peuplée"
    else:
        sens = "de la plus élevée à la plus faible" if v0 >= vN else "de la plus faible à la plus élevée"
    src = f" ({source})" if source else ""
    return (f"Voici le classement des régions du Sénégal par {libelle}{src}, {sens}. "
            f"En tête : **{rows[0][0]}** (**{_fr(v0)}{unite}**). Le détail complet figure ci-dessous.")


def _humanize_row(question: str, d: dict) -> str | None:
    """Phrase naturelle pour les formes de résultat connues."""
    annee = d.get("annee")
    quand = f" en {annee}" if annee else ""
    sup = _sup(question)
    nom = d.get("nom")
    lieu = f"la région de **{nom}**" if nom else "le Sénégal"

    if "libelle" in d and "valeur" in d:
        unite = {"pourcent": "%"}.get(d.get("unite") or "", d.get("unite") or "")
        return (f"{d['libelle']} : **{_fr(d['valeur'])} {unite}**".rstrip()
                + (f" ({annee}, source ANSD)." if annee else " (source ANSD)."))

    # projections démographiques 2025
    if "tranche" in d and d.get("effectif") is not None:
        return (f"En 2025, {lieu} compte **{_fr(d['effectif'])} personnes de {d['tranche']}**, "
                f"soit **{_fr(d['part'])} %** de sa population (projection ANSD).")
    if "hommes" in d and "femmes" in d:
        return (f"En 2025, {lieu} compte **{_fr(d['femmes'])} femmes** et "
                f"**{_fr(d['hommes'])} hommes**, soit **{_fr(d['population'])} habitants** "
                "(projection ANSD).")
    if "part_urbaine" in d:
        if nom and sup:
            adj = "la plus urbanisée" if sup == "plus" else "la moins urbanisée"
            return (f"La région {adj} est **{nom}** : **{_fr(d['part_urbaine'])} %** "
                    "de sa population vit en milieu urbain en 2025 (projection ANSD).")
        ou = f"de la région de **{nom}**" if nom else "du Sénégal"
        return (f"En 2025, **{_fr(d['part_urbaine'])} %** de la population {ou} "
                "vit en milieu urbain (projection ANSD).")
    if annee == 2025 and "population" in d:
        return f"En 2025, {lieu} compte **{_fr(d['population'])} habitants** (projection ANSD)."

    if nom and "population" in d:
        if sup:
            adj = "la plus peuplée" if sup == "plus" else "la moins peuplée"
            return (f"La région {adj} du Sénégal est **{nom}**, avec "
                    f"**{_fr(d['population'])} habitants**{quand} (RGPH-5).")
        return f"La région de **{nom}** comptait **{_fr(d['population'])} habitants**{quand} (RGPH-5)."
    if nom and "taux_pauvrete" in d:
        if sup:
            adj = "le plus élevé" if sup == "plus" else "le plus faible"
            return (f"C'est à **{nom}** que le taux de pauvreté est {adj} : "
                    f"**{_fr(d['taux_pauvrete'])} %** (EHCVM II).")
        return f"Le taux de pauvreté dans la région de **{nom}** est de **{_fr(d['taux_pauvrete'])} %** (EHCVM II)."
    if nom and "gini" in d:
        return f"L'indice de Gini de la région de **{nom}** est de **{_fr(d['gini'])}** (EHCVM II)."
    if nom and "superficie_km2" in d:
        return f"La région de **{nom}** s'étend sur **{_fr(d['superficie_km2'])} km²**."
    if nom and "densite_hab_km2" in d:
        return (f"La densité de population de la région de **{nom}** est de "
                f"**{_fr(d['densite_hab_km2'])} habitants/km²** (RGPH-5).")
    if "taux_chomage_elargi" in d:
        t = d.get("trimestre")
        periode = f"au {t}ᵉ trimestre {annee}" if t and annee else quand.strip() or "à la dernière enquête"
        return f"Le taux de chômage (au sens élargi) était de **{_fr(d['taux_chomage_elargi'])} %** {periode} (ENES)."
    if "taux_activite" in d:
        t = d.get("trimestre")
        periode = f"au {t}ᵉ trimestre {annee}" if t and annee else quand.strip() or "à la dernière enquête"
        return f"Le taux d'activité était de **{_fr(d['taux_activite'])} %** {periode} (ENES)."
    if "taux_inflation" in d:
        return f"L'inflation annuelle moyenne{quand} était de **{_fr(d['taux_inflation'])} %** (IHPC)."
    if "croissance_reelle" in d:
        return f"La croissance réelle du PIB{quand} était de **{_fr(d['croissance_reelle'])} %** (comptes nationaux)."
    if "population" in d:
        return f"Le Sénégal comptait **{_fr(d['population'])} habitants**{quand} (recensement)."
    return None
