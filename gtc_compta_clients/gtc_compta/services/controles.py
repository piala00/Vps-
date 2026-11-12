"""Controles assistes en lecture seule dans Sage.

Recu negatif sans recu d'origine (alerte ANNULATION_RECU_A_VERIFIER) - procedure de la comptabilite :
1) chercher dans Sage, sur le compte qui porte le recu negatif, un recu ANTERIEUR de meme montant :
   s'il existe, la logique est confirmee (le recu negatif l'annule) et le lien est enregistre ;
2) sinon, rechercher dans quels comptes Sage ont ete passes le recu negatif et les recus positifs de
   meme montant du meme jour (reaffectation possible), et presenter le resultat au comptable.
Rien n'est jamais ecrit dans Sage.
"""
from __future__ import annotations

from ..db import now_iso
from .auth import Utilisateur, exiger


def _recu_negatif(db, movement_id):
    m = db.one("SELECT * FROM normalized_movements WHERE id=?", (movement_id,))
    if m is None or m["nature"] != "REGLEMENT" or m["montant"] >= 0:
        raise ValueError("Le mouvement n'est pas un recu negatif")
    return m


def mouvement_de_l_alerte(db, alerte_id) -> int:
    a = db.one("SELECT * FROM alertes WHERE id=?", (alerte_id,))
    if a is None or a["type"] != "ANNULATION_RECU_A_VERIFIER":
        raise ValueError("Selectionner une alerte de type ANNULATION_RECU_A_VERIFIER")
    ref = a["message"].split(" : ", 1)[0].strip()
    mid = db.scalar("SELECT id FROM normalized_movements WHERE reference_piece=? AND ct_num=? AND nature='REGLEMENT' "
                    "AND montant<0 AND statut<>'ANNULE'", (ref, a["ct_num"]))
    if mid is None:
        raise ValueError(f"Recu negatif {ref} introuvable dans les mouvements")
    return mid


def verifier_recu_negatif_dans_sage(db, user: Utilisateur, sage, movement_id: int) -> dict:
    exiger(user, "reprise_sage")
    from datetime import date
    m = _recu_negatif(db, movement_id)
    montant = -m["montant"]
    d = date.fromisoformat(m["date_piece"])
    lignes = [f"Recu negatif {m['reference_piece']} du {d:%d/%m/%Y} sur {m['ct_num']} : {m['montant']}"]

    # 1) recu d'origine sur le meme compte dans Sage (credit de meme montant, anterieur ou du jour)
    deja = {r[0] for r in db.query("SELECT reference_liee FROM normalized_movements WHERE nature='REGLEMENT' "
                                   "AND montant<0 AND reference_liee IS NOT NULL AND statut<>'ANNULE' AND id<>?",
                                   (movement_id,))}
    ecr = sage.ecritures_client(m["ct_num"], None, d)
    origines = [e for e in ecr if e.signe == -montant and e.numero_piece != m["reference_piece"]
                and e.numero_piece not in deja]
    if origines:
        o = sorted(origines, key=lambda e: (e.date_ecriture, e.ec_no))[-1]
        lignes.append(f"Recu d'origine trouve dans Sage sur le meme compte : {o.numero_piece} du "
                      f"{o.date_ecriture:%d/%m/%Y} ({o.journal}, {o.montant}) -> logique confirmee")
        ailleurs = db.one("SELECT ct_num FROM normalized_movements WHERE reference_piece=? AND nature='REGLEMENT' "
                          "AND statut<>'ANNULE' AND ct_num<>?", (o.numero_piece, m["ct_num"]))
        if ailleurs:
            # Le recu d'origine est dans Sage sur ce compte, mais le rapport l'a ecrit sous un autre libelle.
            lignes.append(f"ATTENTION : dans le rapport, {o.numero_piece} est ecrit au nom d'un autre client "
                          f"(code {ailleurs[0]}). Les deux libelles designent le MEME compte Sage {m['ct_num']} : "
                          "rattacher les deux libelles au meme code tiers dans les correspondances.")
            with db.transaction():
                db.audit(user.login, "CONTROLE_RECU_NEGATIF", m["reference_piece"],
                         {"conclusion": "MEME_COMPTE", "origine": o.numero_piece, "libelle_erp": ailleurs[0]})
            return {"conclusion": "MEME_COMPTE", "origine": o.numero_piece,
                    "comptes": {o.numero_piece: [m["ct_num"]], m["reference_piece"]: [m["ct_num"]]},
                    "details": lignes}
        with db.transaction():
            db.execute("UPDATE normalized_movements SET reference_liee=?, libelle=? WHERE id=?",
                       (o.numero_piece, f"Annulation recu {o.numero_piece} (compte errone)", movement_id))
            _clore_alerte(db, m, f"origine {o.numero_piece} trouvee dans Sage")
            db.audit(user.login, "CONTROLE_RECU_NEGATIF", m["reference_piece"],
                     {"conclusion": "ORIGINE_TROUVEE", "origine": o.numero_piece, "ec_no": o.ec_no})
        return {"conclusion": "ORIGINE_TROUVEE", "origine": o.numero_piece, "details": lignes}

    # 2) dans quels comptes les recus ont-ils ete passes ?
    lignes.append("Aucun recu anterieur de meme montant sur ce compte dans Sage.")
    candidats = [r[0] for r in db.query(
        "SELECT reference_piece FROM normalized_movements WHERE nature='REGLEMENT' AND montant=? AND date_piece=? "
        "AND statut<>'ANNULE' AND id<>?", (montant, m["date_piece"], movement_id))]
    comptes = {}
    for ref in [m["reference_piece"]] + candidats:
        trouves = sage.ecritures_par_piece(ref)
        comptes[ref] = sorted({e.ct_num for e in trouves})
        if trouves:
            for e in trouves:
                lignes.append(f"  {ref} passe dans Sage sur le compte {e.ct_num} le {e.date_ecriture:%d/%m/%Y} "
                              f"({'credit' if e.sens == 'C' else 'debit'} {e.montant})")
        else:
            lignes.append(f"  {ref} : aucune ecriture trouvee dans Sage")
    compte_neg = set(comptes[m["reference_piece"]])
    meme = [ref for ref in candidats if compte_neg and compte_neg & set(comptes[ref])]
    if meme:
        conclusion = "MEME_COMPTE"
        lignes.append(f"Le recu negatif et {', '.join(meme)} sont passes sur le MEME compte Sage "
                      f"({', '.join(sorted(compte_neg))}) : ils s'annulent. Les libelles du rapport different ; "
                      "rattacher les deux libelles au meme code tiers dans les correspondances.")
    elif not compte_neg:
        conclusion = "NON_COMPTABILISE"
        lignes.append("Le recu negatif n'est pas (encore) comptabilise dans Sage : verifier la mise a jour comptable.")
    else:
        conclusion = "A_ANALYSER"
        lignes.append("Les recus sont sur des comptes differents : determiner le compte du recu annule.")
    with db.transaction():
        db.audit(user.login, "CONTROLE_RECU_NEGATIF", m["reference_piece"],
                 {"conclusion": conclusion, "comptes": comptes})
    return {"conclusion": conclusion, "comptes": comptes, "details": lignes}


def _clore_alerte(db, m, motif):
    db.execute("UPDATE alertes SET statut='TRAITEE', message=message||? WHERE type='ANNULATION_RECU_A_VERIFIER' "
               "AND ct_num=? AND message LIKE ? AND statut='OUVERTE'",
               (f" [{now_iso()} : {motif}]", m["ct_num"], m["reference_piece"] + " :%"))
