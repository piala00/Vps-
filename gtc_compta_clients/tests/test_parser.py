from datetime import date
from pathlib import Path

import pytest

from gtc_compta.excel.preparation import (ecrire_classeur_prepare, lignes_export, lire_export_erp,
                                          preparer_depuis_classeur)
from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
from gtc_compta.money import MontantInvalide, parse_montant

from .conftest import CORR, DEMO

REEL = Path(__file__).parent / "fixtures" / "RC_OCT_2026_ANONYMISE.xlsx"   # 10 RC OCT.xlsx anonymise


def analyser(cfg, feuille="01", fichier=None, corr=CORR):
    rows = lire_feuille(fichier or DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", feuille)
    return ParseurRapport(cfg["rapport"], corr).analyser(rows, feuille, "BERTOUA", None)


# ---------------------------------------------------------------------------------------
# Rapport REEL (anonymise) : chiffres de reference etablis sur 10 RC OCT.xlsx
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("feuille,fact,avoirs,acomptes,recus,annulees", [
    ("01", 124, 1, 84, 23, 8), ("03", 165, 6, 85, 38, 8), ("12", 247, 2, 156, 62, 9), ("14", 181, 32, 97, 28, 1)])
def test_reel_comptages(cfg, feuille, fact, avoirs, acomptes, recus, annulees):
    s = analyser(cfg, feuille, REEL, {}).stats
    assert (s["factures"], s["avoirs"], s["acomptes"], s["reglements"], s["annulees"]) == \
        (fact, avoirs, acomptes, recus, annulees)


@pytest.mark.parametrize("feuille", ["01", "03", "12", "14"])
def test_reel_totaux_du_rapport_et_aucun_montant_oublie(cfg, feuille):
    r = analyser(cfg, feuille, REEL, {})
    for cle, v in r.stats["controle_totaux"].items():
        assert v["rapport"] == v["lignes"], cle            # coherence du rapport lui-meme
        assert v["ecart_non_explique"] == 0, cle           # chaque montant est retenu, exclu ou bloque


def test_reel_jour01_montants(cfg):
    r = analyser(cfg, "01", REEL, {})
    ctl = r.stats["controle_totaux"]
    assert set(ctl) == {"documents_H", "documents_I", "recus_F"}   # colonnes BC (F, G) non exploitees
    assert ctl["documents_H"]["retenu"] == 12009800          # TOTAL VENTES comptant
    assert ctl["documents_I"]["retenu"] == 37652250          # TOTAL VENTES a terme (avoir FVCB deduit)
    assert ctl["recus_F"]["retenu"] == 118987700             # TOTAL DE VERSEMENTS / RECOUVREMENTS
    assert sum(m.montant for m in r.acomptes) == 12009800    # acomptes imputes = factures comptant
    assert r.date_rapport == date(2026, 10, 1) and r.ligne_entete_recus == 170


def test_reel_colonnes_bon_de_commande_jamais_exploitees(cfg):
    """BCCB033708 : acompte de 3 500 encaisse au stade du BC (colonne F) -> aucun mouvement.
    Les acomptes n'apparaissent qu'imputes sur une facture comptant (meme piece, meme montant)."""
    r = analyser(cfg, "01", REEL, {})
    assert not any(m.reference_piece.startswith(("BCCB", "BLCB")) for m in r.mouvements)
    fact_h = {(m.reference_piece, m.montant) for m in r.factures if m.colonne == "H"}
    assert {(m.reference_piece, m.montant) for m in r.acomptes} == fact_h
    assert not any(m.colonne == "I" for m in r.acomptes)        # facture en compte / BP : pas d'acompte


def test_reel_avoir_fvcb_et_bc_seul(cfg):
    r = analyser(cfg, "01", REEL, {})
    av = next(m for m in r.factures if m.reference_piece == "FVCB000502")
    assert (av.nature, av.sens, av.montant) == ("AVOIR", "D", -125000)       # debit, signe conserve
    refs = {m.reference_piece for m in r.factures}
    assert "BCCB033581" not in refs                          # BC seul (BP) : aucune creance
    # BC33525 : 5 factures distinctes sur le meme BC
    assert sum(1 for m in r.factures if m.bc_origine == "BC33525") == 5


def test_reel_bc_avec_montant_facture_bloque(cfg):
    r = analyser(cfg, "03", REEL, {})
    assert any("BCCB034029" in a.motif and a.gravite == "BLOQUANT" for a in r.anomalies)
    assert not any(m.reference_piece == "BCCB034029" for m in r.mouvements)


def test_reel_meme_numero_pour_deux_clients(cfg):
    r = analyser(cfg, "12", REEL, {})
    assert sum(1 for a in r.anomalies if "FACB039522" in a.motif and "plusieurs clients" in a.motif) == 2


def test_reel_recus_negatifs_annulent_le_recu_errone(cfg):
    """Recu negatif = contre-passation du recu fait sur un compte errone (meme client, meme montant)."""
    r = analyser(cfg, "14", REEL, {})
    ann = {m.reference_piece: m for m in r.reglements if m.montant < 0}
    assert all(m.nature == "REGLEMENT" and m.sens == "C" for m in r.reglements)
    assert set(ann) == {"7RCB028975", "7RCB028976"}
    assert ann["7RCB028975"].reference_liee == "7RCB028907"
    assert (ann["7RCB028975"].sens, ann["7RCB028975"].montant) == ("C", -3500000)   # credit, signe conserve
    assert ann["7RCB028976"].reference_liee == "7RCB028853" and ann["7RCB028976"].montant == -7000000
    assert not any(a.gravite == "BLOQUANT" and "RECUS" == a.section for a in r.anomalies)
    assert r.stats["controle_totaux"]["recus_F"]["ecart_non_explique"] == 0
    assert r.stats["controle_totaux"]["recus_F"]["retenu"] == 93400750          # = TOTAL DE VERSEMENTS


def test_recu_negatif_sans_original_avertit(cfg):
    r = analyser(cfg, "02")
    a = next(m for m in r.reglements if m.reference_piece == "7RCB0462")
    assert (a.nature, a.sens, a.montant, a.reference_liee) == ("REGLEMENT", "C", -5000, "")
    assert any("7RCB0462" in x.motif and x.gravite == "AVERTISSEMENT" for x in r.anomalies)


def test_reel_compte_de_liaison_est_un_client(cfg):
    """COMPTE DE LIAISON, VENTE PROMOTIONNELLE, SOURCE DU PAYS RETOUR : comptes clients Sage reels."""
    r = analyser(cfg, "03", REEL, {})
    liaison = [m for m in r.mouvements if m.client_libelle == "COMPTE DE LIAISON"]
    assert {m.reference_piece for m in liaison} >= {"FRCB000747", "FACB038198"}
    av = next(m for m in liaison if m.reference_piece == "FRCB000747")
    assert (av.nature, av.sens, av.montant) == ("AVOIR", "D", -172995)
    assert r.stats["montants_exclus"].get("H", 0) == 0
    # les versements de caisse restent exclus
    assert not any("VERSEMENT" in m.client_libelle for m in r.mouvements)


# ---------------------------------------------------------------------------------------
# Donnees synthetiques (meme structure) : cas limites cibles
# ---------------------------------------------------------------------------------------
def test_cas1_seules_les_deux_sections_utiles(cfg):
    r = analyser(cfg)
    assert {m.reference_piece for m in r.factures} == {"FACB0201", "FACB0301", "FACB0202", "FACB0203",
                                                       "FRCB0001", "FACB0204", "FACB0206", "FACB0207"}
    assert {m.reference_piece for m in r.reglements} == {"7RCB0451"}
    assert sum(m.montant for m in r.reglements) == 300000     # REPORT, versements caisse, BTF exclus
    assert {m.reference_piece for m in r.acomptes} == {"FACB0301", "FACB0202", "FACB0206"}
    assert r.stats["annulees"] == 1
    assert r.stats["hors_perimetre_exclus"] == 4   # REPORT + versements caisse + BTF + SOLDE
    assert all(v["ecart_non_explique"] == 0 for v in r.stats["controle_totaux"].values())


def test_cas1_entete_recus_detectee_dynamiquement(cfg):
    assert analyser(cfg, "01").ligne_entete_recus != analyser(cfg, "02").ligne_entete_recus


def test_cas2_bc_plus_facture_compte_une_fois(cfg):
    r = analyser(cfg)
    alpha = [m for m in r.factures if m.ct_num == "CL001" and m.nature == "FACTURE"]
    assert [(m.reference_piece, m.montant, m.bc_origine) for m in alpha] == [("FACB0201", 500000, "BC0101")]
    assert r.stats["bc_seuls_ignores"] == 1                      # BCCB0101


def test_facture_comptant_soldee_par_acompte_impute(cfg):
    r = analyser(cfg)
    beta = [(m.nature, m.sens, m.montant) for m in r.mouvements if m.ct_num == "CL002"]
    assert sorted(beta) == [("ACOMPTE", "C", 120000), ("FACTURE", "D", 120000)]
    alpha = [m.nature for m in r.mouvements if m.ct_num == "CL001"]
    assert "ACOMPTE" not in alpha                           # facture en compte : pas d'acompte


def test_mode_facture_seule(cfg):
    cfg["rapport"]["factures_comptant"]["mode"] = "facture_seule"
    assert analyser(cfg).acomptes == []


def test_regle_des_signes(cfg):
    """Regle GTC : factures (retours / avoirs compris) au debit, recus et acomptes au credit,
    toujours avec le signe du rapport."""
    r = analyser(cfg)
    av = next(m for m in r.factures if m.reference_piece == "FRCB0001")
    assert (av.nature, av.sens, av.montant) == ("AVOIR", "D", -50000)
    assert all(m.sens == "D" for m in r.factures)
    assert all(m.sens == "C" for m in r.acomptes + r.reglements)


def test_reel_regle_des_signes_sur_le_mois(cfg):
    for f in ("01", "03", "12", "14"):
        r = analyser(cfg, f, REEL, {})
        assert all(m.sens == "D" for m in r.factures) and all(m.sens == "C" for m in r.acomptes + r.reglements)
        assert all(m.montant < 0 for m in r.factures if m.nature == "AVOIR")


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
    assert next(m for m in r.factures if m.reference_piece == "FACB0204").ct_num == ""
    assert any("NOUVEAU CLIENT X" in a.motif for a in r.anomalies)


def test_jour02_cas_bloquants(cfg):
    r = analyser(cfg, "02")
    assert any("differents" in a.motif for a in r.anomalies)                  # H et I incoherents
    assert any("BCCB0300" in a.motif for a in r.anomalies)                    # n° de BC + facture
    assert any("Recu negatif" in a.motif for a in r.anomalies)                # recu negatif sans original
    assert next(m for m in r.factures if m.reference_piece == "FACB0210").montant == 1250000
    assert all(v["ecart_non_explique"] == 0 for v in r.stats["controle_totaux"].values())


def test_date_feuille_differente_bloquante(cfg):
    rows = lire_feuille(DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", "01")
    r = ParseurRapport(cfg["rapport"], CORR).analyser(rows, "01", "BERTOUA", date(2026, 10, 2))
    assert any("Date de la feuille" in a.motif and a.gravite == "BLOQUANT" for a in r.anomalies)


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
    r = ParseurRapport(cfg["rapport"], CORR).analyser(rows, "01", "BERTOUA", None)
    out = ecrire_classeur_prepare(r, rows, tmp_path / "prep.xlsx", "test")
    lues = lire_export_erp(out)
    assert len(lues) == len(r.mouvements) and lues[0]["id_import"] == lignes_export(r)[0]["id_import"]
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


def test_controle_croise_macro_application(cfg):
    from gtc_compta.excel.preparation import comparer_exports
    l = lignes_export(analyser(cfg))
    assert comparer_exports(l, list(l)) == []
    modif = [dict(x) for x in l]
    modif[0]["montant"] += 1
    assert len(comparer_exports(modif, l)) == 2


def test_compte_de_liaison_conteneur(cfg):
    """COMPTE DE LIAISON : compte conteneur, le beneficiaire reel (colonne E) est conserve."""
    m = next(m for m in analyser(cfg).factures if m.reference_piece == "FACB0206")
    assert m.ct_num == "CL050" and m.acheteur_detail == "REUNION DIRECTION"
    r = analyser(cfg, "03", REEL, {})
    benef = {m.acheteur_detail for m in r.mouvements if m.client_libelle == "COMPTE DE LIAISON"}
    assert "" not in benef and len(benef) >= 2


# ---------------------------------------------------------------------------------------
# Second mois reel : septembre 2026 (09 RC SEPT.xlsx anonymise, jours 09, 18, 24, 25)
# ---------------------------------------------------------------------------------------
SEPT = Path(__file__).parent / "fixtures" / "RC_SEPT_2026_ANONYMISE.xlsx"


@pytest.mark.parametrize("feuille,fact,avoirs,acomptes,recus,h,i,f", [
    ("09", 238, 3, 150, 40, 16206800, 185834025, 124993825),
    ("18", 152, 11, 73, 32, 10043100, 177364600, 124607850),
    ("24", 165, 1, 117, 28, 19013325, 121774450, 82496750),
    ("25", 143, 0, 86, 23, 21312325, 247481745, 115516700)])
def test_septembre_reel(cfg, feuille, fact, avoirs, acomptes, recus, h, i, f):
    r = analyser(cfg, feuille, SEPT, {})
    s = r.stats
    assert (s["factures"], s["avoirs"], s["acomptes"], s["reglements"]) == (fact, avoirs, acomptes, recus)
    ctl = s["controle_totaux"]
    assert (ctl["documents_H"]["retenu"], ctl["documents_I"]["retenu"], ctl["recus_F"]["retenu"]) == (h, i, f)
    assert all(v["rapport"] == v["lignes"] and v["ecart_non_explique"] == 0 for v in ctl.values())


def test_septembre_bc_avec_facture_bloque(cfg):
    r = analyser(cfg, "18", SEPT, {})
    assert any("BCCB031741" in a.motif and a.gravite == "BLOQUANT" for a in r.anomalies)
