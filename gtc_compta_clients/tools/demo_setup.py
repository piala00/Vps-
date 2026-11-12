"""Prepare un environnement de DEMONSTRATION complet (donnees fictives) :
demo/sortie/config.json + base avec une journee importee, rapprochee et des fiches imprimees.
Usage : python tools/demo_setup.py   puis   python run.py --config demo/sortie/config.json
"""
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gtc_compta.context import AppContext  # noqa: E402
from gtc_compta.excel import preparation as prep  # noqa: E402
from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille  # noqa: E402
from gtc_compta.services import clients, imports, printing, reconciliation, solvency, pointing  # noqa: E402

OUT = ROOT / "demo" / "sortie"


def main():
    if not (ROOT / "demo" / "sage_demo.json").exists():
        import subprocess
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "make_demo.py")])
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    pdfs = OUT / "factures_pdf"
    pdfs.mkdir()
    cfg = {"data_dir": "data", "sage": {"mode": "demo"},
           "documents": {"dossiers_pdf": [str(pdfs)], "dossier_export": str(OUT / "exports")},
           "utilisateur": {"login": "compta1", "nom": "Comptable (demo)", "role": "comptable_controleur"}}
    (OUT / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    ctx = AppContext(OUT / "config.json")
    db, u, sage = ctx.db, ctx.user, ctx.sage
    clients.synchroniser_clients(db, u, sage, ctx.cfg["rapport"]["comptes_collectifs"])
    for lib, ct in {"ETS ALPHA": "CL001", "QUINCAILLERIE BETA": "CL002", "SOCIETE GAMMA": "CL003",
                    "DELTA SARL": "CL004", "CLIENTS DETAILS BTA": "CL099", "COMPTE DE LIAISON": "CL050"}.items():
        clients.definir_correspondance(db, u, lib, ct)
    for ct, zone, tel in [("CL001", "CENTRE", "699000001"), ("CL002", "CENTRE", "677000002"),
                          ("CL003", "EST - BATOURI", "655000003"), ("CL004", "BELABO", ""), ("CL099", "CENTRE", ""),
                          ("CL050", "CENTRE", "")]:
        clients.maj_champs_manuels(db, u, ct, zone=zone, delai_reglement_jours=30, telephone_whatsapp=tel or None)
    clients.importer_soldes_ouverture(db, u, sage, date(2026, 9, 30))
    rows = lire_feuille(ROOT / "demo" / "RC_DEMO_SYNTHETIQUE.xlsx", "01")
    res = ParseurRapport(ctx.cfg["rapport"], clients.correspondances(db)).analyser(rows, "COLLAGE", "BERTOUA",
                                                                                   date(2026, 10, 1))
    classeur = prep.ecrire_classeur_prepare(res, rows, OUT / "GTC_PREPARATION_20261001.xlsx", u.login)
    lignes = prep.lire_export_erp(classeur)
    imports.importer_lot(db, u, lignes, str(classeur), imports.empreinte_fichier(classeur),
                         bons=prep.bons_export(res), anomalies=prep.anomalies_export(res))
    reconciliation.rapprocher(db, u, sage, date(2026, 10, 1))
    from gtc_compta.services import etat_comparatif as ec
    ec.enregistrer_jour(db, ec.valeurs_jour(res, ctx.cfg["rapport"]), source=str(classeur))
    ec.rapprocher_ventes_jour(db, u, sage, ctx.cfg["agence"], date(2026, 10, 1))
    res2 = ParseurRapport(ctx.cfg["rapport"], clients.correspondances(db)).analyser(
        lire_feuille(ROOT / "demo" / "RC_DEMO_SYNTHETIQUE.xlsx", "02"), "COLLAGE", "BERTOUA", date(2026, 10, 2))
    ec.enregistrer_jour(db, ec.valeurs_jour(res2, ctx.cfg["rapport"]), source="demo")
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(pdfs / "Facture FACB0201 ETS ALPHA.pdf"))
    c.drawString(72, 750, "FACTURE FACB0201 - DOCUMENT FICTIF DE DEMONSTRATION")
    c.save()
    from gtc_compta.services import documents
    documents.indexer_dossiers(db, [str(pdfs)])
    solvency.controler_bc(db, u, sage, "BCCB0101", ctx.cfg["solvabilite"])
    solvency.controler_bc(db, u, sage, "BCCB0150", ctx.cfg["solvabilite"])
    pointing.enregistrer_solde_client(db, u, sage, "CL002", date(2026, 10, 1), 0, "Gerant Beta", "TELEPHONE")
    pointing.enregistrer_solde_client(db, u, sage, "CL001", date(2026, 10, 1), 1600000, "Mme Alpha", "WHATSAPP")
    r = printing.generer_fiches(db, u, ["CL002"], ctx.data_dir / "impressions" / "FICHES_DEMO.pdf", ctx.cfg)
    printing.confirmer_impression(db, u, r["job_id"])
    print(f"Demo prete : python run.py --config {OUT / 'config.json'}")


if __name__ == "__main__":
    main()
