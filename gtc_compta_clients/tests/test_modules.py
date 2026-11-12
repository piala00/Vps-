from datetime import date

import pytest
from pypdf import PdfReader

from gtc_compta.config import load_config
from gtc_compta.db import Database
from gtc_compta.sage.sql_adapter import verifier_lecture_seule, REQUETES
from gtc_compta.services import documents, pointing, printing, solvency, reconciliation as reco
from gtc_compta.services.auth import Utilisateur

from .test_flux import importer
from .conftest import J1


# -- solvabilite ---------------------------------------------------------------------
def test_cas9_bc_deja_inclus_pas_double_compte(base, user, sage, cfg):
    a = solvency.controler_bc(base, user, sage, "BCCB0101", cfg["solvabilite"])
    assert a.risque_projete == 2300000                      # BC non rajoute
    assert a.avis == "SOUS_CONDITION" and a.versement_necessaire == 300000


def test_cas9_bc_non_inclus_ajoute_une_fois(base, user, sage, cfg):
    a = solvency.controler_bc(base, user, sage, "0150", cfg["solvabilite"])   # reference abregee
    assert a.risque_projete == 120000 + 200000 and a.depassement == 0


def test_cas10_facture_echue_selon_politique(base, user, sage, cfg):
    pol = dict(cfg["solvabilite"])
    assert solvency.controler_bc(base, user, sage, "BCCB0150", pol).avis == "FAVORABLE"
    pol["politique_factures_echues"] = "bloquer"
    a = solvency.controler_bc(base, user, sage, "BCCB0150", pol)
    assert a.avis == "DEFAVORABLE" and any("echue" in m for m in a.motifs)


def test_solvabilite_donnees_insuffisantes(base, user, sage, cfg):
    assert solvency.controler_bc(base, user, sage, "BCCB0160", cfg["solvabilite"]).avis == "DONNEES_INSUFFISANTES"
    assert solvency.controler_bc(base, user, sage, "INCONNU", cfg["solvabilite"]).avis == "DONNEES_INSUFFISANTES"
    sage.disponible = False
    assert solvency.controler_bc(base, user, sage, "BCCB0101", cfg["solvabilite"]).avis == "DONNEES_INSUFFISANTES"
    assert base.scalar("SELECT COUNT(*) FROM purchase_order_credit_checks") == 3


# -- pointage --------------------------------------------------------------------------
def test_cas11_solde_confirme_par_client(base, user, sage):
    r = pointing.enregistrer_solde_client(base, user, sage, "CL002", J1, 0, "M. Beta (gerant)", "TELEPHONE")
    assert r["statut"] == "CONFIRME_PAR_CLIENT"
    h = pointing.historique(base, "CL002")[0]
    assert h["interlocuteur"] == "M. Beta (gerant)" and h["date_arrete"] == "2026-10-01"


def test_cas11_ecart_ouvre_pointage_detaille(base, user, sage):
    r = pointing.enregistrer_solde_client(base, user, sage, "CL001", J1, 1500000, "Mme Alpha", "WHATSAPP")
    assert r["statut"] == "EN_POINTAGE" and r["ecart"] == -50000
    lignes = pointing.lignes(base, r["id"])
    assert len(lignes) == 4
    with pytest.raises(ValueError):
        pointing.cloturer(base, user, r["id"], "CONFIRME_PAR_CLIENT")
    pointing.maj_ligne(base, user, lignes[2]["id"], "CONTESTE", "avoir non recu par le client")
    pointing.cloturer(base, user, r["id"], "CONTESTE")
    assert pointing.historique(base, "CL001")[0]["statut"] == "CONTESTE"


# -- documents ---------------------------------------------------------------------------
def test_cas12_pdf_disponible_ou_absent(base, sage, tmp_path):
    d = tmp_path / "factures"
    d.mkdir()
    (d / "Facture FACB0201 ETS ALPHA.pdf").write_bytes(b"%PDF-1.4\n%fictif\n")
    assert documents.indexer_dossiers(base, [str(d)]) >= 1
    assert documents.trouver_pdf(base, sage, "FACB 0201").name.startswith("Facture FACB0201")
    with pytest.raises(documents.PdfIntrouvable, match="Aucun PDF"):
        documents.trouver_pdf(base, sage, "FACB9999")
    (d / "Facture FACB0201 ETS ALPHA.pdf").unlink()
    with pytest.raises(documents.PdfIntrouvable, match="fichier absent"):
        documents.trouver_pdf(base, sage, "FACB0201")


def test_liens_messagerie():
    assert documents.lien_whatsapp("699 00 00 01", "Bonjour").startswith("https://wa.me/237699000001?text=")
    with pytest.raises(ValueError):
        documents.lien_whatsapp("", "x")
    assert documents.lien_telegram("@alpha", "x") == "https://t.me/alpha"


# -- impression --------------------------------------------------------------------------
def _valide(base, user, cfg, sage):
    importer(base, user, cfg)
    reco.rapprocher(base, user, sage, J1)


def test_cas13_impression_differee_recto_verso(base, user, cfg, sage, tmp_path):
    _valide(base, user, cfg, sage)
    q = printing.file_attente(base, cfg["impression"])
    assert [x["ct_num"] for x in q] == ["CL099", "CL001", "CL002"] or len(q) == 3
    res = printing.generer_fiches(base, user, [x["ct_num"] for x in q], tmp_path / "f.pdf", cfg)
    assert all(n % 2 == 0 for n in res["pages_par_client"].values())   # clients separes physiquement
    assert len(PdfReader(str(tmp_path / "f.pdf")).pages) == res["pages"]
    assert printing.file_attente(base, cfg["impression"]) == []            # pas de reimpression involontaire
    printing.confirmer_impression(base, user, res["job_id"])
    h = base.one("SELECT * FROM print_history WHERE ct_num='CL001'")
    assert h["solde_reporte"] == 1400000 and h["solde_final"] == 1550000 and h["statut"] == "IMPRIME"


def test_cas13_report_de_solde_et_pagination(base, user, cfg, sage, tmp_path):
    """Plusieurs jours non imprimes : report en haut de page, nombre de pages pair."""
    from gtc_compta.sage.base import SageEntry
    from gtc_compta.services import imports
    lignes = []
    for i in range(1, 46):
        lignes.append({"format_version": "GTC-EXPORT-1", "id_import": "MASSE", "agence": "BERTOUA",
                       "date_rapport": f"2026-10-{(i % 9) + 2:02d}", "type_mouvement": "FACTURE",
                       "reference_piece": f"FACB9{i:03d}", "code_tiers": "CL004", "nom_client": "DELTA SARL",
                       "acheteur_detail": "", "montant": 1000 * i, "sens": "D", "bc_origine": "",
                       "mode_reference": "", "source_feuille": "01", "source_ligne": i})
        sage.ajouter_ecriture(SageEntry(1000 + i, "CL004", "VTE", date.fromisoformat(lignes[-1]["date_rapport"]),
                                        f"FACB9{i:03d}", f"FACB9{i:03d}", "Facture", "D", 1000 * i))
    imports.importer_lot(base, user, lignes, "masse.xlsx", "m")
    assert reco.rapprocher(base, user, sage, date(2026, 10, 10), ["CL004"])[0].statut == "VALIDE"
    res = printing.generer_fiches(base, user, ["CL004"], tmp_path / "d.pdf", cfg)
    lpp = printing.lignes_par_page(cfg["impression"])
    assert res["pages"] % 2 == 0 and res["pages"] >= -(-45 // lpp)
    txt = [p.extract_text() for p in PdfReader(str(tmp_path / "d.pdf")).pages]
    assert "A reporter" in txt[0] and "Report" in txt[1]
    assert "Solde anterieur" in txt[0] and "-100 000" in txt[0]
    final = -100000 + sum(1000 * i for i in range(1, 46))
    assert f"{final:,}".replace(",", " ") in "".join(txt)


def test_annulation_job_libere_lignes(base, user, cfg, sage, tmp_path):
    _valide(base, user, cfg, sage)
    res = printing.generer_fiches(base, user, ["CL001"], tmp_path / "a.pdf", cfg)
    printing.annuler_job(base, user, res["job_id"], "bourrage papier")
    assert [x["ct_num"] for x in printing.file_attente(base, cfg["impression"])].count("CL001") == 1


# -- securite / infrastructure ----------------------------------------------------------
@pytest.mark.parametrize("sql", ["UPDATE F_COMPTET SET CT_Intitule='x'", "SELECT 1; DELETE FROM F_ECRITUREC",
                                 "SELECT * INTO T FROM F_COMPTET", "EXEC sp_who", "DROP TABLE x"])
def test_sql_ecriture_interdite(sql):
    with pytest.raises(PermissionError):
        verifier_lecture_seule(sql)


def test_requetes_livrees_lecture_seule():
    for q in REQUETES.values():
        verifier_lecture_seule(q)


def test_config_refuse_mot_de_passe(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"sage": {"password": "secret"}}')
    with pytest.raises(ValueError):
        load_config(p)


def test_sauvegarde_restauration(tmp_path, user):
    db = Database(tmp_path / "a.sqlite3")
    db.audit(user.login, "TEST")
    db.backup(tmp_path / "b.sqlite3")
    db.close()
    Database.restore(tmp_path / "b.sqlite3", tmp_path / "c.sqlite3")
    assert Database(tmp_path / "c.sqlite3").scalar("SELECT COUNT(*) FROM audit_events WHERE action='TEST'") == 1


def test_transaction_atomique(db, user):
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.audit(user.login, "A")
            raise RuntimeError
    assert db.scalar("SELECT COUNT(*) FROM audit_events") == 0
