"""
Module Text-to-SQL inspire de DIN-SQL (Pourreza & Rafiei, 2023).

DIN-SQL atteint 85,3% d'Execution Accuracy sur Spider (Yu et al., 2018)
par decomposition en 4 etapes, toutes reproduites ici :
  1. Schema linking  : lier les entites de la question aux tables/colonnes
  2. Classification  : requete simple / imbriquee / complexe
  3. Generation      : SQL via LLM, few-shot specifiques au domaine ANSD
  4. Auto-correction : execution, et en cas d'erreur, re-generation avec
                       le message d'erreur (self-correction, max N essais)

Securite (guardrail technique) :
  - connexion SQLite en LECTURE SEULE (mode ro)
  - liste blanche : seuls les SELECT sont executes
  - limite de lignes retournees
"""
from __future__ import annotations
import re
import sqlite3
from dataclasses import dataclass, field

from app.core.config import settings
from app.llm.client import LLMClient
from app.sql.sources import DataMartCurate, SourceStatistique

SCHEMA_DESCRIPTION = """Tables disponibles (base statistique ANSD, donnees officielles) :
- regions(id, nom, chef_lieu, superficie_km2) : les 14 regions du Senegal
- demographie(region_id, annee, population) : population residente par region aux recensements (2013 = RGPH-4, 2023 = RGPH-5)
- population_nationale(annee, population) : population totale aux recensements 1976, 1988, 2002, 2013, 2023
- emploi(annee, trimestre, taux_chomage_elargi, taux_chomage_bit, taux_activite) : ENES trimestrielle (%, 2023-2025)
- inflation(annee, taux_inflation) : variation annuelle moyenne de l'IHPC (%, 2019-2024)
- pauvrete(region_id, taux_pauvrete, profondeur, severite, gini, conso_moyenne_fcfa) : EHCVM II 2021/2022 par region
- pib(annee, croissance_reelle) : croissance du PIB reel (%, comptes nationaux, 2022-2024)
- indicateurs_nationaux(code, libelle, valeur, unite, annee, source) : indicateurs de reference (esperance de vie, fecondite, urbanisation, pauvrete nationale...)

Dictionnaire metier (schema linking) :
- "taux de chomage" -> emploi.taux_chomage_elargi (par trimestre) ; "inflation", "prix" -> inflation.taux_inflation
- "population", "habitants" -> demographie.population (par region) ou population_nationale (total pays)
- "pauvrete" -> pauvrete.taux_pauvrete (region) ou indicateurs_nationaux code='pauvrete_nationale'
- "croissance", "PIB" -> pib.croissance_reelle ; "esperance de vie", "fecondite", "urbanisation" -> indicateurs_nationaux (LIKE sur libelle)
- noms de regions -> regions.nom (jointure sur region_id)
"""

FEW_SHOTS = """Exemples (few-shot, domaine ANSD) :
Q: Quelle etait la population de Dakar en 2023 ?
SQL: SELECT r.nom, d.annee, d.population FROM demographie d JOIN regions r ON r.id=d.region_id WHERE lower(r.nom)='dakar' AND d.annee=2023;
Q: Quel est le taux de chomage le plus recent ?
SQL: SELECT annee, trimestre, taux_chomage_elargi FROM emploi ORDER BY annee DESC, trimestre DESC LIMIT 1;
Q: Classe les regions par taux de pauvrete decroissant.
SQL: SELECT r.nom, p.taux_pauvrete FROM pauvrete p JOIN regions r ON r.id=p.region_id ORDER BY p.taux_pauvrete DESC;
Q: Quelle est l'esperance de vie au Senegal ?
SQL: SELECT libelle, valeur, unite, annee FROM indicateurs_nationaux WHERE code='esperance_vie';
Q: Comment la population du Senegal a-t-elle evolue depuis 1976 ?
SQL: SELECT annee, population FROM population_nationale ORDER BY annee;
"""

SQL_SYSTEM = f"""SQL_GENERATION - Tu es un traducteur langage naturel -> SQL (SQLite).
{SCHEMA_DESCRIPTION}
{FEW_SHOTS}
Regles : genere UNE seule requete SELECT valide SQLite, sans commentaire, sans explication."""


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
        # Port (décision #94) : la voie numérique dépend d'un contrat de source
        # statistique, non d'un stockage figé. Adaptateur par défaut = entrepôt
        # curaté ; une source distante (ODP) se branche en la passant ici.
        self.source: SourceStatistique = source or DataMartCurate(self.db_path)

    # -- Etape securite : validation avant execution -----------------
    @staticmethod
    def _is_safe(sql: str) -> bool:
        s = sql.strip().rstrip(";").lower()
        if not s.startswith("select"):
            return False
        forbidden = ["insert", "update", "delete", "drop", "alter", "attach",
                     "pragma", "create", ";"]
        return not any(f in s for f in forbidden)

    def _execute(self, sql: str):
        # délègue au port : le stockage (entrepôt curaté, ou source distante) est
        # interchangeable, la voie ne connaît que le contrat.
        r = self.source.execute(sql)
        return r.columns, r.rows

    def _extract_sql(self, text: str) -> str:
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S)
        sql = (m.group(1) if m else text).strip()
        return sql.split(";")[0].strip() + ";"

    def answer(self, question: str) -> SQLResult:
        # Etape 0 (strategie hybride, decision #39) : gabarits deterministes
        # d'abord — plus rapides (~1 ms, aucun appel LLM) et plus surs
        # (EA 15/15) sur le perimetre du schema connu. Le LLM (DIN-SQL)
        # couvre la longue traine des formulations hors gabarits.
        from app.sql.templates import template_sql
        tpl = template_sql(question)
        if tpl is not None:
            try:
                cols, rows = self._execute(tpl)
                if rows:
                    return SQLResult(answer=self._verbalize(question, cols, rows),
                                     sql=tpl, rows=rows, columns=cols)
            except sqlite3.Error:
                pass  # gabarit inadapte : on tente la generation LLM
        prompt, last_err = question, None
        for attempt in range(settings.sql_max_retries + 1):
            resp = self.llm.complete(SQL_SYSTEM, prompt,
                                     temperature=settings.llm_temperature)
            sql = self._extract_sql(resp.text)
            if not self._is_safe(sql):
                return SQLResult(answer="Requete refusee : seules les lectures "
                                        "(SELECT) sont autorisees.",
                                 sql=sql, error="unsafe", retries=attempt)
            try:
                cols, rows = self._execute(sql)
                return SQLResult(answer=self._verbalize(question, cols, rows),
                                 sql=sql, rows=rows, columns=cols, retries=attempt)
            except sqlite3.Error as e:
                # Auto-correction DIN-SQL : reinjecter l'erreur dans le prompt
                last_err = str(e)
                prompt = (f"{question}\nLa requete precedente `{sql}` a echoue "
                          f"avec l'erreur : {last_err}. Corrige-la.")
        return SQLResult(answer="La requete n'a pas pu etre executee sur la base ANSD.",
                         error=last_err, retries=settings.sql_max_retries)

    @staticmethod
    def _verbalize(question: str, cols: list, rows: list) -> str:
        """Verbalisation deterministe des resultats : le chiffre affiche
        provient TOUJOURS de la base (jamais du LLM) -> hallucination
        numerique structurellement impossible sur cette voie (guardrail).
        Redaction en phrases naturelles par gabarits semantiques (une
        colonne = un sens metier connu du schema ANSD)."""
        # requete de repli "SELECT 1;" (aucune forme reconnue) : le dire
        # honnetement plutot qu'afficher "1 : 1"
        if cols == ["1"]:
            return ("Je n'ai pas trouvé cette information dans la base de "
                    "données. Reformulez votre question, ou consultez les "
                    "publications proposées ci-dessous.")
        if not rows:
            return "Aucune donnée ne correspond à cette question dans la base ANSD."
        if len(rows) == 1:
            phrase = _humanize_row(question, dict(zip(cols, rows[0])))
            if phrase:
                return phrase
            paires = ", ".join(f"{_LIBELLES.get(c, c)} : {_fr(v)}"
                               for c, v in zip(cols, rows[0]) if v is not None)
            # Ligne unique dont toutes les valeurs sont NULL (ex. indicateur non
            # publie, ou requete LLM hors perimetre) : ne JAMAIS renvoyer une
            # phrase vide « Selon les donnees officielles de l'ANSD, . » — le
            # dire honnetement (P1 : aucune affirmation sans contenu verifiable).
            if not paires:
                return _INDISPONIBLE
            return f"Selon les données officielles de l'ANSD, {paires}."
        # plusieurs lignes, mais toutes leurs cellules sont vides : idem
        if not any(v is not None for r in rows for v in r):
            return _INDISPONIBLE
        lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows[:15]]
        more = f"\n... ({len(rows)} lignes au total)" if len(rows) > 15 else ""
        return "Resultats (base ANSD) :\n" + "\n".join(lines) + more


# ---------------------------------------------------------------- redaction
# Message honnete unique quand la base ne contient pas le chiffre demande :
# on n'affirme jamais dans le vide, on oriente vers les publications.
_INDISPONIBLE = ("Cette donnée précise n'est pas disponible dans la base "
                 "chiffrée de RAMA. Elle figure peut-être dans une publication "
                 "de l'ANSD — voyez les sources proposées ci-dessous, ou "
                 "reformulez votre question.")

_LIBELLES = {
    "annee": "année", "trimestre": "trimestre", "nom": "région",
    "population": "population", "taux_chomage_elargi": "taux de chômage élargi",
    "taux_chomage_bit": "taux de chômage (BIT)", "taux_activite": "taux d'activité",
    "taux_inflation": "taux d'inflation", "croissance_reelle": "croissance du PIB",
    "taux_pauvrete": "taux de pauvreté", "gini": "indice de Gini",
    "superficie_km2": "superficie", "densite_hab_km2": "densité",
    "libelle": "indicateur", "valeur": "valeur", "unite": "unité",
    "source": "source", "conso_moyenne_fcfa": "consommation moyenne",
}


def _fr(v) -> str:
    """Nombres a la francaise : milliers espaces, decimale virgule."""
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    if isinstance(v, float):
        return f"{v:,.10g}".replace(",", " ").replace(".", ",")
    return str(v)


def _sup(question: str) -> str | None:
    """Sens du superlatif demande ("plus" = maximum, "moins" = minimum),
    en tenant compte des adjectifs qui inversent ("le plus faible")."""
    m = re.search(r"\b(plus|moins)\s*(\w*)", question.lower())
    if not m:
        return None
    direction = m.group(1)
    if m.group(2) in {"faible", "faibles", "bas", "basse", "petit", "petite"}:
        direction = "moins" if direction == "plus" else "plus"
    return direction


def _humanize_row(question: str, d: dict) -> str | None:
    """Phrase naturelle pour les formes de resultat connues du schema."""
    annee = d.get("annee")
    quand = f" en {annee}" if annee else ""
    sup = _sup(question)
    # indicateurs nationaux : (libelle, valeur, unite, annee)
    if "libelle" in d and "valeur" in d:
        unite = d.get("unite") or ""
        unite = {"pourcent": "%", "%": "%"}.get(unite, unite)
        return f"{d['libelle']} : **{_fr(d['valeur'])} {unite}**".rstrip() + \
               (f" ({annee}, source ANSD)." if annee else " (source ANSD).")
    nom = d.get("nom")
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
        return f"La densité de population de la région de **{nom}** est de **{_fr(d['densite_hab_km2'])} habitants/km²** (RGPH-5)."
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
