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
HDR = ["N°", "BC", "N° DOCUMENT", "CLIENT", "REFERENCE", "BC COMPTANT", "BC EN COMPTE",
       "FACT. COMPTANT", "FACT. EN COMPTE"]


def feuille(ws, jour, docs, recus, decalage=0):
    ws.append(["GLOBAL TRADE COMPANY SARL - AGENCE DE BERTOUA (DONNEES FICTIVES)"])
    ws.append([f"RAPPORT COMMERCIAL DU {jour}/10/2026"])
    ws.append([])
    ws.append(["", "", "DOCUMENTS COMMERCIAUX"])
    ws.append(HDR)
    for i, d in enumerate(docs, 1):
        ws.append([i] + d)
    ws.append(["", "", "", "TOTAL", "", None, None, None, None])
    for _ in range(3 + decalage):
        ws.append([])
    ws.append(["", "", "BONS DE LIVRAISON"])
    ws.append(["", "", "BLCB0001", "ETS ALPHA", "EN COMPTE", 80000, None, None, None])
    for _ in range(4):
        ws.append([])
    ws.append(["", "", "REÇUS DE VERSEMENTS"])
    ws.append(["N°", "", "N° RECU", "CLIENT", "REFERENCE", "MONTANT"])
    for i, r in enumerate(recus, 1):
        ws.append([i, ""] + r)
    ws.append(["", "", "", "VERSEMENT CAISSE CENTRALE", "", 455000])
    ws.append(["", "", "", "TOTAL", "", sum(r[3] for r in recus if isinstance(r[3], int))])
    ws.append([])
    ws.append(["", "", "DEPENSES"])
    ws.append(["", "", "", "Carburant vehicule", "", 15000])


def rapport(path):
    wb = Workbook()
    wb.remove(wb.active)
    feuille(wb.create_sheet("01"), "01", [
        ["", "BCCB0101", "ETS ALPHA", "EN COMPTE", None, 500000, None, None],          # BC seul
        ["BC0101", "FACB0201", "ETS ALPHA", "EN COMPTE", None, 500000, None, 500000],    # BC + facture
        ["", "FVCB0301", "QUINCAILLERIE BETA", "COMPTANT", None, None, 120000, None],   # facture directe
        ["", "FACB0202", "CLIENTS DETAILS BTA", "M. NDONGO", None, None, 35000, None],  # compte collectif
        ["BC0099", "FACB0203", "SOCIETE GAMMA", "EN COMPTE", None, None, None, 200000], # livraison partielle
        ["", "FRCB0001", "ETS ALPHA", "EN COMPTE", None, None, None, -50000],          # avoir / retour
        ["", "FACB0204", "NOUVEAU CLIENT X", "EN COMPTE", None, None, None, 75000],     # sans correspondance
    ], [
        ["7RCB0451", "ETS ALPHA", "ESPECES", 300000],
        ["RCB0452", "QUINCAILLERIE BETA", "", 120000],
        ["7RCB0453", "CLIENTS DETAILS BTA", "M. NDONGO", 35000],
    ])
    feuille(wb.create_sheet("02"), "02", [
        ["", "FACB0210", "DELTA SARL", "EN COMPTE", None, None, None, "1 250 000"],
        ["", "FACB0211", "SOCIETE GAMMA", "EN COMPTE", None, None, 90000, 95000],      # H/I incoherents
    ], [
        ["7RCB0460", "SOCIETE GAMMA", "CHEQUE", 150000],
        ["7RCB0461", "DELTA SARL", "VIREMENT", 250000],
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
        {"ec_no": 13, "ct_num": "CL002", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FVCB0301", "reference_piece": "FVCB0301", "libelle": "Facture FVCB0301", "sens": "D", "montant": 120000},
        {"ec_no": 14, "ct_num": "CL002", "journal": "CAI", "date_ecriture": "2026-10-01", "numero_piece": "RCB0452", "reference_piece": "RCB0452", "libelle": "Reglement", "sens": "C", "montant": 120000},
        {"ec_no": 15, "ct_num": "CL003", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0203", "reference_piece": "FACB0203", "libelle": "Facture FACB0203", "sens": "D", "montant": 200000, "date_echeance": "2026-10-15"},
        {"ec_no": 16, "ct_num": "CL003", "journal": "OD", "date_ecriture": "2026-10-01", "numero_piece": "OD0007", "reference_piece": "", "libelle": "Frais de transport refactures", "sens": "D", "montant": 25000},
        {"ec_no": 17, "ct_num": "CL099", "journal": "VTE", "date_ecriture": "2026-10-01", "numero_piece": "FACB0202", "reference_piece": "FACB0202", "libelle": "Facture detail", "sens": "D", "montant": 35000},
        {"ec_no": 18, "ct_num": "CL099", "journal": "CAI", "date_ecriture": "2026-10-01", "numero_piece": "7RCB0453", "reference_piece": "7RCB0453", "libelle": "Reglement detail", "sens": "C", "montant": 35000},
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
