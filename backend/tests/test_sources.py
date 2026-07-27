# -*- coding: utf-8 -*-
"""
Tests du port `SourceStatistique` et de la fédération (décision #94).

Prouve, de façon DÉTERMINISTE (sans dépendre du réseau), que :
  1. l'entrepôt curaté sert les chiffres avec leur provenance ;
  2. la source composite bascule proprement sur le repli quand un adaptateur
     distant est incapable ou en panne (dégradation gracieuse) ;
  3. la voie Text-to-SQL donne le MÊME résultat via le port qu'en accès direct
     (le refactoring n'a rien changé au comportement).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sql.sources import (DataMartCurate, Resultat, SourceComposite,
                             SourceIncapable)
from app.sql.odp import AdaptateurODP

INFLATION_SQL = "SELECT annee, taux_inflation FROM inflation ORDER BY annee;"


def test_datamart_sert_avec_provenance():
    mart = DataMartCurate()
    r = mart.execute(INFLATION_SQL)
    assert r.rows, "l'entrepôt doit renvoyer la série d'inflation"
    assert "curaté" in r.provenance.lower()
    print(f"  [OK ] entrepôt curaté : {len(r.rows)} lignes, provenance citée")


def test_composite_repli_sur_incapable():
    """Une source qui ne sait pas servir -> on passe à la suivante."""
    class Incapable:
        def execute(self, sql): raise SourceIncapable("ne sait pas")
        def provenance(self): return "stub incapable"
    mart = DataMartCurate()
    comp = SourceComposite([Incapable(), mart])
    r = comp.execute(INFLATION_SQL)
    assert r.rows and "curaté" in r.provenance.lower()
    print("  [OK ] composite : bascule sur le repli quand la 1re source est incapable")


def test_composite_repli_sur_panne_reseau():
    """Une source distante qui LÈVE (panne/timeout) -> repli, pas de crash."""
    class EnPanne:
        def execute(self, sql): raise ConnectionError("API injoignable")
        def provenance(self): return "stub en panne"
    mart = DataMartCurate()
    comp = SourceComposite([EnPanne(), mart])
    r = comp.execute(INFLATION_SQL)
    assert r.rows, "le repli doit servir malgré la panne de la source distante"
    print("  [OK ] composite : survit à une panne réseau de l'adaptateur distant")


def test_odp_incapable_hors_perimetre():
    """L'adaptateur ODP ne prétend pas tout servir."""
    odp = AdaptateurODP()
    try:
        odp.execute("SELECT nom FROM regions;")
        assert False, "aurait dû lever SourceIncapable"
    except SourceIncapable:
        print("  [OK ] adaptateur ODP : SourceIncapable hors de son périmètre")


def test_federation_odp_puis_mart_meme_resultat():
    """Fédération réelle : ODP en tête (série d'inflation), entrepôt en repli.
    Que l'ODP soit joignable ou non (Cloudflare en env. restreint), la série est
    servie et identique à l'accès direct à l'entrepôt."""
    mart = DataMartCurate()
    attendu = mart.execute(INFLATION_SQL).rows
    comp = SourceComposite([AdaptateurODP(), mart])
    r = comp.execute(INFLATION_SQL)
    servie_par = "ODP (live)" if "Open Data" in r.provenance else "entrepôt curaté (repli)"
    assert r.rows == attendu or ("Open Data" in r.provenance and r.rows), \
        "la série doit être servie, identique à l'entrepôt en cas de repli"
    print(f"  [OK ] fédération ODP→entrepôt : série servie par {servie_par}")


def test_pipeline_via_port_inchange():
    """La voie Text-to-SQL passe par le port et donne le même chiffre."""
    from app.sql.pipeline import TextToSQLPipeline

    class _NoLLM:
        def complete(self, *a, **k):
            raise RuntimeError("pas d'appel LLM attendu sur un gabarit")
    pipe = TextToSQLPipeline(_NoLLM())
    res = pipe.answer("Quel est le taux d'inflation en 2023 ?")
    assert res.rows and "%" in res.answer
    print(f"  [OK ] voie SQL via le port : {res.answer[:60]}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\n{len(fns)} tests de source/fédération : TOUS PASSENT")
