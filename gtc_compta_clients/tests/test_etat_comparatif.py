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
    assert wb.sheetnames == ["SEPTEMBRE 2026", "OCTOBRE 2026", "RAPPROCHEMENT VENTES SAGE", "CONTROLES",
                             "ETAT COMPARATIF 2026"]                 # l'etat comparatif annuel est la derniere feuille
    ws = wb["OCTOBRE 2026"]
    # Modele GTC « ETAT CHIFFRE D'AFFAIRE »
    assert ws["A1"].value == "ETAT CHIFFRE D'AFFAIRE MOIS OCTOBRE 2026"
    assert (ws["A2"].value, ws["B2"].value) == ("DATES", "CHIFFRE D'AFFAIRE")
    assert [ws.cell(3, c).value for c in range(2, 7)] == ["TOTAL", "COMPTANT", "CREDIT", "RECOUVREMENT", "TOTAL RECETTE"]
    assert ws.max_column == 6                                   # s'arrete au TOTAL RECETTE
    assert ws["D4"].value == "=B4-C4" and ws["F4"].value == "=C4+E4"        # formules du modele
    assert ws.cell(4 + 31, 1).value == "TOTAL" and ws.cell(4 + 31, 2).value == "=SUM(B4:B34)"
    assert ws.cell(36, 1).value == "Total SEPTEMBRE 2026" and ws.cell(37, 1).value == "VARIATION"
    assert ws.cell(38, 1).value == "Total OCTOBRE 2025"
    assert ws.cell(40, 1).value == "CREANCE AU 31-10-26" and ws.cell(41, 1).value == "CREANCE AU 30-09-26"
    assert ws.cell(40, 4).value == "n/d"                        # creance non calculee (Sage non interroge)


def test_creance_fin_de_mois_depuis_sage(base, user, sage):
    r = ec.calculer_creance(base, user, sage, "BERTOUA", 2026, 10)
    assert r["statut"] == "OK" and r["montant"] == sum(sage.soldes_a_date(date(2026, 10, 31)).values())
    assert ec.tableau_mois(base, "BERTOUA", 2026, 10)["creance_fin"] == r["montant"]


def test_creance_non_disponible_sans_sage_ni_soldes_d_ouverture(db, user, sage):
    sage.disponible = False
    assert ec.calculer_creance(db, user, sage, "BERTOUA", 2026, 10)["statut"] == "NON_DISPONIBLE"


def test_import_d_un_etat_chiffre_d_affaire_existant(db, user, tmp_path):
    """Classeur au modele GTC (une feuille par mois) : charge comme historique, lignes saisies controlees."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for nom, mois, jours, saisi_m1, creances in (
            ("JANVIER", 1, [(2, 1000, 400, 300), (3, 500, 100, 200)], None,
             [("CREANCE AU 31/12/24", 5000), ("CREANCE AU 31/01/25", 6000)]),
            ("FEVRIER", 2, [(1, 800, 300, 100)], ("Total janvier 2025", 1500, 500, 1000, 400, 900),
             [("CREANCE AU 28-02-25", 6500), ("CREANCE AU 31-01-25", 6100)])):
        ws = wb.create_sheet(nom)
        ws.append([f"ETAT CHIFFRE D'AFFAIRE MOIS {nom} 2025"])
        ws.append(["DATES", "CHIFFRE D'AFFAIRE"])
        ws.append([None, "TOTAL", "COMPTANT", "CREDIT", "RECOUVREMENT", "TOTAL RECETTE"])
        for j, tot, cpt, rec in jours:
            ws.append([__import__("datetime").datetime(2025, mois, j), tot, cpt, tot - cpt, rec, cpt + rec])
        ws.append(["TOTAL"])
        if saisi_m1:
            ws.append(list(saisi_m1))
        for lib, v in creances:
            ws.append([lib, None, None, v])
    wb.save(tmp_path / "etat.xlsx")
    r = ec.charger_etat_modele(db, user, tmp_path / "etat.xlsx", "AGENCE X")
    assert r["jours"] == 3 and r["mois"] == [(2025, 1), (2025, 2)]
    t = ec.tableau_mois(db, "AGENCE X", 2025, 2)
    assert t["total_m1"]["total_ventes"] == 1500 and t["creance_debut"] == 6000 and t["creance_fin"] == 6500
    motifs = " ".join(c[2] for c in r["controles"])
    assert "6100" in motifs and "ecart 100" in motifs                    # creance au 31/01 saisie deux fois differemment
    assert "recouvrements" in motifs                                       # Total janvier saisi : recouvrement faux


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
    assert t["source_n1"] == "saisi" and t["total_n1"]["total_ventes"] == 4900
    assert t["m1_saisi_recap"]["vente_credit"] == 5000


def test_creances_non_mises_a_jour_detectees(db, user, tmp_path):
    """Cas reel (etat 2025, feuille OCTOBRE) : lignes CREANCE recopiees du mois precedent."""
    from datetime import datetime
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "OCTOBRE"
    ws.append(["ETAT CHIFFRE D'AFFAIRE MOIS OCTOBRE 2025"])
    ws.append(["DATES", "CHIFFRE D'AFFAIRE"])
    ws.append([None, "TOTAL", "COMPTANT", "CREDIT", "RECOUVREMENT", "TOTAL RECETTE"])
    ws.append([datetime(2025, 10, 1), 1000, 400, 600, 300, 700])
    ws.append(["CREANCE AU 30-09-25", None, None, 281419325])
    ws.append(["CREANCE AU 31-08-25", None, None, 272460025])
    wb.save(tmp_path / "oct.xlsx")
    r = ec.charger_etat_modele(db, user, tmp_path / "oct.xlsx", "AGENCE X")
    assert any("31-10-25 absente" in c[2] for c in r["controles"])


def test_etat_comparatif_annuel_une_ligne_par_mois(base, user, cfg, tmp_path):
    """Derniere feuille : une ligne par mois (janvier a decembre), memes colonnes, comparaison avec le mois
    precedent ; pas de comparaison N-1 sans les rapports de l'annee precedente."""
    for f, mois in (("RC_SEPT_2026_ANONYMISE.xlsx", 9), ("RC_OCT_2026_ANONYMISE.xlsx", 10)):
        ec.charger_rapport_mensuel(base, user, FX / f, cfg["rapport"], "BERTOUA", mois, 2026)
    ta = ec.tableau_annuel(base, "BERTOUA", 2026)
    assert [x["libelle"] for x in ta["mois"]][0] == "JANVIER" and len(ta["mois"]) == 12
    sept, octo = ec.tableau_mois(base, "BERTOUA", 2026, 9)["total_m"], ec.tableau_mois(base, "BERTOUA", 2026, 10)["total_m"]
    assert ta["mois"][9]["totaux"]["total_ventes"] == octo["total_ventes"] and ta["mois"][0]["totaux"] is None
    assert ta["total"]["recette"] == sept["recette"] + octo["recette"]
    c = ta["comparaison"]
    assert c["mois"] == (2026, 10) and c["precedent"] == (2026, 9)
    assert c["variation_precedent"]["recouvrements"] == octo["recouvrements"] - sept["recouvrements"]
    assert c["totaux_n1"] is None                                  # N-1 non disponible : non compare
    assert ec.tableau_annuel(base, "BERTOUA", 2026, 9)["comparaison"]["totaux_precedent"] is None  # aout non charge

    dest = ec.exporter_excel(base, "BERTOUA", [(2026, 9), (2026, 10)], tmp_path / "etat.xlsx", "GTC")
    ws = load_workbook(dest)["ETAT COMPARATIF 2026"]
    assert ws["A1"].value == "ETAT COMPARATIF ANNEE 2026" and ws["A2"].value == "MOIS"
    assert [ws.cell(3, c).value for c in range(2, 7)] == ["TOTAL", "COMPTANT", "CREDIT", "RECOUVREMENT", "TOTAL RECETTE"]
    assert [ws.cell(r, 1).value for r in range(4, 16)][::11] == ["JANVIER", "DECEMBRE"]
    assert ws["B13"].value == "='OCTOBRE 2026'!B35" and ws["F12"].value == "='SEPTEMBRE 2026'!F34"
    assert ws["A16"].value == "TOTAL" and ws["B16"].value == "=SUM(B4:B15)"
    assert ws["A18"].value == "COMPARAISON OCTOBRE 2026 / SEPTEMBRE 2026"
    assert (ws["A19"].value, ws["A20"].value, ws["A21"].value, ws["A22"].value) == \
        ("OCTOBRE 2026", "SEPTEMBRE 2026", "VARIATION", "VARIATION %")
    assert ws["E21"].value == "=E19-E20"
    assert "non disponibles" in ws["A23"].value
