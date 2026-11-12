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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from gtc_compta.config import DEFAULTS  # noqa: E402
from gtc_compta.db import Database  # noqa: E402
from gtc_compta.excel.preparation import anomalies_export, bons_export, lignes_export  # noqa: E402
from gtc_compta.excel.report_parser import CATALOGUE_ERREURS, ParseurRapport  # noqa: E402
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


def mois_du_fichier(path, wb):
    """Mois du rapport : prefixe du nom de fichier (\"05_RC_MAI\", \"05 RC MAI\"), sinon mois majoritaire des
    dates imprimees. Annee : celle des dates imprimees."""
    import re as _re
    from collections import Counter as _C
    dates = []
    for f in [x for x in wb.sheetnames if x.isdigit()][:31]:
        for r in wb[f].iter_rows(min_row=1, max_row=8, values_only=True):
            v = next((x for x in r[:3] if hasattr(x, "year")), None)
            if v is not None:
                dates.append(v)
                break
    annee = _C(d.year for d in dates).most_common(1)[0][0] if dates else date.today().year
    m = _re.match(r"^(\d{1,2})[ _.-]", Path(path).name)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), annee
    return (_C(d.month for d in dates).most_common(1)[0][0] if dates else None), annee


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
    dates_feuilles = []
    for path in a.rapports:
        wb = load_workbook(path, read_only=True, data_only=True)
        recap = lire_recap(wb)
        mois, annee = mois_du_fichier(path, wb)
        nb = 0
        for f in [x for x in wb.sheetnames if x.isdigit()]:
            rows = [list(r) for r in wb[f].iter_rows(values_only=True)]
            try:
                attendu = date(annee, mois, int(f)) if mois else None
            except ValueError:
                attendu = None          # feuille 31 d'un mois de 30 jours
                import re as _re
                pieces = [r[2] for r in rows if len(r) > 2 and r[2]
                          and _re.match(r"^\d*(FACB|FRCB|FVCB|RCB)", str(r[2]).replace(" ", ""))]
                if pieces:
                    dates_feuilles.append([Path(path).name, f, "", "", f"Feuille hors calendrier contenant "
                                                                        f"{len(pieces)} piece(s) (ex. {pieces[0]})"])
                continue
            res = ParseurRapport(regles, {}).analyser(rows, f, cfg["agence"], attendu)
            if res.date_feuille and attendu and res.date_feuille != attendu:
                dates_feuilles.append([Path(path).name, f, attendu.isoformat(), res.date_feuille.isoformat(),
                                       "Date imprimee (A4) differente de la date de la feuille"])
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
            imports.importer_lot(db, u, lignes, f"{fic}#{f}", "v", bons=bons_export(r),
                                 anomalies=[a for a in anomalies_export(r) if a["code"] != "CLIENT_SANS_CORRESPONDANCE"])
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
    registre = [[x["date_rapport"], x["feuille"], x["ligne"], x["code"], x["gravite"],
                 "OUI" if x["impact_solde"] else "non", x["statut"], x["client_libelle"] or lib.get(x["ct_num"], ""),
                 x["reference"], x["montant"], x["motif"][:200], x["resolution"] or ""]
                for x in db.query("SELECT * FROM anomalies_cr ORDER BY date_rapport, id")]
    libelles = {c: l for _r, c, _i, l in CATALOGUE_ERREURS}
    libelles.update({"PIECE_SAISIE_DEUX_FOIS": "Meme piece saisie a nouveau un autre jour (meme client, meme montant)",
                     "CONFLIT_MONTANT": "Piece deja saisie avec un autre montant",
                     "FACTURE_COMPTANT_SANS_ACOMPTE": "Facture comptant sans acompte connu sur son BC",
                     "REJET_IMPORT": "Ligne rejetee a l'import"})
    par_code = {}
    for x in db.query("SELECT code, impact_solde, statut, COUNT(*) n FROM anomalies_cr GROUP BY code, impact_solde, statut"):
        d = par_code.setdefault(x["code"], {"impact": x["impact_solde"], "total": 0, "ouvertes": 0})
        d["total"] += x["n"]
        d["ouvertes"] += x["n"] if x["statut"] == "OUVERTE" else 0
    catalogue = sorted(([c, libelles.get(c, c), "OUI" if d["impact"] else "non", d["total"], d["ouvertes"]]
                        for c, d in par_code.items()), key=lambda r: (-r[3], r[0]))

    wb = Workbook()
    ws = wb.active
    ws.title = "SYNTHESE"
    t = Counter(x[0] for x in alertes)
    for row in ([["Rapport", "Jours lus"]] + synthese + [[]] + [
            ["Jours verifies", len(controle)],
            ["Jours : total du rapport different des lignes", sum(1 for c in controle if c[10] != "OK")],
            ["Jours : montant non explique", sum(1 for c in controle if c[11] != "OK")],
            ["Ecarts feuilles / RECAP", len(recap_ecarts)],
            ["Feuilles a date imprimee incoherente", len(dates_feuilles)],
            ["Anomalies (hors correspondances clients)", len(anomalies)],
            ["Factures comptant sans acompte connu sur leur BC", t.get("FACTURE_COMPTANT_SANS_ACOMPTE", 0)],
            ["Recus negatifs sans recu d'origine", t.get("ANNULATION_RECU_A_VERIFIER", 0)],
            ["Recus negatifs (total)", len(recus_neg)],
            ["Anomalies CR au registre (total)", len(registre)],
            ["Anomalies CR ouvertes avec impact sur un solde", sum(1 for r_ in registre if r_[6] == "OUVERTE")],
            ]):
        ws.append(row)
    feuilles = [
        ("CONTROLE_JOURS", ["Rapport", "Feuille", "Date", "Factures", "Avoirs", "Acomptes imputes", "Recus",
                            "Recus negatifs", "BC/BL seuls", "Annulees", "Total rapport = lignes",
                            "Montants expliques"], controle),
        ("RECAP", ["Rapport", "Date", "Colonne RECAP", "Feuille du jour", "RECAP", "Ecart"], recap_ecarts),
        ("DATES_FEUILLES", ["Rapport", "Feuille", "Date attendue", "Date imprimee (A4)", "Constat"], dates_feuilles),
        ("ANOMALIES", ["Rapport", "Feuille", "Date", "Ligne", "Gravite", "Motif", "Contenu"], anomalies),
        ("FACTURES_COMPTANT", ["Type", "Client (libelle)", "Constat"],
         [x for x in alertes if x[0] == "FACTURE_COMPTANT_SANS_ACOMPTE"]),
        ("RECUS_NEGATIFS", ["Date", "Recu", "Client (libelle)", "Montant", "Recu annule"], recus_neg),
        ("CATALOGUE", ["Code", "Erreur de CR", "Impact sur le solde", "Cas", "Ouvertes apres import"], catalogue),
        ("REGISTRE_ANOMALIES", ["Date", "Feuille", "Ligne", "Code", "Gravite", "Impact solde", "Statut", "Client",
                                "Piece", "Montant", "Motif", "Resolution"], registre),
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
