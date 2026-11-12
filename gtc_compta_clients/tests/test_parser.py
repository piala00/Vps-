from datetime import date

import pytest

from gtc_compta.excel.preparation import (ecrire_classeur_prepare, lignes_export, lire_export_erp,
                                          preparer_depuis_classeur)
from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
from gtc_compta.money import MontantInvalide, parse_montant

from .conftest import CORR, DEMO


def analyser(cfg, feuille="01"):
    rows = lire_feuille(DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", feuille)
    return ParseurRapport(cfg["rapport"], CORR).analyser(rows, feuille, "BERTOUA", date(2026, 10, int(feuille)))


def test_cas1_seules_les_deux_sections_utiles(cfg):
    r = analyser(cfg)
    refs = {m.reference_piece for m in r.mouvements}
    assert refs == {"FACB0201", "FVCB0301", "FACB0202", "FACB0203", "FRCB0001", "FACB0204",
                    "7RCB0451", "RCB0452", "7RCB0453"}
    assert "BLCB0001" not in refs                                 # BL seul ignore
    # totaux, versement caisse et depenses non integres
    assert sum(m.montant for m in r.reglements) == 300000 + 120000 + 35000
    assert r.stats["totaux_exclus"] >= 2 and r.stats["hors_perimetre_exclus"] == 1
    assert not any("Carburant" in a.contenu for a in r.anomalies)
    assert not any(a.ligne in (5,) for a in r.anomalies)        # ligne d'en-tete non signalee


def test_cas1_entete_recus_detectee_dynamiquement(cfg):
    assert analyser(cfg, "01").ligne_entete_recus != analyser(cfg, "02").ligne_entete_recus


def test_cas2_bc_plus_facture_compte_une_fois(cfg):
    r = analyser(cfg)
    alpha = [m for m in r.factures if m.ct_num == "CL001" and m.nature == "FACTURE"]
    assert [(m.reference_piece, m.montant, m.bc_origine) for m in alpha] == [("FACB0201", 500000, "BC0101")]
    assert r.stats["bc_seuls_ignores"] == 2                      # BCCB0101 + BLCB0001


def test_avoir_negatif_pas_de_double_inversion(cfg):
    av = next(m for m in analyser(cfg).factures if m.reference_piece == "FRCB0001")
    assert (av.nature, av.sens, av.montant) == ("AVOIR", "C", 50000)


def test_type_non_parametre_bloquant(cfg):
    del cfg["rapport"]["types_documents"]["FRCB"]
    r = analyser(cfg)
    assert any("FRCB" in a.motif and a.gravite == "BLOQUANT" for a in r.anomalies)
    assert "FRCB0001" not in {m.reference_piece for m in r.mouvements}


def test_compte_collectif_ventilation_analytique(cfg):
    m = next(m for m in analyser(cfg).factures if m.reference_piece == "FACB0202")
    assert m.ct_num == "CL099" and m.acheteur_detail == "M. NDONGO"


def test_client_sans_correspondance_signale(cfg):
    r = analyser(cfg)
    m = next(m for m in r.factures if m.reference_piece == "FACB0204")
    assert m.ct_num == ""
    assert any("NOUVEAU CLIENT X" in a.motif for a in r.anomalies)


def test_montants_h_i_incoherents_bloquants(cfg):
    r = analyser(cfg, "02")
    assert any("differents" in a.motif for a in r.anomalies)
    assert "FACB0211" not in {m.reference_piece for m in r.mouvements}
    assert next(m for m in r.factures if m.reference_piece == "FACB0210").montant == 1250000


def test_entete_recus_absente_bloquante(cfg):
    r = ParseurRapport(cfg["rapport"], CORR).analyser([["", "", "FACB1", "ETS ALPHA", "", None, None, 10, None]],
                                                      "X", "B", None)
    assert r.bloquant


@pytest.mark.parametrize("v,attendu", [(1500, 1500), (1500.0, 1500), ("1 250 000", 1250000),
                                       ("1.250.000", 1250000), ("(5 000)", -5000), ("-200", -200),
                                       ("12 000 FCFA", 12000), ("", None), (None, None)])
def test_parse_montant(v, attendu):
    assert parse_montant(v) == attendu


def test_parse_montant_centimes_refuses():
    with pytest.raises(MontantInvalide):
        parse_montant("100,55")


def test_classeur_prepare_aller_retour(cfg, tmp_path):
    rows = lire_feuille(DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", "01")
    r = ParseurRapport(cfg["rapport"], CORR).analyser(rows, "01", "BERTOUA", date(2026, 10, 1))
    out = ecrire_classeur_prepare(r, rows, tmp_path / "prep.xlsx", "test")
    lues = lire_export_erp(out)
    assert len(lues) == len(r.mouvements) and lues[0]["id_import"] == lignes_export(r)[0]["id_import"]
    # le classeur produit est relisible comme classeur de preparation (secours macros desactivees)
    r2 = preparer_depuis_classeur(out, cfg["rapport"], CORR)
    assert [m.reference_piece for m in r2.mouvements] == [m.reference_piece for m in r.mouvements]
    assert r2.date_rapport == date(2026, 10, 1)
    with pytest.raises(ValueError):
        ecrire_classeur_prepare(r, rows, tmp_path / "faux.xlsm")


def test_export_erp_ecrit_par_excel_normalise(tmp_path):
    """Simule les conversions d'Excel (date en datetime, montant flottant) sur EXPORT_ERP."""
    from datetime import datetime
    from openpyxl import Workbook
    from gtc_compta.excel.preparation import EXPORT_COLONNES
    wb = Workbook()
    ws = wb.active
    ws.title = "EXPORT_ERP"
    ws.append(EXPORT_COLONNES)
    ws.append(["GTC-EXPORT-1", "BERTOUA-2026-10-01-V1", "BERTOUA", datetime(2026, 10, 1), "FACTURE", "FACB0201",
               None, "ETS ALPHA", None, 500000.0, "D", None, "EN COMPTE", "COLLAGE", 7.0, "x"])
    wb.save(tmp_path / "vba.xlsx")
    l = lire_export_erp(tmp_path / "vba.xlsx")[0]
    assert l["date_rapport"] == "2026-10-01" and l["montant"] == 500000 and l["source_ligne"] == 7
    assert l["code_tiers"] == ""
