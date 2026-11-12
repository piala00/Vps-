"""Verification de TOUS les rapports mensuels fournis (lecture seule), avec le traitement reel de
l'application, dans l'ordre chronologique : controle des totaux de chaque jour, comparaison avec
la feuille RECAP, anomalies, registre des BC et factures comptant sans acompte, recus negatifs,
numeros de pieces en double entre jours / mois. Produit un classeur Excel de constats.

Usage : python tools/verifier_mois.py "09 RC SEPT.xlsx" "10 RC OCT.xlsx" ... --sortie VERIFICATION.xlsx
NB : faute de codes Sage, chaque libelle client distinct est traite comme un compte (deux orthographes
d'un meme client apparaissent donc comme deux comptes)."""
import argparse
import copy
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from gtc_compta.config import DEFAULTS  # noqa: E402
from gtc_compta.db import Database  # noqa: E402
from gtc_compta.excel.preparation import bons_export, lignes_export  # noqa: E402
from gtc_compta.excel.report_parser import ParseurRapport  # noqa: E402
from gtc_compta.sage.base import SageClient  # noqa: E402
from gtc_compta.sage.fake import FakeSageAdapter  # noqa: E402
from gtc_compta.services import clients as sc, imports  # noqa: E402
from gtc_compta.services.auth import Utilisateur  # noqa: E402
from gtc_compta.text import normaliser  # noqa: E402

COLS_RECAP = {"F": "ACOMPTE", "H": "VENTE COMPTANT", "I": "VENTE A TERME", "R": "RECOUVREMENTS"}


def total_ligne(rows, libelle, col):
    """Montant de la premiere ligne dont B..E contient le libelle (ligne TOTAL du rapport)."""
    idx = "ABCDEFGHI".index(col)
    for r in rows:
        txt = normaliser(" ".join(str(v) for v in r[1:5] if v is not None))
        if libelle in txt and len(r) > idx:
            return r[idx] if isinstance(r[idx], (int, float)) else 0
    return None


def lire_recap(wb):
    if "RECAP" not in wb.sheetnames:
        return {}
    out = {}
    rows = list(wb["RECAP"].iter_rows(values_only=True))
    entete = next((i for i, r in enumerate(rows) if r and r[0] and "DATE" in normaliser(r[0])), None)
    if entete is None:
        return {}
    noms = [normaliser(c) if c else "" for c in rows[entete]]
    for r in rows[entete + 1:]:
        if r and hasattr(r[0], "date"):
            out[r[0].date().isoformat()] = {n: r[k] for k, n in enumerate(noms) if n}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rapports", nargs="+")
    ap.add_argument("--sortie", default="VERIFICATION_RAPPORTS.xlsx")
    a = ap.parse_args()
    cfg = copy.deepcopy(DEFAULTS)
    regles = cfg["rapport"]
    jours, recap_ecarts, synthese = [], [], []
    for path in a.rapports:
        wb = load_workbook(path, read_only=True, data_only=True)
        recap = lire_recap(wb)
        nb = 0
        for f in [x for x in wb.sheetnames if x.isdigit()]:
            rows = [list(r) for r in wb[f].iter_rows(values_only=True)]
            res = ParseurRapport(regles, {}).analyser(rows, f, cfg["agence"], None)
            if res.date_rapport is None:
                continue
            jours.append((Path(path).name, f, res))
            nb += 1
            d = res.date_rapport.isoformat()
            if d in recap:
                ctl = res.stats["controle_totaux"]
                feuille = {"F": total_ligne(rows, "TOTAL VENTES", "F") or 0,
                           "H": (ctl.get("documents_H") or {}).get("rapport") or 0,
                           "I": (ctl.get("documents_I") or {}).get("rapport") or 0,
                           "R": (ctl.get("recus_F") or {}).get("rapport") or 0}
                for k, nom in COLS_RECAP.items():
                    v = recap[d].get(nom) or 0
                    if feuille[k] != v:
                        recap_ecarts.append((Path(path).name, d, nom, feuille[k], v, v - feuille[k]))
        wb.close()
        synthese.append([Path(path).name, nb])
    jours.sort(key=lambda x: (x[2].date_rapport, x[1]))

    # Base temporaire : chaque libelle distinct = un compte (pas de codes Sage ici)
    noms = sorted({normaliser(m.client_libelle) for _, _, r in jours for m in r.mouvements})
    tmp = Path(tempfile.mkdtemp()) / "verif.sqlite3"
    db = Database(tmp)
    u = Utilisateur("verification", "Verification", "comptable_controleur")
    sage = FakeSageAdapter()
    for k, nom in enumerate(noms):
        sage.ajouter_client(SageClient(f"V{k:04d}", nom))
    sc.synchroniser_clients(db, u, sage, regles["comptes_collectifs"])
    corr = {nom: f"V{k:04d}" for k, nom in enumerate(noms)}
    with db.transaction():
        for nom, ct in corr.items():
            sc.definir_correspondance(db, u, nom, ct)
    controle, anomalies = [], []
    for fic, f, r in jours:
        lignes = lignes_export(r)
        imports.completer_codes(lignes, corr)
        if lignes:
            imports.importer_lot(db, u, lignes, f"{fic}#{f}", "v", bons=bons_export(r))
        else:
            imports.enregistrer_bons(db, bons_export(r))
        s = r.stats
        ok_tot = all(v["rapport"] is None or v["rapport"] == v["lignes"] for v in s["controle_totaux"].values())
        ok_exp = all(v.get("ecart_non_explique", 0) == 0 for v in s["controle_totaux"].values())
        controle.append([fic, f, r.date_rapport.isoformat(), s["factures"], s["avoirs"], s["acomptes"],
                         s["reglements"], s.get("annulations_recus", 0), s["bc_seuls_ignores"], s["annulees"],
                         "OK" if ok_tot else "ECART", "OK" if ok_exp else "NON EXPLIQUE"])
        for x in r.anomalies:
            if x.gravite != "INFO" and "sans correspondance" not in x.motif:
                anomalies.append([fic, f, r.date_rapport.isoformat(), x.ligne, x.gravite, x.motif, x.contenu[:120]])
    lib = {v: k for k, v in corr.items()}
    alertes = [[x["type"], lib.get(x["ct_num"], x["ct_num"]), x["message"]]
               for x in db.query("SELECT * FROM alertes ORDER BY id")]
    recus_neg = [[x["date_piece"], x["reference_piece"], lib.get(x["ct_num"]), x["montant"], x["reference_liee"] or "NON TROUVE"]
                 for x in db.query("SELECT * FROM normalized_movements WHERE nature='REGLEMENT' AND montant<0 ORDER BY date_piece")]
    doublons = [[x["motif"], x["feuille"], x["ligne"], x["contenu_json"][:160]]
                for x in db.query("SELECT r.*, b.fichier AS feuille FROM raw_import_rows r JOIN import_batches b "
                                  "ON b.id=r.batch_id WHERE r.resultat='DEJA_PRESENT' OR r.motif LIKE 'Attention%'")]

    wb = Workbook()
    ws = wb.active
    ws.title = "SYNTHESE"
    t = Counter(x[0] for x in alertes)
    for row in ([["Rapport", "Jours lus"]] + synthese + [[]] + [
            ["Jours verifies", len(controle)],
            ["Jours : total du rapport different des lignes", sum(1 for c in controle if c[10] != "OK")],
            ["Jours : montant non explique", sum(1 for c in controle if c[11] != "OK")],
            ["Ecarts feuilles / RECAP", len(recap_ecarts)],
            ["Anomalies (hors correspondances clients)", len(anomalies)],
            ["Factures comptant sans acompte connu sur leur BC", t.get("FACTURE_COMPTANT_SANS_ACOMPTE", 0)],
            ["Recus negatifs sans recu d'origine", t.get("ANNULATION_RECU_A_VERIFIER", 0)],
            ["Recus negatifs (total)", len(recus_neg)],
            ["Pieces deja presentes / numero reutilise", len(doublons)],
            ]):
        ws.append(row)
    feuilles = [
        ("CONTROLE_JOURS", ["Rapport", "Feuille", "Date", "Factures", "Avoirs", "Acomptes imputes", "Recus",
                            "Recus negatifs", "BC/BL seuls", "Annulees", "Total rapport = lignes",
                            "Montants expliques"], controle),
        ("RECAP", ["Rapport", "Date", "Colonne RECAP", "Feuille du jour", "RECAP", "Ecart"], recap_ecarts),
        ("ANOMALIES", ["Rapport", "Feuille", "Date", "Ligne", "Gravite", "Motif", "Contenu"], anomalies),
        ("FACTURES_COMPTANT", ["Type", "Client (libelle)", "Constat"],
         [x for x in alertes if x[0] == "FACTURE_COMPTANT_SANS_ACOMPTE"]),
        ("RECUS_NEGATIFS", ["Date", "Recu", "Client (libelle)", "Montant", "Recu annule"], recus_neg),
        ("NUMEROS", ["Constat", "Lot", "Ligne", "Contenu"], doublons),
    ]
    fill = PatternFill("solid", fgColor="DDEBF7")
    for nom, ent, data in feuilles:
        w = wb.create_sheet(nom)
        w.append(ent)
        for c in w[1]:
            c.font, c.fill = Font(bold=True), fill
        for r_ in data:
            w.append(list(r_))
        for col, larg in zip("ABCDEFGHIJKL", (20, 14, 14, 14, 14, 60, 60, 12, 12, 12, 14, 14)):
            w.column_dimensions[col].width = larg
    wb.save(a.sortie)
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            print(" | ".join(str(v) for v in row if v is not None))
    print("Classeur :", a.sortie)


if __name__ == "__main__":
    main()
