"""Etat comparatif de tous les rapports mensuels fournis + analyse mois par mois (lecture seule).

Produit un classeur Excel :
- une feuille par mois au modele RECAP (vente comptant, vente a credit, total ventes, recouvrements,
  recette totale = recouvrements + vente comptant ; TOTAL M, M-1, EVOLUTION, N-1, ECART) et, si Sage est
  configure (--config avec sage.mode = "sql"), le rapprochement quotidien des ventes CR / Sage ;
- ANALYSE_MENSUELLE : volumes et erreurs de CR de chaque mois ;
- CONTROLE_RECAP : ecarts entre la feuille RECAP du rapport et les feuilles journalieres, avec la formule
  RECAP en cause.

Usage : python tools/etat_comparatif.py "04 RC AVR.xlsx" ... "10 RC OCT.xlsx" --sortie ETAT_COMPARATIF.xlsx
        [--config config.json]
"""
import argparse
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from gtc_compta.config import DEFAULTS, load_config  # noqa: E402
from gtc_compta.db import Database  # noqa: E402
from gtc_compta.excel.rapport_mensuel import formules_recap, lire_recap, mois_du_fichier  # noqa: E402
from gtc_compta.excel.report_parser import ParseurRapport  # noqa: E402
from gtc_compta.services import etat_comparatif as ec  # noqa: E402
from gtc_compta.services.auth import Utilisateur  # noqa: E402

RECAP_COLS = {"vente_comptant": "VENTE COMPTANT", "vente_credit": "VENTE A TERME", "total_ventes": "TOTAL VENTES",
              "recouvrements": "RECOUVREMENTS", "acompte": "ACOMPTE"}
COL_LETTRE = {"ACOMPTE": 2, "VENTE COMPTANT": 3, "VENTE A TERME": 4, "TOTAL VENTES": 5, "RECOUVREMENTS": 6}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rapports", nargs="+")
    ap.add_argument("--sortie", default="ETAT_COMPARATIF.xlsx")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config) if a.config else dict(DEFAULTS, _path="")
    regles, agence = cfg["rapport"], cfg["agence"]
    mode = cfg.get("etat_comparatif", {}).get("recette", "comptant+recouvrement")
    db = Database(Path(tempfile.mkdtemp()) / "etat.sqlite3")
    u = Utilisateur("etat", "Etat comparatif", "comptable_controleur")
    analyse, controle_recap, mois_liste = [], [], []
    for path in a.rapports:
        wb = load_workbook(path, read_only=True, data_only=True)
        mois, annee = mois_du_fichier(path, wb)
        recap = lire_recap(wb)
        formules = formules_recap(path)
        st = Counter()
        codes = Counter()
        jours_actifs = 0
        for f in [x for x in wb.sheetnames if x.isdigit()]:
            try:
                d = date(annee, mois, int(f))
            except (ValueError, TypeError):
                continue
            res = ParseurRapport(regles, {}).analyser([list(r) for r in wb[f].iter_rows(values_only=True)], f, agence, d)
            v = ec.valeurs_jour(res, regles, mode)
            ec.enregistrer_jour(db, v, source=Path(path).name)
            if v["total_ventes"] or v["recouvrements"]:
                jours_actifs += 1
            for k in ("factures", "avoirs", "acomptes", "reglements", "annulations_recus", "bc_seuls_ignores",
                      "annulees", "factures_montant_nul"):
                st[k] += res.stats.get(k, 0)
            for an in res.anomalies:
                if an.code != "CLIENT_SANS_CORRESPONDANCE":
                    codes[an.code] += 1
            r = recap.get(d.isoformat())
            if r:
                for cle, nom in RECAP_COLS.items():
                    val = r.get(nom) or 0
                    if val != v[cle]:
                        fo = formules.get(int(f), {}).get(COL_LETTRE[nom], "")
                        controle_recap.append([Path(path).name, d, nom, v[cle], val, val - v[cle], str(fo)])
        wb.close()
        ec.enregistrer_references_recap(db, agence, annee, mois, path, mode)
        mois_liste.append((annee, mois))
        t = ec.tableau_mois(db, agence, annee, mois)["total_m"]
        analyse.append([f"{ec.NOMS_MOIS[mois - 1]} {annee}", jours_actifs, t["vente_comptant"], t["vente_credit"],
                        t["total_ventes"], t["recouvrements"], t["recette"], st["factures"], st["avoirs"],
                        st["reglements"], st["annulations_recus"], st["annulees"],
                        sum(n for c, n in codes.items() if c not in ("FACTURE_MONTANT_NUL", "BC_SANS_NUMERO_C",
                                                                     "BC_SANS_NUMERO")),
                        ", ".join(f"{c} x{n}" for c, n in codes.most_common()
                                  if c not in ("FACTURE_MONTANT_NUL", "BC_SANS_NUMERO_C", "BC_SANS_NUMERO"))])
    if cfg.get("sage", {}).get("mode") == "sql":
        from gtc_compta.sage import creer_adaptateur
        sage = creer_adaptateur(cfg)
        for annee, mois in mois_liste:
            ec.rapprocher_ventes_mois(db, u, sage, agence, annee, mois)
    ec.exporter_excel(db, agence, mois_liste, a.sortie, cfg.get("societe", ""))
    wb = load_workbook(a.sortie)
    gras, bleu = Font(bold=True), PatternFill("solid", fgColor="DDEBF7")
    ws = wb.create_sheet("ANALYSE_MENSUELLE", 0)
    ws.append(["Mois", "Jours actifs", "Vente comptant", "Vente a credit", "Total ventes", "Recouvrements",
               "Recette totale", "Factures", "Avoirs", "Recus", "Recus negatifs", "Lignes ANNULEE",
               "Erreurs de CR", "Detail des erreurs (codes du catalogue)"])
    for r in analyse:
        ws.append(r)
    ws.append(["TOTAL", sum(r[1] for r in analyse)] + [sum(r[k] for r in analyse) for k in range(2, 13)])
    ws2 = wb.create_sheet("CONTROLE_RECAP", 1)
    ws2.append(["Rapport", "Date", "Colonne RECAP", "Feuille du jour", "RECAP", "Ecart", "Formule RECAP"])
    for r in controle_recap:
        ws2.append(r)
    for w in (ws, ws2):
        for c in w[1]:
            c.font, c.fill = gras, bleu
        for row in w.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, int) and abs(c.value) > 999:
                    c.number_format = "# ##0"
                elif isinstance(c.value, date):
                    c.number_format = "DD/MM/YYYY"
    for col, larg in zip("ABCDEFGHIJKLMN", (16, 10, 15, 16, 16, 16, 16, 9, 8, 8, 9, 9, 10, 90)):
        ws.column_dimensions[col].width = larg
    for col, larg in zip("ABCDEFG", (18, 12, 16, 16, 16, 14, 24)):
        ws2.column_dimensions[col].width = larg
    wb.save(a.sortie)
    for r in analyse:
        print(" | ".join(str(x) for x in r[:13]))
    print(f"Ecarts RECAP : {len(controle_recap)} ; classeur : {a.sortie}")


if __name__ == "__main__":
    main()
