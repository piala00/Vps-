"""Registre des anomalies CR : aucune erreur de rapport ne doit fausser un solde en silence."""
from datetime import date

import pytest

from gtc_compta.excel.preparation import anomalies_export, bons_export, lignes_export
from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
from gtc_compta.services import anomalies as reg
from gtc_compta.services import clients as svc_clients
from gtc_compta.services import imports
from gtc_compta.services.ledger import fiche_client

from .conftest import CORR, DEMO


def importer_jour(db, user, cfg, feuille):
    r = ParseurRapport(cfg["rapport"], svc_clients.correspondances(db)).analyser(
        lire_feuille(DEMO / "RC_DEMO_SYNTHETIQUE.xlsx", feuille), feuille, "BERTOUA", None)
    lignes = lignes_export(r)
    return imports.importer_lot(db, user, lignes, f"j{feuille}", "x", bons=bons_export(r), anomalies=anomalies_export(r))


def codes_ouverts(db):
    return sorted(r["code"] for r in reg.lister(db, "OUVERTE"))


def test_anomalies_du_rapport_conservees_jusqu_a_resolution(base, user, cfg):
    importer_jour(base, user, cfg, "02")
    assert codes_ouverts(base) == sorted(["MONTANTS_H_I_DIFFERENTS", "BC_AVEC_FACTURE", "RECU_NEGATIF_SANS_ORIGINE"])
    n, mt = reg.resume_client(base, "CL003")                     # SOCIETE GAMMA : 2 lignes bloquees
    assert (n, mt) == (2, 90000 + 40000)                         # H/I incoherents (H 90 000) + BC0300 (40 000)


def test_integration_d_une_facture_corrigee(base, user, cfg):
    importer_jour(base, user, cfg, "02")
    a = next(r for r in reg.lister(base) if r["code"] == "BC_AVEC_FACTURE")
    avant = fiche_client(base, "CL003").solde_final
    mid = reg.integrer_facture_corrigee(base, user, a["id"], "FACB0300")
    m = base.one("SELECT * FROM normalized_movements WHERE id=?", (mid,))
    assert (m["nature"], m["sens"], m["montant"], m["source"]) == ("FACTURE", "D", 40000, "CORRECTION_CR")
    assert fiche_client(base, "CL003").solde_final == avant + 40000          # facture a terme : pas d'acompte
    assert base.one("SELECT statut FROM anomalies_cr WHERE id=?", (a["id"],))[0] == "RESOLUE"
    with pytest.raises(ValueError):
        reg.integrer_facture_corrigee(base, user, a["id"], "FACB0300")       # deja traitee


def _l(ref, ct, nom, mt, jour, nature="REGLEMENT", sens="C", idi="L"):
    return {"format_version": "GTC-EXPORT-1", "id_import": f"{idi}{jour}", "agence": "BERTOUA",
            "date_rapport": f"2026-10-{jour:02d}", "type_mouvement": nature, "reference_piece": ref,
            "code_tiers": ct, "nom_client": nom, "acheteur_detail": "", "montant": mt, "sens": sens,
            "bc_origine": "", "mode_reference": "", "source_feuille": f"{jour:02d}", "source_ligne": 5}


def test_meme_recu_saisi_deux_jours_meme_client(base, user):
    imports.importer_lot(base, user, [_l("7RCB900", "CL001", "ETS ALPHA", 70000, 1)], "a", "a")
    rap = imports.importer_lot(base, user, [_l("7RCB900", "CL001", "ETS ALPHA", 70000, 2)], "b", "b")
    assert rap.inseres == 0 and rap.deja_presents == 1                        # jamais compte deux fois
    a = base.one("SELECT * FROM anomalies_cr WHERE code='PIECE_SAISIE_DEUX_FOIS'")
    assert a is not None and a["statut"] == "INFORMATION" and "2026-10-01" in a["motif"]


def test_meme_numero_de_recu_pour_deux_clients_jours_differents(base, user):
    imports.importer_lot(base, user, [_l("7RCB901", "CL001", "ETS ALPHA", 70000, 1)], "a", "a")
    imports.importer_lot(base, user, [_l("7RCB901", "CL002", "QUINCAILLERIE BETA", 25000, 3)], "b", "b")
    a = base.one("SELECT * FROM anomalies_cr WHERE code='NUMERO_PLUSIEURS_CLIENTS'")
    assert a["statut"] == "OUVERTE" and a["impact_solde"] == 1 and a["ct_num"] == "CL002"


def test_montant_different_pour_une_piece_deja_saisie(base, user):
    imports.importer_lot(base, user, [_l("7RCB902", "CL001", "ETS ALPHA", 70000, 1)], "a", "a")
    imports.importer_lot(base, user, [_l("7RCB902", "CL001", "ETS ALPHA", 75000, 2)], "b", "b")
    a = base.one("SELECT * FROM anomalies_cr WHERE code='CONFLIT_MONTANT'")
    assert a["statut"] == "OUVERTE" and "70000 au lieu de 75000" in a["motif"]


def test_ligne_rejetee_puis_reintegree_apres_correspondance(base, user, cfg):
    rap = importer_jour(base, user, cfg, "01")                    # NOUVEAU CLIENT X : sans code tiers
    assert len(rap.rejets) == 1
    assert "CLIENT_SANS_CORRESPONDANCE" in codes_ouverts(base)
    base.execute("INSERT INTO clients(ct_num, intitule) VALUES ('CL777', 'NOUVEAU CLIENT X')")
    svc_clients.definir_correspondance(base, user, "NOUVEAU CLIENT X", "CL777")
    r = reg.reintegrer_rejets(base, user)
    assert r == {"integrees": 1, "toujours_rejetees": 0}
    assert fiche_client(base, "CL777").solde_final == 75000
    assert "CLIENT_SANS_CORRESPONDANCE" not in codes_ouverts(base)
    assert reg.reintegrer_rejets(base, user)["integrees"] == 0              # pas de double integration


def test_anomalie_resolue_automatiquement_quand_l_import_lie_le_recu(base, user):
    """Le parseur signale le recu negatif (pas d'original dans la journee) ; l'import le lie a la veille."""
    imports.importer_lot(base, user, [_l("7RCB910", "CL002", "QUINCAILLERIE BETA", 60000, 1)], "a", "a")
    ano = {"agence": "BERTOUA", "date_rapport": "2026-10-02", "feuille": "02", "ligne": 9,
           "code": "RECU_NEGATIF_SANS_ORIGINE", "gravite": "AVERTISSEMENT", "impact_solde": True,
           "motif": "Recu negatif 7RCB911 ...", "client": "QUINCAILLERIE BETA", "reference": "7RCB911",
           "montant": -60000, "colonne": "F"}
    imports.importer_lot(base, user, [_l("7RCB911", "CL002", "QUINCAILLERIE BETA", -60000, 2)], "b", "b",
                         anomalies=[ano])
    a = base.one("SELECT * FROM anomalies_cr WHERE reference='7RCB911'")
    assert a["statut"] == "RESOLUE" and "7RCB910" in a["resolution"]


def test_ignorer_exige_un_motif(base, user, cfg):
    importer_jour(base, user, cfg, "02")
    a = reg.lister(base)[0]
    with pytest.raises(ValueError):
        reg.ignorer(base, user, a["id"], " ")
    reg.ignorer(base, user, a["id"], "verifie avec le commercial")
    assert base.one("SELECT statut, resolu_par FROM anomalies_cr WHERE id=?", (a["id"],))[:] == ("IGNOREE", "compta1")


def test_catalogue_couvre_toutes_les_anomalies_reelles(cfg):
    """Toutes les anomalies des jours reels anonymises ont un code du catalogue (aucune 'AUTRE')."""
    from pathlib import Path
    fx = Path(__file__).parent / "fixtures"
    for fic, feuilles in (("RC_OCT_2026_ANONYMISE.xlsx", ("01", "03", "12", "14")),
                          ("RC_SEPT_2026_ANONYMISE.xlsx", ("09", "18", "24", "25")),
                          ("RC_AOUT_2026_ANONYMISE.xlsx", ("04", "08", "11"))):
        for f in feuilles:
            r = ParseurRapport(cfg["rapport"], {}).analyser(lire_feuille(fx / fic, f), f, "B", None)
            assert all(a.code and a.code != "AUTRE" for a in r.anomalies)


# -- Cas reels d'avril a juillet 2026 (rapports anonymises) ---------------------------------------
def _reel(cfg, fichier, feuille):
    from pathlib import Path
    fx = Path(__file__).parent / "fixtures" / fichier
    return ParseurRapport(cfg["rapport"], {}).analyser(lire_feuille(fx, feuille), feuille, "BERTOUA", None)


def _codes(r):
    return [a.code for a in r.anomalies]


def test_reel_avril_recus_au_numero_tronque_7RC(cfg):
    """10/04 : 7RC009311 (4 000 000) et 7RC009273 (3 000 000) -> repris, signales ; plus de montant non explique."""
    r = _reel(cfg, "RC_AVR_2026_ANONYMISE.xlsx", "10")
    assert {"7RC009311", "7RC009273"} <= {m.reference_piece for m in r.reglements}
    assert _codes(r).count("NUMERO_MAL_SAISI") == 2
    assert all(v["ecart_non_explique"] == 0 for v in r.stats["controle_totaux"].values())


def test_reel_avril_facture_annulee_compensee_par_avoir(cfg):
    """24/04 : FACB014784 (+9 641 000) et FRCB000286 (-9 641 000) ANNULEE -> reprises toutes les deux."""
    r = _reel(cfg, "RC_AVR_2026_ANONYMISE.xlsx", "24")
    pieces = {m.reference_piece: m.montant for m in r.factures}
    assert pieces["FACB014784"] == 9641000 and pieces["FRCB000286"] == -9641000
    assert "FACTURE_ANNULEE_PAR_AVOIR" in _codes(r) and "ANNULEE_AVEC_MONTANT" not in _codes(r)


def test_reel_mai_avoir_au_prefixe_tronque_FRC(cfg):
    r = _reel(cfg, "RC_MAI_2026_ANONYMISE.xlsx", "29")
    av = next(m for m in r.factures if m.reference_piece == "FRC000378")
    assert (av.nature, av.sens, av.montant) == ("AVOIR", "D", -4250)
    assert "NUMERO_MAL_SAISI" in _codes(r)


def test_reel_mai_trois_numeros_de_facture_pour_deux_clients(cfg):
    r = _reel(cfg, "RC_MAI_2026_ANONYMISE.xlsx", "18")
    assert _codes(r).count("NUMERO_PLUSIEURS_CLIENTS") == 6          # FACB017927, 017928, 017929


def test_reel_juin_facture_saisie_en_comptant_et_en_vat(cfg):
    """17/06 : FACB021708 (189 000) en H ET en I -> une seule facture (H, acompte present) ; signale."""
    r = _reel(cfg, "RC_JUIN_2026_ANONYMISE.xlsx", "17")
    f = [m for m in r.factures if m.reference_piece == "FACB021708"]
    assert len(f) == 1 and f[0].colonne == "H" and f[0].montant == 189000
    assert "MONTANT_H_ET_I" in _codes(r) and "FACTURE_SANS_NUMERO" in _codes(r)
    assert all(v["ecart_non_explique"] == 0 for v in r.stats["controle_totaux"].values())


def test_reel_juin_commentaire_a_la_place_du_client(cfg):
    r = _reel(cfg, "RC_JUIN_2026_ANONYMISE.xlsx", "23")
    assert "CLIENT_LIBELLE_COMMENTAIRE" in _codes(r)


def test_reel_juillet_numero_de_preparation_de_livraison(cfg):
    r = _reel(cfg, "RC_JUIL_2026_ANONYMISE.xlsx", "11")
    assert any(a.code == "BC_AVEC_FACTURE" and "PLCB002148" in a.motif for a in r.anomalies)


def test_date_feuille_du_modele_non_mise_a_jour(cfg):
    """Mai 2026 : toutes les feuilles portaient une date d'avril (A4) -> anomalie bloquante DATE_FEUILLE."""
    r = ParseurRapport(cfg["rapport"], {}).analyser(
        lire_feuille(__import__("pathlib").Path(__file__).parent / "fixtures" / "RC_MAI_2026_ANONYMISE.xlsx", "18"),
        "18", "BERTOUA", date(2026, 5, 18))
    assert r.date_feuille == date(2026, 4, 18) and r.date_rapport == date(2026, 5, 18)
    assert any(a.code == "DATE_FEUILLE" and a.gravite == "BLOQUANT" for a in r.anomalies)
