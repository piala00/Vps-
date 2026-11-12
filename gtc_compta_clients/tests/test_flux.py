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
from gtc_compta.db import Database
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
    assert rap.inseres == 11 and len(rap.rejets) == 1
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
    assert rap2.inseres == 0 and rap2.deja_presents == 11
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
    av = f.lignes[1]
    assert (av.debit, av.credit) == (-50000, 0)                 # avoir : debit negatif


def test_solde_non_garanti_sans_ouverture(db, user, sage, cfg):
    svc_clients.synchroniser_clients(db, user, sage, [])
    f = fiche_client(db, "CL001")
    assert not f.solde_garanti


def test_cas5_cas6_concordance_et_ecart(base, user, cfg, sage):
    importer(base, user, cfg)
    res = {r.ct_num: r for r in reco.rapprocher(base, user, sage, J1)}
    assert res["CL001"].statut == "VALIDE" and res["CL002"].statut == "VALIDE" and res["CL099"].statut == "VALIDE"
    assert res["CL050"].statut == "VALIDE" and res["CL050"].solde_erp == 60000      # COMPTE DE LIAISON
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


def test_fichier_correspondances_export_import(db, user, sage, cfg, tmp_path):
    from openpyxl import load_workbook
    svc_clients.synchroniser_clients(db, user, sage, cfg["rapport"]["comptes_collectifs"])
    n = svc_clients.exporter_libelles_a_completer(db, cfg["rapport"], DEMO / "RC_DEMO_SYNTHETIQUE.xlsx",
                                                  tmp_path / "c.xlsx")
    assert n == 7                                      # 6 clients connus + NOUVEAU CLIENT X
    wb = load_workbook(tmp_path / "c.xlsx")
    ws = wb["CORRESPONDANCES"]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "ETS ALPHA":
            assert row[1].value is None and row[5].value == "CL001"   # suggestion seulement
            row[1].value = "CL001"
        if row[0].value == "NOUVEAU CLIENT X":
            row[1].value = "CL777"
    wb.save(tmp_path / "c.xlsx")
    ok, err = svc_clients.importer_correspondances_xlsx(db, user, tmp_path / "c.xlsx")
    assert ok == 1 and len(err) == 1 and "CL777" in err[0]
    assert svc_clients.correspondances(db)["ETS ALPHA"] == "CL001"


def test_annulation_recu_liee_jour_precedent(base, user, cfg):
    """Recu fait sur le mauvais compte le 01/10, contre-passe le 02/10 et refait sur le bon compte."""
    def ligne(ref, ct, nom, mt, sens, nature, jour):
        return {"format_version": "GTC-EXPORT-1", "id_import": f"J{jour}", "agence": "BERTOUA",
                "date_rapport": f"2026-10-{jour:02d}", "type_mouvement": nature, "reference_piece": ref,
                "code_tiers": ct, "nom_client": nom, "acheteur_detail": "", "montant": mt, "sens": sens,
                "bc_origine": "", "mode_reference": "", "source_feuille": "x", "source_ligne": 1}
    imports.importer_lot(base, user, [ligne("7RCB100", "CL002", "QUINCAILLERIE BETA", 80000, "C", "REGLEMENT", 1)],
                         "j1", "1")
    rap = imports.importer_lot(base, user, [
        ligne("7RCB101", "CL002", "QUINCAILLERIE BETA", -80000, "C", "REGLEMENT", 2),
        ligne("7RCB102", "CL001", "ETS ALPHA", 80000, "C", "REGLEMENT", 2)], "j2", "2")
    assert rap.inseres == 2
    m = base.one("SELECT * FROM normalized_movements WHERE reference_piece='7RCB101'")
    assert m["reference_liee"] == "7RCB100" and "Annulation recu 7RCB100" in m["libelle"]
    assert (m["sens"], m["montant"]) == ("C", -80000)
    lignes = {l.piece: l for l in fiche_client(base, "CL002", date(2026, 10, 2)).lignes}
    assert (lignes["7RCB101"].debit, lignes["7RCB101"].credit) == (0, -80000)   # credit negatif
    assert fiche_client(base, "CL002", date(2026, 10, 2)).solde_final == 0           # les deux recus s'annulent
    assert fiche_client(base, "CL001", date(2026, 10, 2)).solde_final == 1400000 - 80000
    # un second recu negatif ne peut pas annuler le meme recu
    imports.importer_lot(base, user, [ligne("7RCB103", "CL002", "QUINCAILLERIE BETA", -80000, "C",
                                            "REGLEMENT", 3)], "j3", "3")
    assert base.scalar("SELECT reference_liee FROM normalized_movements WHERE reference_piece='7RCB103'") is None
    assert base.scalar("SELECT COUNT(*) FROM alertes WHERE type='ANNULATION_RECU_A_VERIFIER'") == 1


def test_import_refuse_sens_contraire_a_la_regle(base, user):
    l = {"format_version": "GTC-EXPORT-1", "id_import": "S", "agence": "BERTOUA", "date_rapport": "2026-10-01",
         "type_mouvement": "AVOIR", "reference_piece": "FRCB9", "code_tiers": "CL001", "nom_client": "ETS ALPHA",
         "acheteur_detail": "", "montant": 5000, "sens": "C", "bc_origine": "", "mode_reference": "",
         "source_feuille": "x", "source_ligne": 1}
    rap = imports.importer_lot(base, user, [l], "s", "s")
    assert rap.inseres == 0 and "contraire a la regle" in rap.rejets[0][1]


def test_appariement_independant_de_la_representation_sage(base, user, cfg, sage):
    """L'avoir FRCB0001 est au debit negatif dans l'ERP ; qu'il soit en credit positif (demo) ou en
    debit negatif dans Sage, la fiche est rapprochee."""
    from dataclasses import replace
    sage.ecritures = [replace(e, sens="D", montant=-e.montant) if e.numero_piece == "FRCB0001" else e
                      for e in sage.ecritures]
    importer(base, user, cfg)
    assert next(r for r in reco.rapprocher(base, user, sage, J1) if r.ct_num == "CL001").statut == "VALIDE"


def test_migration_004_convertit_les_anciens_signes(tmp_path):
    """Une base creee avec l'ancienne convention (avoirs et recus negatifs inverses) est convertie."""
    import sqlite3
    from gtc_compta.db import database as dbm
    p = tmp_path / "ancienne.sqlite3"
    anciennes = [m for m in dbm._migrations() if m[0] <= 3]
    cn = sqlite3.connect(p)
    cn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, nom TEXT, applique_le TEXT)")
    for num, name, sql in anciennes:
        for stmt in dbm._split_sql(sql):
            cn.execute(stmt)
        cn.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (num, name, "x"))
    cn.execute("INSERT INTO clients(ct_num, intitule) VALUES ('C1','X')")
    for nat, ref, sens, mt in [("AVOIR", "FRCB1", "C", 500), ("ANNULATION_RECU", "7RCB2", "D", 800),
                               ("FACTURE", "FACB3", "D", 900), ("REGLEMENT", "7RCB4", "C", 300)]:
        cn.execute("INSERT INTO normalized_movements(agence, nature, reference_piece, ct_num, date_piece, sens, "
                   "montant, source, cree_le, cree_par) VALUES ('B',?,?, 'C1', '2026-10-01', ?, ?, 'RAPPORT', 'x', 'x')",
                   (nat, ref, sens, mt))
    cn.commit()
    cn.close()
    d = Database(p)
    rows = {r["reference_piece"]: (r["nature"], r["sens"], r["montant"])
            for r in d.query("SELECT * FROM normalized_movements")}
    assert rows == {"FRCB1": ("AVOIR", "D", -500), "7RCB2": ("REGLEMENT", "C", -800),
                    "FACB3": ("FACTURE", "D", 900), "7RCB4": ("REGLEMENT", "C", 300)}
    assert d.scalar("PRAGMA foreign_keys") == 1


def _ligne_recu(ref, ct, nom, mt, jour, id_import):
    return {"format_version": "GTC-EXPORT-1", "id_import": id_import, "agence": "BERTOUA",
            "date_rapport": f"2026-10-{jour:02d}", "type_mouvement": "REGLEMENT", "reference_piece": ref,
            "code_tiers": ct, "nom_client": nom, "acheteur_detail": "", "montant": mt, "sens": "C",
            "bc_origine": "", "mode_reference": "", "source_feuille": "x", "source_ligne": 1}


def test_recu_negatif_origine_trouvee_dans_sage(base, user, sage):
    """Cas 1 : le recu d'origine est dans Sage sur le meme compte (anterieur au rapport) -> lien etabli."""
    from gtc_compta.services import controles
    imports.importer_lot(base, user, [_ligne_recu("7RCB477", "CL002", "QUINCAILLERIE BETA", -965950, 27, "N")],
                         "n", "n")
    alerte = base.one("SELECT * FROM alertes WHERE type='ANNULATION_RECU_A_VERIFIER'")
    mid = controles.mouvement_de_l_alerte(base, alerte["id"])
    sage.ajouter_ecriture(SageEntry(500, "CL002", "CAI", date(2026, 9, 20), "7RCB399", "7RCB399", "Recu", "C", 965950))
    r = controles.verifier_recu_negatif_dans_sage(base, user, sage, mid)
    assert r["conclusion"] == "ORIGINE_TROUVEE" and r["origine"] == "7RCB399"
    assert base.scalar("SELECT reference_liee FROM normalized_movements WHERE id=?", (mid,)) == "7RCB399"
    assert base.scalar("SELECT statut FROM alertes WHERE id=?", (alerte["id"],)) == "TRAITEE"


def test_recu_negatif_les_deux_recus_sur_le_meme_compte(base, user, sage):
    """Cas 2 : pas de recu anterieur ; le recu positif du jour (autre libelle dans le rapport) et le recu
    negatif sont passes sur le MEME compte Sage -> ils s'annulent, libelles a rattacher."""
    from gtc_compta.services import controles
    imports.importer_lot(base, user, [_ligne_recu("7RCB347", "CL001", "ETS ALPHA", 965950, 27, "P"),
                                      _ligne_recu("7RCB477", "CL002", "QUINCAILLERIE BETA", -965950, 27, "P")],
                         "p", "p")
    sage.ajouter_ecriture(SageEntry(501, "CL002", "CAI", date(2026, 10, 27), "7RCB347", "7RCB347", "Recu", "C", 965950))
    sage.ajouter_ecriture(SageEntry(502, "CL002", "CAI", date(2026, 10, 27), "7RCB477", "7RCB477", "Recu", "C", -965950))
    mid = base.scalar("SELECT id FROM normalized_movements WHERE reference_piece='7RCB477'")
    r = controles.verifier_recu_negatif_dans_sage(base, user, sage, mid)
    assert r["conclusion"] == "MEME_COMPTE" and r["origine"] == "7RCB347"
    assert any("MEME compte" in x for x in r["details"])


def test_recu_negatif_sage_indisponible(base, user, sage):
    from gtc_compta.sage.base import SageIndisponible
    from gtc_compta.services import controles
    imports.importer_lot(base, user, [_ligne_recu("7RCB477", "CL002", "QUINCAILLERIE BETA", -5000, 27, "Q")], "q", "q")
    sage.disponible = False
    with pytest.raises(SageIndisponible):
        controles.verifier_recu_negatif_dans_sage(base, user, sage,
                                                  base.scalar("SELECT id FROM normalized_movements"))


def test_recu_negatif_comptes_differents_a_analyser(base, user, sage):
    """Cas 3 : aucun recu anterieur sur le compte du recu negatif ; le recu positif du jour est sur un autre
    compte Sage -> a analyser par le comptable (aucune modification automatique)."""
    from gtc_compta.services import controles
    imports.importer_lot(base, user, [_ligne_recu("7RCB347", "CL001", "ETS ALPHA", 965950, 27, "R"),
                                      _ligne_recu("7RCB477", "CL002", "QUINCAILLERIE BETA", -965950, 27, "R")],
                         "r", "r")
    sage.ajouter_ecriture(SageEntry(601, "CL001", "CAI", date(2026, 10, 27), "7RCB347", "7RCB347", "Recu", "C", 965950))
    sage.ajouter_ecriture(SageEntry(602, "CL002", "CAI", date(2026, 10, 27), "7RCB477", "7RCB477", "Recu", "C", -965950))
    mid = base.scalar("SELECT id FROM normalized_movements WHERE reference_piece='7RCB477'")
    r = controles.verifier_recu_negatif_dans_sage(base, user, sage, mid)
    assert r["conclusion"] == "A_ANALYSER"
    assert r["comptes"] == {"7RCB477": ["CL002"], "7RCB347": ["CL001"]}
    assert base.scalar("SELECT reference_liee FROM normalized_movements WHERE id=?", (mid,)) is None


def test_septembre_recu_negatif_lie_au_recu_de_la_veille(db, user, cfg):
    """25/09 : 7RCB026463 (-121 800) annule 7RCB026459 du 24/09, meme client (rapport reel anonymise)."""
    from pathlib import Path
    from gtc_compta.sage.base import SageClient
    from gtc_compta.sage.fake import FakeSageAdapter
    from gtc_compta.text import normaliser
    sept = Path(__file__).parent / "fixtures" / "RC_SEPT_2026_ANONYMISE.xlsx"
    res = {f: ParseurRapport(cfg["rapport"], {}).analyser(lire_feuille(sept, f), f, "BERTOUA", None)
           for f in ("24", "25")}
    noms = sorted({normaliser(m.client_libelle) for r in res.values() for m in r.mouvements})
    sage = FakeSageAdapter()
    for k, nom in enumerate(noms):
        sage.ajouter_client(SageClient(f"S{k:03d}", nom))
    svc_clients.synchroniser_clients(db, user, sage, [])
    corr = {nom: f"S{k:03d}" for k, nom in enumerate(noms)}
    for f in ("24", "25"):
        lignes = lignes_export(res[f])
        imports.completer_codes(lignes, corr)
        assert not imports.importer_lot(db, user, lignes, f"sept{f}", f).rejets
    m = db.one("SELECT * FROM normalized_movements WHERE reference_piece='7RCB026463'")
    assert (m["montant"], m["reference_liee"]) == (-121800, "7RCB026459")
    assert db.scalar("SELECT COUNT(*) FROM alertes WHERE type='ANNULATION_RECU_A_VERIFIER'") == 0


# -- Registre des BC et controle des factures comptant ------------------------------------------
def _fc(ref, bc, ct, nom, mt, jour, id_import):
    base = {"format_version": "GTC-EXPORT-1", "id_import": id_import, "agence": "BERTOUA",
            "date_rapport": f"2026-10-{jour:02d}", "reference_piece": ref, "code_tiers": ct, "nom_client": nom,
            "acheteur_detail": "", "montant": mt, "bc_origine": bc, "mode_reference": "COMPTANT",
            "source_feuille": "x", "source_ligne": 1}
    return [dict(base, type_mouvement="FACTURE", sens="D"), dict(base, type_mouvement="ACOMPTE", sens="C")]


def _bon(bc, piece, nom, acompte, bp, jour):
    return {"agence": "BERTOUA", "bc": bc, "piece": piece, "client": nom, "acompte": acompte, "bp": bp,
            "date_rapport": f"2026-10-{jour:02d}", "ligne": 1}


def _alertes_comptant(db):
    return [r["message"] for r in db.query("SELECT message FROM alertes WHERE type='FACTURE_COMPTANT_SANS_ACOMPTE'")]


def test_facture_comptant_acompte_sur_bc_anterieur(base, user):
    imports.enregistrer_bons(base, [_bon("BC100", "BCCB100", "ETS ALPHA", 50000, 0, 1)])
    rap = imports.importer_lot(base, user, _fc("FACB100", "BC100", "CL001", "ETS ALPHA", 50000, 3, "A"), "a", "a")
    assert rap.alertes_comptant == 0 and _alertes_comptant(base) == []


def test_facture_comptant_n_de_bc_d_un_autre_client(base, user):
    imports.enregistrer_bons(base, [_bon("BC200", "BCCB200", "QUINCAILLERIE BETA", 9000, 0, 1),
                                    _bon("BC201", "BCCB201", "ETS ALPHA", 26000, 0, 2)])
    rap = imports.importer_lot(base, user, _fc("FACB200", "BC200", "CL001", "ETS ALPHA", 26000, 3, "B"), "b", "b")
    assert rap.alertes_comptant == 1
    msg = _alertes_comptant(base)[0]
    assert "appartient a un autre client (QUINCAILLERIE BETA)" in msg and "BC probable : BC201" in msg


def test_facture_comptant_issue_d_un_bc_en_bp(base, user):
    imports.enregistrer_bons(base, [_bon("BC300", "BCCB300", "ETS ALPHA", 0, 36450, 24)])
    imports.importer_lot(base, user, _fc("FACB300", "BC300", "CL001", "ETS ALPHA", 36450, 26, "C"), "c", "c")
    assert "BC en BP" in _alertes_comptant(base)[0]


def test_facture_comptant_colonne_b_non_bc_avec_acompte_sur_la_ligne(base, user):
    """Colonne B = 'OLA' (pas un n° de BC) et acompte F = H sur la ligne : pas d'alerte."""
    from gtc_compta.config import DEFAULTS
    from gtc_compta.excel.report_parser import cle_bc
    cle = cle_bc("OLA", "FACB400", DEFAULTS["rapport"])
    assert cle == "PIECE:FACB400"
    imports.enregistrer_bons(base, [_bon(cle, "FACB400", "ETS ALPHA", 1200, 0, 9)])
    imports.importer_lot(base, user, _fc("FACB400", "OLA", "CL001", "ETS ALPHA", 1200, 9, "D"), "d", "d")
    assert _alertes_comptant(base) == []


def test_historique_bons_mois_precedent(base, user, cfg):
    """Charger le registre de septembre (rapport anonymise) sans creer de mouvement."""
    from pathlib import Path
    sept = Path(__file__).parent / "fixtures" / "RC_SEPT_2026_ANONYMISE.xlsx"
    n = imports.charger_historique_bons(base, user, sept, cfg["rapport"], "BERTOUA")
    assert n > 300
    assert base.scalar("SELECT COUNT(*) FROM normalized_movements") == 0
    assert base.scalar("SELECT COUNT(*) FROM bons_commande_rapport WHERE acompte<>0") > 0


def test_recu_negatif_ecrit_avant_le_recu_positif_dans_la_feuille(base, user):
    """Cas reel du 08/08 : le recu negatif (ligne 233) precede dans la feuille le recu qu'il annule
    (ligne 263). Le lien doit etre etabli quel que soit l'ordre."""
    rap = imports.importer_lot(base, user, [
        _ligne_recu("7RCB646", "CL002", "QUINCAILLERIE BETA", -500000, 8, "O"),
        _ligne_recu("7RCB641", "CL002", "QUINCAILLERIE BETA", 500000, 8, "O")], "o", "o")
    assert rap.inseres == 2
    assert base.scalar("SELECT reference_liee FROM normalized_movements WHERE reference_piece='7RCB646'") == "7RCB641"
    assert base.scalar("SELECT COUNT(*) FROM alertes WHERE type='ANNULATION_RECU_A_VERIFIER'") == 0
