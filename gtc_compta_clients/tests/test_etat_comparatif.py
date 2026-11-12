"""Etat comparatif (modele RECAP) et rapprochement quotidien des ventes CR / Sage."""
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
from gtc_compta.sage.base import SageEntry
from gtc_compta.services import etat_comparatif as ec

from .conftest import DEMO

FX = Path(__file__).parent / "fixtures"


def _jour(cfg, fichier, feuille, d=None):
    return ParseurRapport(cfg["rapport"], {}).analyser(lire_feuille(fichier, feuille), feuille, "BERTOUA", d)


def test_valeurs_jour_reel_01_octobre(cfg):
    """Chiffres du 01/10/2026 identiques a la ligne RECAP du rapport (hors ACOMPTE errone le 4 et le 21)."""
    v = ec.valeurs_jour(_jour(cfg, FX / "RC_OCT_2026_ANONYMISE.xlsx", "01"), cfg["rapport"])
    assert (v["vente_comptant"], v["vente_credit"], v["total_ventes"], v["recouvrements"]) == \
        (12009800, 37652250, 49662050, 118987700)
    assert v["total_ventes_cellule_cr"] == 49662050          # cellule I169 du CR = comptant + credit
    assert v["recette"] == 118987700 + 12009800               # regle GTC : recouvrements + vente comptant
    assert v["acompte"] == 13060400


def test_recette_selon_le_modele_recap(cfg):
    v = ec.valeurs_jour(_jour(cfg, FX / "RC_OCT_2026_ANONYMISE.xlsx", "01"), cfg["rapport"], "acompte+recouvrement")
    assert v["recette"] == 132048100                          # = RECETTE de la feuille RECAP


def _charger_demo(db, cfg, feuille="01"):
    res = _jour(cfg, DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", feuille)
    v = ec.valeurs_jour(res, cfg["rapport"])
    ec.enregistrer_jour(db, v, "demo")
    return v


def test_rapprochement_ventes_ecart_explique_piece_par_piece(base, user, cfg, sage):
    v = _charger_demo(base, cfg)
    assert v["total_ventes"] == 942700
    r = ec.rapprocher_ventes_jour(base, user, sage, "BERTOUA", date(2026, 10, 1))
    assert r["statut"] == "ECART" and r["ventes_sage"] == 867700 and r["ecart"] == 75000
    assert r["pieces_cr_absentes_de_sage"] == [("FACB0204", 75000)]
    assert r["pieces_sage_absentes_du_cr"] == []


def test_rapprochement_ventes_concordant(base, user, cfg, sage):
    _charger_demo(base, cfg)
    sage.ajouter_ecriture(SageEntry(700, "CL777", "VTE", date(2026, 10, 1), "FACB0204", "FACB0204", "Facture", "D", 75000))
    r = ec.rapprocher_ventes_jour(base, user, sage, "BERTOUA", date(2026, 10, 1))
    assert r["statut"] == "CONCORDANT" and r["ecart"] == 0
    assert base.scalar("SELECT statut_sage FROM etat_comparatif_jours") == "CONCORDANT"


def test_rapprochement_ventes_sage_indisponible(base, user, cfg, sage):
    _charger_demo(base, cfg)
    sage.disponible = False
    assert ec.rapprocher_ventes_jour(base, user, sage, "BERTOUA", date(2026, 10, 1))["statut"] == "SAGE_INDISPONIBLE"


def test_nouveaux_chiffres_du_cr_remettent_le_controle_a_faire(base, user, cfg, sage):
    v = _charger_demo(base, cfg)
    ec.rapprocher_ventes_jour(base, user, sage, "BERTOUA", date(2026, 10, 1))
    v["total_ventes"] += 1000
    ec.enregistrer_jour(base, v, "correction")
    assert base.scalar("SELECT statut_sage FROM etat_comparatif_jours") == "NON_VERIFIE"


def test_tableau_du_mois_et_export_excel(base, user, cfg, tmp_path):
    for f, mois in (("RC_SEPT_2026_ANONYMISE.xlsx", 9), ("RC_OCT_2026_ANONYMISE.xlsx", 10)):
        n = ec.charger_rapport_mensuel(base, user, FX / f, cfg["rapport"], "BERTOUA", mois, 2026)
        assert n == 4
    t = ec.tableau_mois(base, "BERTOUA", 2026, 10)
    assert len(t["jours"]) == 4 and t["total_m1"] is not None and t["total_n1"] is None
    assert t["total_m"]["total_ventes"] == sum(j["total_ventes"] for j in t["jours"])
    assert t["evolution"]["recouvrements"] == t["total_m"]["recouvrements"] - t["total_m1"]["recouvrements"]
    dest = ec.exporter_excel(base, "BERTOUA", [(2026, 9), (2026, 10)], tmp_path / "etat.xlsx", "GTC")
    wb = load_workbook(dest)
    assert wb.sheetnames == ["SEPTEMBRE 2026", "OCTOBRE 2026", "RAPPROCHEMENT VENTES SAGE", "CONTROLES"]
    ws = wb["OCTOBRE 2026"]
    assert ws["A3"].value == "DATES" and ws["F3"].value == "RECETTE TOTALE"
    assert ws.max_column == 6                                  # l'etat comparatif s'arrete a la recette totale
    assert any(r[0].value == "TOTAL M" for r in ws.iter_rows())


def test_references_saisies_dans_recap(base, user, cfg, tmp_path):
    """TOTAL N-1 (saisi dans RECAP) sert de reference quand l'annee precedente n'est pas chargee ; le TOTAL M-1
    saisi est conserve pour etre compare au M-1 calcule."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "RECAP"
    ws.append(["DATES", "ACOMPTE", "VENTE COMPTANT", "VENTE A TERME", "TOTAL VENTES", "RECOUVREMENTS", "RECETTE"])
    ws.append(["TOTAL M-1", 10, 1000, 5000, 6000, 3000, 3010])
    ws.append(["TOTAL N-1", 20, 900, 4000, 4900, 2500, 2520])
    wb.save(tmp_path / "rc.xlsx")
    refs = ec.enregistrer_references_recap(base, "BERTOUA", 2026, 10, tmp_path / "rc.xlsx", "comptant+recouvrement")
    assert refs["N-1_SAISI_RECAP"]["recette"] == 2500 + 900
    t = ec.tableau_mois(base, "BERTOUA", 2026, 10)
    assert t["source_n1"] == "saisi dans RECAP" and t["total_n1"]["total_ventes"] == 4900
    assert t["m1_saisi_recap"]["vente_credit"] == 5000
