"""Analyse un rapport commercial mensuel reel (LECTURE SEULE) avec les regles de config :
statistiques par jour, controle des totaux, anomalies, et (option) export des libelles
clients a faire correspondre aux codes Sage.

Usage : python tools/analyser_rapport.py RAPPORT.xlsx [--config config.json]
                 [--feuilles 01,02] [--libelles sortie.xlsx] [--detail]"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook  # noqa: E402

from gtc_compta.config import load_config  # noqa: E402
from gtc_compta.excel.report_parser import ParseurRapport  # noqa: E402
from gtc_compta.text import normaliser  # noqa: E402


def analyser(path, cfg, feuilles=None):
    wb = load_workbook(path, read_only=True, data_only=True)
    noms = feuilles or [n for n in wb.sheetnames if n.isdigit()]
    out = {}
    for n in noms:
        rows = [list(r) for r in wb[n].iter_rows(values_only=True)]
        out[n] = ParseurRapport(cfg["rapport"], {}).analyser(rows, n, cfg["agence"], None)
    wb.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rapport")
    ap.add_argument("--config")
    ap.add_argument("--feuilles")
    ap.add_argument("--libelles")
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config) if a.config else load_config("/nonexistent.json")
    res = analyser(a.rapport, cfg, a.feuilles.split(",") if a.feuilles else None)
    tot = Counter()
    anos = Counter()
    ecarts_totaux = []
    print(f"{'J':>3} {'date':>10} {'fact':>5} {'avoir':>5} {'acpt':>5} {'recus':>5} {'BCseul':>6} {'annul':>5} "
          f"{'nul':>4} {'excl':>4} {'ano':>4}  total rapport=lignes / aucun montant oublie")
    for n, r in res.items():
        s = r.stats
        for k in ("factures", "avoirs", "acomptes", "reglements", "bc_seuls_ignores", "annulees",
                  "factures_montant_nul", "hors_perimetre_exclus"):
            tot[k] += s[k]
        for x in r.anomalies:
            if "sans correspondance" not in x.motif:
                anos[(x.gravite, x.motif.split(":")[0][:70])] += 1
        ctl = s["controle_totaux"]
        ok = all(v["rapport"] is None or v["rapport"] == v["lignes"] for v in ctl.values())
        coh = all(v["ecart_non_explique"] == 0 for v in ctl.values())
        if not ok or not coh:
            ecarts_totaux.append((n, ctl))
        nb_ano = sum(1 for x in r.anomalies if "sans correspondance" not in x.motif)
        print(f"{n:>3} {str(r.date_rapport):>10} {s['factures']:>5} {s['avoirs']:>5} {s['acomptes']:>5} "
              f"{s['reglements']:>5} {s['bc_seuls_ignores']:>6} {s['annulees']:>5} {s['factures_montant_nul']:>4} "
              f"{s['hors_perimetre_exclus']:>4} {nb_ano:>4}  {'OK' if ok else 'ECART'} / "
              f"{'coherent' if coh else 'A EXPLIQUER'}")
    print("\nTOTAL MOIS :", dict(tot))
    print("\nAnomalies (hors correspondances clients) :")
    for (g, m), c in anos.most_common():
        print(f"  {c:>4} x {g:<13} {m}")
    print("\nJours avec ecart de totaux ou montants non expliques :", len(ecarts_totaux))
    for n, ctl in ecarts_totaux:
        print("  ", n, ctl)
    if a.detail:
        for n, r in res.items():
            for x in r.anomalies:
                if x.gravite != "INFO" and "sans correspondance" not in x.motif:
                    print(f"  [{n}:{x.ligne}] {x.gravite} {x.motif} | {x.contenu[:90]}")
    if a.libelles:
        from openpyxl import Workbook
        lib = Counter()
        exemples = {}
        for n, r in res.items():
            for m in r.mouvements:
                lib[normaliser(m.client_libelle)] += 1
                exemples.setdefault(normaliser(m.client_libelle), (m.client_libelle, n, m.reference_piece))
        wb = Workbook()
        ws = wb.active
        ws.title = "CORRESPONDANCES"
        ws.append(["libelle_rapport", "code_tiers_sage", "occurrences", "exemple_feuille", "exemple_piece"])
        for k, c in lib.most_common():
            o, f, p = exemples[k]
            ws.append([o, None, c, f, p])
        ws.column_dimensions["A"].width = 45
        ws.column_dimensions["B"].width = 18
        wb.save(a.libelles)
        print(f"\n{len(lib)} libelles clients exportes dans {a.libelles} (colonne B a completer)")


if __name__ == "__main__":
    main()
