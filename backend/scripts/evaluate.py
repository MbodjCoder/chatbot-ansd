"""Évaluation de bout en bout sur le jeu de référence data/eval/gold.jsonl :
voie attendue, faits et liens présents, refus hors périmètre, fidélité.

Usage   : cd backend && python scripts/evaluate.py
Sorties : rapport console, docs/EVALUATION.md, data/eval/report.json
"""
from __future__ import annotations
import io
import json
import sys
import time
import unicodedata
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.chatbot import ANSDChatbot  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
GOLD = BASE / "data" / "eval" / "gold.jsonl"
REPORT_JSON = BASE / "data" / "eval" / "report.json"
REPORT_MD = BASE.parent / "docs" / "EVALUATION.md"


def _fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).lower())
                if unicodedata.category(c) != "Mn")
    return s


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "—"


def check(item: dict, r) -> tuple[bool, list[str]]:
    """Retourne (succès, raisons d'échec)."""
    fails = []
    ans_fold = _fold(r.answer or "")
    is_refusal = (r.guardrail in ("off_topic", "injection", "political")
                  or (r.route in ("-", "", None) and r.guardrail not in ("ok", None)))

    if item.get("refusal"):
        if not is_refusal:
            fails.append(f"attendu refus, obtenu route={r.route} guard={r.guardrail}")
        return (not fails), fails

    if "route" in item and r.route != item["route"]:
        fails.append(f"route {r.route} != {item['route']}")
    if "guard" in item and r.guardrail != item["guard"]:
        fails.append(f"guard {r.guardrail} != {item['guard']}")
    for sub in item.get("contains", []):
        if _fold(sub) not in ans_fold:
            fails.append(f"manque «{sub}»")
    for sub in item.get("not_contains", []):
        if _fold(sub) in ans_fold:
            fails.append(f"contient interdit «{sub}»")
    if "link_contains" in item:
        urls = _fold(" ".join(l.get("url", "") for l in (r.links or [])))
        if _fold(item["link_contains"]) not in urls:
            fails.append(f"aucun lien contenant «{item['link_contains']}»")
    if "data_rows" in item:
        n = len(r.data["rows"]) if r.data and "rows" in r.data else 0
        if n != item["data_rows"]:
            fails.append(f"{n} lignes != {item['data_rows']}")
    return (not fails), fails


def main() -> int:
    items = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    bot = ANSDChatbot()
    llm_actif = bot.use_llm_aux  # correction fautes / réécriture disponibles ?

    results, latences = [], []
    for it in items:
        sid = f"eval-{it['id']}"
        for prev in it.get("context", []):
            bot.ask(prev, session_id=sid)
        t0 = time.perf_counter()
        r = bot.ask(it["q"], session_id=sid)
        dt = (time.perf_counter() - t0) * 1000
        latences.append(dt)
        ok, why = check(it, r)
        results.append({"id": it["id"], "cap": it.get("cap", "?"),
                        "needs_llm": it.get("needs_llm", False),
                        "ok": ok, "why": why, "route": r.route,
                        "guard": r.guardrail, "latence_ms": round(dt)})

    # agrégats
    core = [x for x in results if not x["needs_llm"]]
    llm_dep = [x for x in results if x["needs_llm"]]
    core_ok = sum(x["ok"] for x in core)
    safety = [x for x in results if x["cap"] == "securite"]
    safety_ok = sum(x["ok"] for x in safety)
    rag_items = [x for x in results if x["route"] in ("RAG", "HYBRID")]
    faithful = sum(1 for x in rag_items if x["guard"] != "unfaithful")
    lat_sorted = sorted(latences)
    p50 = lat_sorted[len(lat_sorted) // 2]
    p95 = lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)]

    # par capacité
    caps: dict[str, list] = {}
    for x in core:
        caps.setdefault(x["cap"], []).append(x)

    summary = {
        "n_total": len(results),
        "core_ok": core_ok, "core_total": len(core),
        "core_rate": round(100.0 * core_ok / len(core), 1) if core else 0,
        "safety_ok": safety_ok, "safety_total": len(safety),
        "faithful_ok": faithful, "rag_total": len(rag_items),
        "llm_dep_ok": sum(x["ok"] for x in llm_dep), "llm_dep_total": len(llm_dep),
        "llm_actif": llm_actif,
        "latence_p50_ms": round(p50), "latence_p95_ms": round(p95),
        "latence_max_ms": round(max(latences)),
        "par_capacite": {c: {"ok": sum(x["ok"] for x in xs), "total": len(xs)}
                         for c, xs in caps.items()},
    }

    # console
    print("=" * 64)
    print("ÉVALUATION DU CHATBOT ANSD —", "LLM actif" if llm_actif else "mode déterministe (démo)")
    print("=" * 64)
    for x in results:
        flag = "OK " if x["ok"] else "ECH"
        skip = " (needs_llm)" if x["needs_llm"] and not llm_actif else ""
        print(f"  [{flag}] {x['id']:<20} {x['cap']:<14} {x['latence_ms']:>4}ms{skip}"
              + ("" if x["ok"] else "  -> " + " ; ".join(x["why"])))
    print("-" * 64)
    print(f"Exactitude (déterministe) : {core_ok}/{len(core)} = {summary['core_rate']}%")
    print(f"Sécurité (refus)          : {safety_ok}/{len(safety)}")
    print(f"Fidélité (RAG/HYBRID)     : {faithful}/{len(rag_items)}")
    print(f"Robustesse LLM            : {summary['llm_dep_ok']}/{summary['llm_dep_total']}"
          + ("" if llm_actif else " (LLM inactif : indicatif)"))
    print(f"Latence p50 / p95 / max   : {summary['latence_p50_ms']} / "
          f"{summary['latence_p95_ms']} / {summary['latence_max_ms']} ms")

    REPORT_JSON.write_text(json.dumps({"summary": summary, "results": results},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(summary, results, llm_actif)
    print(f"\nRapports : {REPORT_JSON}\n           {REPORT_MD}")

    # garde-barrière CI : régression bloquante sur l'exactitude déterministe ou
    # la sécurité (les cas needs_llm ne bloquent pas hors fournisseur rapide).
    regression = (core_ok < len(core)) or (safety_ok < len(safety))
    if regression:
        print("\n[ÉCHEC] régression détectée (exactitude déterministe ou sécurité).")
    return 1 if regression else 0


def _write_md(s: dict, results: list, llm_actif: bool) -> None:
    lignes = [
        "# Évaluation du Chatbot ANSD (protocole reproductible)",
        "",
        f"> Généré par `python scripts/evaluate.py` sur `data/eval/gold.jsonl` "
        f"({s['n_total']} cas). Jeu de test défini **indépendamment** du système "
        "(faits officiels + comportement attendu). "
        + ("LLM actif." if llm_actif else "Mode déterministe (démo, hors ligne)."),
        "",
        "## Synthèse",
        "",
        "| Dimension | Résultat |",
        "|---|---|",
        f"| Exactitude fonctionnelle (déterministe) | **{s['core_ok']}/{s['core_total']} "
        f"= {s['core_rate']}%** |",
        f"| Sécurité — refus hors périmètre / injection | **{s['safety_ok']}/{s['safety_total']}** |",
        f"| Fidélité — rail factuel sur RAG/HYBRID (aucun « unfaithful ») | "
        f"**{s['faithful_ok']}/{s['rag_total']}** |",
        f"| Robustesse aux fautes (dépend du LLM) | {s['llm_dep_ok']}/{s['llm_dep_total']}"
        + ("" if llm_actif else " — *LLM inactif : indicatif*") + " |",
        f"| Latence p50 / p95 / max | **{s['latence_p50_ms']} / {s['latence_p95_ms']} / "
        f"{s['latence_max_ms']} ms** |",
        "",
        "## Par capacité",
        "",
        "| Capacité | Réussite |",
        "|---|---|",
    ]
    for cap, v in sorted(s["par_capacite"].items()):
        lignes.append(f"| {cap} | {v['ok']}/{v['total']} |")
    lignes += ["", "## Détail par cas", "",
               "| Cas | Capacité | Route | Latence | Verdict |",
               "|---|---|---|---|---|"]
    for x in results:
        verdict = "✅" if x["ok"] else "❌ " + " ; ".join(x["why"])
        lignes.append(f"| {x['id']} | {x['cap']} | {x['route']} | {x['latence_ms']} ms | {verdict} |")
    lignes += ["", "## Lecture",
               "",
               "- **Exactitude** mesurée sur des voies déterministes (SQL/CATALOG/NAV/"
               "RAG ancré) : reproductible sans réseau.",
               "- **Sécurité** : les questions hors périmètre, politiques ou d'injection "
               "doivent être refusées (garde-fou d'entrée).",
               "- **Fidélité** : le rail factuel vérifie que les chiffres d'une réponse "
               "RAG sont couverts par les passages cités (aucun verdict « unfaithful »).",
               "- **Robustesse aux fautes de frappe** : nécessite un fournisseur LLM "
               "rapide (correction en amont) ; en démo hors ligne, ces cas sont indicatifs.",
               ""]
    REPORT_MD.write_text("\n".join(lignes), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
