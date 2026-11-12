"""Genere les donnees de DEMONSTRATION (fictives, anonymes) :
- demo/RC_DEMO_SYNTHETIQUE.xlsx : rapport commercial synthetique (structure du cahier
  des charges, NON verifiee sur le vrai "10 RC OCT.xlsx") ;
- demo/sage_demo.json : base Sage fictive pour l'adaptateur de demonstration.
Usage : python tools/make_demo.py
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]


def _n(v):
    if isinstance(v, str):
        return int(v.replace(" ", ""))
    return v or 0


def feuille(ws, jour, docs, recus, decalage=0):
    """Reproduit la STRUCTURE du rapport reel (10 RC OCT.xlsx) avec des donnees fictives.
    Colonnes : A folio, B BC, C piece, D client, E reference, F ACOMPTE (ENTREE), G BP,
    H facture COMPTANT, I facture VAT (vente a terme)."""
    from datetime import datetime
    ws.append(["GLOBAL TRADE COMPANY SARL (DONNEES FICTIVES)"])
    ws.append([])
    ws.append(["AGENCE DE BERTOUA"])
    ws.append([datetime(2026, 10, int(jour))])
    ws.append(["FOLIO", "N° PIECES", None, "NOMS ET PRENOMS", "REFRENCES", "MONTANT"])
    ws.append([None, None, None, None, None, "BON DE COMMANDE", None, "FACTURE"])
    ws.append([None, None, None, None, None, "ENTREE", "BP", "COMPTANT", "VAT"])
    ws.append([])
    for i, d in enumerate(docs, 1):
        ws.append([i] + d)
    tot = [sum(_n(d[k]) for d in docs) for k in (4, 5, 6, 7)]
    ws.append([])
    ws.append([None, None, None, "TOTAL VENTES", None] + tot)
    ws.append([None, None, None, None, None, None, "TOTAL VENTES", None, tot[2] + tot[3]])
    for _ in range(decalage):
        ws.append([])
    ws.append(["REÇUS DE VERSEMENTS "])
    ws.append([None, None, "N°PIECES", "NOMS ET PRENOMS", None, "RECOUVREMENTS", None, "AUTRES"])
    ws.append([])
    for i, r in enumerate(recus, 1):
        ws.append([None, i] + r[:2] + [None, r[2]])
    ws.append([])
    ws.append([None, None, None, "TOTAL DE VERSEMENTS", None, sum(r[2] for r in recus), None, None, 0])
    ws.append([None, None, None, "TOTAL RECETTES", None, tot[0] + sum(r[2] for r in recus)])
    ws.append([None, None, None, "REPORT", None, 10000])
    ws.append([None, None, None, "VERSEMENT CAISSE CENTRALE", None, None, None, 455000])
    ws.append([1, None, "BTF 2651", "VERSEMENT CAISSE RECETTE", None, None, None, 70000])
    ws.append([None, None, None, "SOLDE", None, None, None, 10000])
    ws.append([])
    ws.append([None, None, "RESPONSABLE DES VENTES", None, "COMMERCIAL", None, None, None, "LE CAISSIER"])


def rapport(path):
    wb = Workbook()
    wb.remove(wb.active)
    feuille(wb.create_sheet("01"), "01", [
        ["BC0101", "BCCB0101", "ETS ALPHA", "EN COMPTE", None, 500000, None, None],          # BC seul (BP)
        ["BC0101", "FACB0201", "ETS ALPHA", "EN COMPTE", None, 500000, None, 500000],        # BC + facture a terme
        ["BC0102", "FACB0301", "QUINCAILLERIE BETA", "COMPTANT", 120000, None, 120000, None],# acompte + facture comptant
        ["BC0103", "FACB0202", "CLIENTS DETAILS BTA", "M. NDONGO", 35000, None, 35000, None],# compte collectif
        ["BC0099", "FACB0203", "SOCIETE GAMMA", "EN COMPTE", None, None, None, 200000],     # livraison partielle
        [None, "FRCB0001", "ETS ALPHA", "EN COMPTE", None, None, None, -50000],              # avoir / retour
        [None, "FACB0204", "NOUVEAU CLIENT X", "EN COMPTE", None, None, None, 75000],        # sans correspondance
        ["BC0105", "FACB0205", "ETS ALPHA", "ANNULEE", 0, None, 0, None],                    # annulee
        ["BC0106", "FACB0206", "COMPTE DE LIAISON", "REUNION DIRECTION", 2700, None, 2700, None],  # liaison
    ], [
        ["7RCB0451", "ETS ALPHA", 300000],
    ])
    feuille(wb.create_sheet("02"), "02", [
        [None, "FACB0210", "DELTA SARL", "EN COMPTE", None, None, None, "1 250 000"],
        [None, "FACB0211", "SOCIETE GAMMA", "EN COMPTE", None, None, 90000, 95000],          # H/I incoherents
        ["BC0300", "BCCB0300", "SOCIETE GAMMA", "EN COMPTE", None, 40000, None, 40000],      # n° de BC + montant facture
    ], [
        ["7RCB0460", "SOCIETE GAMMA", 150000],
        ["7RCB0461", "DELTA SARL", 250000],
        ["7RCB0462", "DELTA SARL", -5000],                                                   # recu negatif
    ], decalage=9)
    ws = wb.create_sheet("RECAP")
    ws.append(["RECAPITULATIF (fictif)"])
    wb.save(path)


SAGE = {
    "_avertissement": "Donnees Sage FICTIVES pour demonstration et tests uniquement.",
    "clients": [
        {"ct_num": "CL001", "intitule": "ETS ALPHA", "telephone": "699000001", "ville": "BERTOUA", "encours_autorise": 2000000},
        {"ct_num": "CL002", "intitule": "QUINCAILLERIE BETA", "telephone": "677000002", "ville": "BERTOUA", "encours_autorise": 500000},
        {"ct_num": "CL003", "intitule": "SOCIETE GAMMA", "telephone": "655000003", "ville": "BATOURI", "encours_autorise": 1000000},
        {"ct_num": "CL004", "intitule": "DELTA SARL", "telephone": "", "ville": "BELABO", "encours_autorise": 0},
        {"ct_num": "CL099", "intitule": "CLIENTS DETAILS BTA", "telephone": "", "ville": "BERTOUA", "encours_autorise": None},
    ],
    "ecritures": [
        {"ec_no": 1, "ct_num": "CL001", "journal": "RAN", "date_ecriture": "2026-09-30", "numero_piece": "RAN", "reference_piece": "", "libelle": "Report a nouveau", "sens": "D", "montant": 1400000},
        {"ec_no": 2, "ct_num": "CL002", "journal": "RAN", "date_ecriture": "2026-09-30", "numero_piece": "RAN", "reference_piece": "", "libelle": "Report a nouveau", "sens": "D", "montant": 0},
        {"ec_no": 3, "ct_num": "CL003", "journal": "RAN", "date_ecriture": "2026-09-30", "numero_piece": "RAN", "reference_piece": "", "libelle": "Report a nouveau", "sens": "D", "montant": 640000},
        {"ec_no": 4, "ct_num": "CL004", "journal": "RAN", "date_ecriture": "2026-09-30", "numero_piece": "RAN", "reference_piece": "", "libelle": "Report a nouveau", "sens": "C", "montant": 100000},
        {"ec_no": 5, "ct_num": "CL099", "journal": "RAN", "date_ecriture": "2026-09-30", "numero_piece": "RAN", "reference_piece": "", "libelle": "Report a nouveau", "sens": "D", "montant": 0},
        {"ec_no": 10, "ct_num": "CL001", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0201", "reference_piece": "FACB0201", "libelle": "Facture FACB0201", "sens": "D", "montant": 500000, "date_echeance": "2026-10-31"},
        {"ec_no": 11, "ct_num": "CL001", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FRCB0001", "reference_piece": "FRCB0001", "libelle": "Avoir retour", "sens": "C", "montant": 50000},
        {"ec_no": 12, "ct_num": "CL001", "journal": "CAI", "date_ecriture": "2026-10-01", "numero_piece": "7RCB0451", "reference_piece": "7RCB0451", "libelle": "Reglement especes", "sens": "C", "montant": 300000},
        {"ec_no": 13, "ct_num": "CL002", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0301", "reference_piece": "FACB0301", "libelle": "Facture FACB0301", "sens": "D", "montant": 120000},
        {"ec_no": 14, "ct_num": "CL002", "journal": "CAI", "date_ecriture": "2026-10-01", "numero_piece": "RC0452", "reference_piece": "BC0102", "libelle": "Acompte sur commande BC0102", "sens": "C", "montant": 120000},
        {"ec_no": 15, "ct_num": "CL003", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0203", "reference_piece": "FACB0203", "libelle": "Facture FACB0203", "sens": "D", "montant": 200000, "date_echeance": "2026-10-15"},
        {"ec_no": 16, "ct_num": "CL003", "journal": "OD", "date_ecriture": "2026-10-01", "numero_piece": "OD0007", "reference_piece": "", "libelle": "Frais de transport refactures", "sens": "D", "montant": 25000},
        {"ec_no": 17, "ct_num": "CL099", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0202", "reference_piece": "FACB0202", "libelle": "Facture detail", "sens": "D", "montant": 35000},
        {"ec_no": 18, "ct_num": "CL099", "journal": "CAI", "date_ecriture": "2026-10-01", "numero_piece": "RC0453", "reference_piece": "", "libelle": "Acompte detail", "sens": "C", "montant": 35000},
    ],
    "bons_commande": [
        {"piece": "BCCB0101", "ct_num": "CL001", "date_doc": "2026-10-01", "montant_ttc": 500000},
        {"piece": "BCCB0150", "ct_num": "CL002", "date_doc": "2026-10-02", "montant_ttc": 200000},
        {"piece": "BCCB0160", "ct_num": "CL004", "date_doc": "2026-10-02", "montant_ttc": 300000},
    ],
    "solvabilite": {
        "BCCB0101": {"plafond": 2000000, "risque_sage": 2300000, "bc_deja_inclus": True,
                     "factures_echues": [], "details": {"note": "fictif"}},
        "BCCB0150": {"plafond": 500000, "risque_sage": 120000, "bc_deja_inclus": False,
                     "factures_echues": [{"piece": "FVCB0100", "montant": 80000, "jours_retard": 12}]},
    },
}


if __name__ == "__main__":
    out = ROOT / "demo"
    out.mkdir(exist_ok=True)
    rapport(out / "RC_DEMO_SYNTHETIQUE.xlsx")
    (out / "sage_demo.json").write_text(json.dumps(SAGE, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Donnees de demonstration generees dans", out, file=sys.stderr)
