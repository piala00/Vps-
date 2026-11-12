"""Parcours complet : import -> ventilation -> rapprochement -> fiche -> impression."""
import json
from datetime import date

import pytest

from gtc_compta.excel.preparation import lignes_export
from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
from gtc_compta.sage.base import SageEntry
from gtc_compta.services import clients as svc_clients
from gtc_compta.services import imports, reconciliation as reco
from gtc_compta.services.auth import AccesRefuse, Utilisateur
from gtc_compta.services.ledger import fiche_client

from .conftest import CORR, DEMO, J1


def lignes_jour(cfg, feuille="01"):
    rows = lire_feuille(DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", feuille)
    r = ParseurRapport(cfg["rapport"], CORR).analyser(rows, feuille, "BERTOUA", date(2026, 10, int(feuille)))
    return lignes_export(r)


def importer(db, user, cfg, feuille="01"):
    return imports.importer_lot(db, user, lignes_jour(cfg, feuille), f"jour{feuille}.xlsx", "x")


def test_import_et_rejet_client_non_mappe(base, user, cfg):
    rap = importer(base, user, cfg)
    assert rap.inseres == 8 and len(rap.rejets) == 1
    assert "Code tiers absent" in rap.rejets[0][1]


def test_cas3_reimport_zero_doublon(base, user, cfg):
    importer(base, user, cfg)
    n = base.scalar("SELECT COUNT(*) FROM normalized_movements")
    rap = importer(base, user, cfg)
    assert rap.deja_importe and rap.inseres == 0
    lignes = lignes_jour(cfg)
    for l in lignes:
        l["id_import"] = "AUTRE-FICHIER"
    rap2 = imports.importer_lot(base, user, lignes, "copie.xlsx", "y")
    assert rap2.inseres == 0 and rap2.deja_presents == 8
    assert base.scalar("SELECT COUNT(*) FROM normalized_movements") == n


def test_cas3_montant_modifie_conflit_sans_doublon(base, user, cfg):
    importer(base, user, cfg)
    lignes = lignes_jour(cfg)
    for l in lignes:
        l["id_import"] = "CORRIGE"
        if l["reference_piece"] == "FACB0201":
            l["montant"] = 510000
    rap = imports.importer_lot(base, user, lignes, "corrige.xlsx", "z")
    assert rap.conflits == 1 and rap.inseres == 0
    assert base.scalar("SELECT COUNT(*) FROM normalized_movements WHERE reference_piece='FACB0201'") == 1


def test_cas4_solde_progressif(base, user, cfg):
    importer(base, user, cfg)
    f = fiche_client(base, "CL001", J1)
    assert f.solde_garanti and f.solde_ouverture == 1400000
    assert [(l.piece, l.solde) for l in f.lignes] == [("FACB0201", 1900000), ("FRCB0001", 1850000),
                                                     ("7RCB0451", 1550000)]


def test_solde_non_garanti_sans_ouverture(db, user, sage, cfg):
    svc_clients.synchroniser_clients(db, user, sage, [])
    f = fiche_client(db, "CL001")
    assert not f.solde_garanti


def test_cas5_cas6_concordance_et_ecart(base, user, cfg, sage):
    importer(base, user, cfg)
    res = {r.ct_num: r for r in reco.rapprocher(base, user, sage, J1)}
    assert res["CL001"].statut == "VALIDE" and res["CL002"].statut == "VALIDE" and res["CL099"].statut == "VALIDE"
    r = base.one("SELECT * FROM daily_reconciliations WHERE ct_num='CL001' AND obsolete=0")
    preuve = json.loads(r["preuve_json"])
    assert r["valide_par"] == "AUTO:compta1" and r["empreinte_sage"] and preuve["nb_ecritures_sage"] == 3
    assert base.scalar("SELECT COUNT(*) FROM normalized_movements WHERE ct_num='CL001' AND statut='VALIDE'") == 3
    g = res["CL003"]
    assert g.statut == "ECART_A_ANALYSER" and g.ecart == -25000
    assert [e["type"] for e in g.ecarts] == ["SAGE_ABSENT_ERP"]
    assert base.scalar("SELECT COUNT(*) FROM normalized_movements WHERE ct_num='CL003' AND statut='VALIDE'") == 0


def test_cas7_sage_indisponible(base, user, cfg, sage):
    importer(base, user, cfg)
    sage.disponible = False
    res = reco.rapprocher(base, user, sage, J1)
    assert {r.statut for r in res} == {"EN_ATTENTE_SAGE"}
    assert base.scalar("SELECT COUNT(*) FROM daily_reconciliations WHERE statut IN ('VALIDE','RAPPROCHE')") == 0


def test_operateur_ne_valide_pas_automatiquement(base, operateur, cfg, sage):
    importer(base, operateur, cfg)
    res = {r.ct_num: r for r in reco.rapprocher(base, operateur, sage, J1)}
    assert res["CL001"].statut == "RAPPROCHE"
    with pytest.raises(AccesRefuse):
        reco.valider_fiche(base, operateur, res["CL001"].reconciliation_id)


def test_cas8_ecriture_diverse_reprise_option_a(base, user, cfg, sage):
    importer(base, user, cfg)
    g = next(r for r in reco.rapprocher(base, user, sage, J1) if r.ct_num == "CL003")
    disc = reco.ecarts_ouverts(base, g.reconciliation_id)[0]
    assert disc["journal"] == "OD" and disc["numero_piece"] == "OD0007"
    with pytest.raises(ValueError):
        reco.reprendre_ecriture_sage(base, user, disc["id"], "  ")
    mid = reco.reprendre_ecriture_sage(base, user, disc["id"], "Frais transport refactures valides", "OD0007")
    with pytest.raises(ValueError):
        reco.reprendre_ecriture_sage(base, user, disc["id"], "encore")   # deja resolu : pas de double
    g2 = reco.rapprocher(base, user, sage, J1, ["CL003"])[0]
    assert g2.statut == "VALIDE" and g2.ecart == 0
    m = base.one("SELECT * FROM normalized_movements WHERE id=?", (mid,))
    assert m["sage_ec_no"] == 16 and m["source"] == "SAGE_COMPLEMENT"
    assert base.scalar("SELECT COUNT(*) FROM audit_events WHERE action='REPRISE_ECRITURE_SAGE'") == 1


def test_option_b_ne_force_pas_egalite(base, user, cfg, sage):
    importer(base, user, cfg)
    g = next(r for r in reco.rapprocher(base, user, sage, J1) if r.ct_num == "CL003")
    disc = reco.ecarts_ouverts(base, g.reconciliation_id)[0]
    reco.resoudre_ecart(base, user, disc["id"], "OPTION_B_FACTURE_GESCOM", "A facturer via Gescom")
    assert reco.rapprocher(base, user, sage, J1, ["CL003"])[0].statut == "ECART_A_ANALYSER"


def test_cas14_ecriture_retroactive(base, user, cfg, sage):
    importer(base, user, cfg)
    reco.rapprocher(base, user, sage, J1)
    sage.ajouter_ecriture(SageEntry(99, "CL001", "OD", date(2026, 10, 1), "OD0099", "", "Regularisation", "D", 1000))
    alertes = reco.verifier_retroactivite(base, user, sage)
    assert [a["ct_num"] for a in alertes] == ["CL001"]
    r = base.one("SELECT statut FROM daily_reconciliations WHERE ct_num='CL001' AND obsolete=0")
    assert r[0] == "A_RAPPROCHER"
    assert base.scalar("SELECT COUNT(*) FROM alertes WHERE type='ECRITURE_RETROACTIVE'") == 1


def test_correction_tracee_invalide_fiche(base, user, cfg, sage):
    importer(base, user, cfg)
    reco.rapprocher(base, user, sage, J1)
    mid = base.scalar("SELECT id FROM normalized_movements WHERE reference_piece='FACB0201'")
    new = imports.corriger_mouvement(base, user, mid, "Erreur de saisie", montant=510000)
    assert base.scalar("SELECT statut FROM normalized_movements WHERE id=?", (mid,)) == "ANNULE"
    assert base.scalar("SELECT remplace_id FROM normalized_movements WHERE id=?", (new,)) == mid
    assert base.scalar("SELECT statut FROM daily_reconciliations WHERE ct_num='CL001' AND obsolete=0") == "A_RAPPROCHER"


def test_champs_manuels_survivent_synchro(base, user, sage, cfg):
    svc_clients.maj_champs_manuels(base, user, "CL001", zone="CENTRE-VILLE", delai_reglement_jours="30")
    svc_clients.synchroniser_clients(base, user, sage, cfg["rapport"]["comptes_collectifs"])
    row = svc_clients.lister_clients(base, "CL001")[0]
    assert row["zone"] == "CENTRE-VILLE" and row["delai_reglement_jours"] == 30


def test_correspondance_jamais_automatique_sur_ressemblance(base):
    sugg = svc_clients.suggestions_correspondance(base, "ETS ALFA")
    assert sugg[0][0] == "CL001"
    assert svc_clients.correspondances(base).get("ETS ALFA") is None


def test_permissions(base):
    op = Utilisateur("x", "x", "operateur")
    with pytest.raises(AccesRefuse):
        svc_clients.definir_correspondance(base, op, "A", "CL001")
