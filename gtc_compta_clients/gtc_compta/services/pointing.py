"""Pointage contradictoire avec le client et confirmation de solde.

Distinct du rapprochement interne : CONFIRME_PAR_CLIENT != RAPPROCHE_SAGE.
Aucune ecriture Sage n'est modifiee.
"""
from __future__ import annotations

from datetime import date

from ..db import now_iso
from .auth import Utilisateur, exiger
from .reconciliation import empreinte_ecritures

STATUTS_LIGNE = ("CONFIRME", "CONTESTE", "MANQUANT", "EN_VERIFICATION")


def enregistrer_solde_client(db, user: Utilisateur, sage, ct_num: str, date_arrete: date,
                             solde_client: int, interlocuteur: str, canal: str = "",
                             notes: str = "", preuve: str = "") -> dict:
    exiger(user, "pointage")
    if not interlocuteur.strip():
        raise ValueError("Identite de l'interlocuteur obligatoire")
    ecritures = sage.ecritures_client(ct_num, None, date_arrete)   # SageIndisponible -> exception
    solde_sage = sum(e.signe for e in ecritures)
    ecart = int(solde_client) - solde_sage
    statut = "CONFIRME_PAR_CLIENT" if ecart == 0 else "EN_POINTAGE"
    with db.transaction():
        cur = db.execute(
            "INSERT INTO client_balance_confirmations(ct_num, date_arrete, solde_client, solde_sage, ecart, "
            "interlocuteur, canal, statut, empreinte_sage, notes, preuve, enregistre_le, enregistre_par) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ct_num, date_arrete.isoformat(), int(solde_client), solde_sage, ecart, interlocuteur, canal, statut,
             empreinte_ecritures(0, ecritures), notes, preuve, now_iso(), user.login))
        cid = cur.lastrowid
        if statut == "EN_POINTAGE":
            dern = db.scalar("SELECT MAX(date_arrete) FROM client_balance_confirmations WHERE ct_num=? "
                             "AND statut='CONFIRME_PAR_CLIENT' AND date_arrete<?", (ct_num, date_arrete.isoformat()))
            for e in ecritures:
                if dern and e.date_ecriture.isoformat() <= dern:
                    continue
                db.execute("INSERT INTO client_pointing_lines(confirmation_id, sage_ec_no, date_ecriture, piece, "
                           "libelle, sens, montant) VALUES (?,?,?,?,?,?,?)",
                           (cid, e.ec_no, e.date_ecriture.isoformat(), e.numero_piece, e.libelle, e.sens, e.montant))
        db.audit(user.login, "SOLDE_CLIENT_COMMUNIQUE", ct_num,
                 {"confirmation": cid, "solde_client": solde_client, "solde_sage": solde_sage, "statut": statut})
    return {"id": cid, "statut": statut, "solde_sage": solde_sage, "ecart": ecart}


def maj_ligne(db, user: Utilisateur, ligne_id: int, statut: str, commentaire: str = "") -> None:
    exiger(user, "pointage")
    if statut not in STATUTS_LIGNE:
        raise ValueError(f"Statut inconnu : {statut}")
    with db.transaction():
        db.execute("UPDATE client_pointing_lines SET statut=?, commentaire=?, modifie_le=?, modifie_par=? WHERE id=?",
                   (statut, commentaire, now_iso(), user.login, ligne_id))
        db.audit(user.login, "POINTAGE_LIGNE", str(ligne_id), {"statut": statut, "commentaire": commentaire})


def cloturer(db, user: Utilisateur, confirmation_id: int, statut: str, notes: str = "") -> None:
    exiger(user, "pointage")
    if statut not in ("CONFIRME_PAR_CLIENT", "CONTESTE"):
        raise ValueError("Statut de cloture invalide")
    c = db.one("SELECT * FROM client_balance_confirmations WHERE id=?", (confirmation_id,))
    if statut == "CONFIRME_PAR_CLIENT":
        n = db.scalar("SELECT COUNT(*) FROM client_pointing_lines WHERE confirmation_id=? AND statut<>'CONFIRME'",
                      (confirmation_id,), 0)
        if n:
            raise ValueError(f"{n} ligne(s) non confirmee(s) : confirmation impossible")
    with db.transaction():
        db.execute("UPDATE client_balance_confirmations SET statut=?, notes=COALESCE(notes,'')||? WHERE id=?",
                   (statut, ("\n" + notes) if notes else "", confirmation_id))
        db.audit(user.login, "CLOTURE_POINTAGE", c["ct_num"], {"confirmation": confirmation_id, "statut": statut})


def historique(db, ct_num: str):
    return db.query("SELECT * FROM client_balance_confirmations WHERE ct_num=? ORDER BY date_arrete DESC, id DESC",
                    (ct_num,))


def lignes(db, confirmation_id: int):
    return db.query("SELECT * FROM client_pointing_lines WHERE confirmation_id=? ORDER BY date_ecriture, id",
                    (confirmation_id,))
