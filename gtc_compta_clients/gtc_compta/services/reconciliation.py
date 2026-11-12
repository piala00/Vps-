"""Rapprochement quotidien ERP <-> Sage Comptabilite (lecture seule).

Principes :
- meme date d'arrete, meme tiers ; solde d'ouverture = solde Sage a la date de reference ;
- Sage indisponible ou extraction incomplete => EN_ATTENTE_SAGE, jamais RAPPROCHE ;
- solde d'ouverture absent => BLOQUE ;
- validation automatique UNIQUEMENT si ecart nul ET aucune ligne non appariee ;
- chaque controle conserve sa preuve (soldes, empreinte des ecritures Sage, appariements).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..db import now_iso
from ..sage.base import SageEntry, SageExtractionIncomplete, SageIndisponible
from ..text import normaliser_reference
from .auth import Utilisateur, exiger
from .clients import solde_ouverture
from .ledger import fiche_client, mouvements_client

STATUTS = ["EN_PREPARATION", "A_RAPPROCHER", "EN_ATTENTE_SAGE", "RAPPROCHE",
           "ECART_A_ANALYSER", "BLOQUE", "VALIDE"]


@dataclass
class ResultatClient:
    ct_num: str
    statut: str
    solde_erp: int | None = None
    solde_sage: int | None = None
    ecart: int | None = None
    message: str = ""
    reconciliation_id: int | None = None
    ecarts: list[dict] = field(default_factory=list)


def empreinte_ecritures(solde_ref: int, ecritures: list[SageEntry]) -> str:
    h = hashlib.sha256(str(solde_ref).encode())
    for e in sorted(ecritures, key=lambda e: e.ec_no):
        h.update(f"|{e.ec_no}:{e.date_ecriture}:{e.sens}:{e.montant}:{normaliser_reference(e.numero_piece)}".encode())
    return h.hexdigest()


def clients_a_rapprocher(db, date_arrete: date) -> list[str]:
    d = date_arrete.isoformat()
    rows = db.query(
        "SELECT DISTINCT ct_num FROM normalized_movements WHERE statut<>'ANNULE' AND "
        "(date_piece=? OR (statut='PROVISOIRE' AND date_piece<=?)) "
        "UNION SELECT ct_num FROM daily_reconciliations WHERE obsolete=0 AND date_arrete=? "
        "AND statut<>'VALIDE' ORDER BY 1", (d, d, d))
    return [r[0] for r in rows]


def apparier(mvts: list, ecritures: list[SageEntry]):
    """Retourne (paires, ecarts). Gere references non uniques et ecritures agregees."""
    paires, ecarts = [], []
    restant_e = {e.ec_no: e for e in ecritures}
    restant_m = []
    for m in mvts:                                   # 1) lien explicite par EC_No
        if m["sage_ec_no"] and m["sage_ec_no"] in restant_e:
            e = restant_e.pop(m["sage_ec_no"])
            if e.montant == m["montant"] and e.sens == m["sens"]:
                paires.append((m["id"], [e.ec_no]))
            else:
                ecarts.append({"type": "MONTANT_DIFFERENT", "movement_id": m["id"], "sage_ec_no": e.ec_no,
                               "montant_erp": _s(m["montant"], m["sens"]), "montant_sage": e.signe,
                               "description": f"{m['reference_piece']} : montant/sens different"})
        else:
            restant_m.append(m)
    par_ref = defaultdict(list)                      # 2) par reference de piece et sens
    for e in restant_e.values():
        for ref in {normaliser_reference(e.reference_piece), normaliser_reference(e.numero_piece)} - {""}:
            par_ref[(ref, e.sens)].append(e)
    pris: set[int] = set()
    non_apparies = []
    for m in restant_m:
        refs = [normaliser_reference(m["reference_piece"])]
        if m["nature"] == "ACOMPTE" and m["bc_origine"]:
            refs.append(normaliser_reference(m["bc_origine"]))     # acompte rattache au BC
        cands = []
        for r_ in refs:
            cands += [e for e in par_ref.get((r_, m["sens"]), []) if e.ec_no not in pris and e not in cands]
        if not cands:
            non_apparies.append(m)
            continue
        exact = next((e for e in cands if e.montant == m["montant"]), None)
        choix = [exact] if exact else cands               # ecritures agregees / eclatees
        total = sum(e.montant for e in choix)
        pris.update(e.ec_no for e in choix)
        if total == m["montant"]:
            paires.append((m["id"], [e.ec_no for e in choix]))
        else:
            ecarts.append({"type": "MONTANT_DIFFERENT", "movement_id": m["id"],
                           "sage_ec_no": choix[0].ec_no, "montant_erp": _s(m["montant"], m["sens"]),
                           "montant_sage": sum(e.signe for e in choix),
                           "description": f"{m['reference_piece']} : ERP {m['montant']} / Sage {total}"})
    # 3) Repli prudent (acomptes / reglements dont la reference Sage differe) : meme date,
    #    meme sens, meme montant, et correspondance UNIQUE des deux cotes. Trace dans la preuve.
    libres = [e for e in restant_e.values() if e.ec_no not in pris]
    for m in non_apparies:
        cle = (m["date_piece"], m["sens"], m["montant"])
        cs = [e for e in libres if (e.date_ecriture.isoformat(), e.sens, e.montant) == cle]
        jumeaux = [x for x in non_apparies if (x["date_piece"], x["sens"], x["montant"]) == cle]
        if len(cs) == 1 and len(jumeaux) == 1 and m["nature"] in ("ACOMPTE", "REGLEMENT", "ANNULATION_RECU"):
            pris.add(cs[0].ec_no)
            libres.remove(cs[0])
            paires.append((m["id"], [cs[0].ec_no], "DATE_SENS_MONTANT"))
            continue
        ecarts.append({"type": "ERP_ABSENT_SAGE", "movement_id": m["id"], "sage_ec_no": None,
                       "montant_erp": _s(m["montant"], m["sens"]), "montant_sage": None,
                       "description": f"{m['nature']} {m['reference_piece']} du {m['date_piece']} "
                                      "absent de Sage a la date d'arrete"})
    for e in restant_e.values():
        if e.ec_no not in pris:
            ecarts.append({"type": "SAGE_ABSENT_ERP", "movement_id": None, "sage_ec_no": e.ec_no,
                           "montant_erp": None, "montant_sage": e.signe,
                           "description": f"Ecriture Sage {e.journal} {e.numero_piece} du {e.date_ecriture} "
                                         f"'{e.libelle}' absente du suivi ERP"})
    return paires, ecarts


def _s(montant, sens):
    return montant if sens == "D" else -montant


def rapprocher(db, user: Utilisateur, sage, date_arrete: date, ct_nums: list[str] | None = None,
               auto_valider: bool = True, progression=None) -> list[ResultatClient]:
    ct_nums = ct_nums if ct_nums is not None else clients_a_rapprocher(db, date_arrete)
    out = []
    for i, ct in enumerate(ct_nums):
        out.append(_rapprocher_client(db, user, sage, ct, date_arrete, auto_valider))
        if progression:
            progression(i + 1, len(ct_nums))
    return out


def _enregistrer(db, user, ct, d, statut, message, **kw) -> int:
    db.execute("UPDATE daily_reconciliations SET obsolete=1 WHERE ct_num=? AND date_arrete=? AND obsolete=0",
               (ct, d.isoformat()))
    cur = db.execute(
        "INSERT INTO daily_reconciliations(ct_num, date_arrete, statut, solde_erp, solde_sage, ecart, "
        "empreinte_sage, preuve_json, message, execute_le, execute_par) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ct, d.isoformat(), statut, kw.get("solde_erp"), kw.get("solde_sage"), kw.get("ecart"),
         kw.get("empreinte"), kw.get("preuve"), message, now_iso(), user.login))
    return cur.lastrowid


def _rapprocher_client(db, user, sage, ct, d: date, auto_valider) -> ResultatClient:
    ob = solde_ouverture(db, ct, d)
    if ob is None:
        with db.transaction():
            rid = _enregistrer(db, user, ct, d, "BLOQUE", "Solde d'ouverture Sage absent : solde non garanti")
        return ResultatClient(ct, "BLOQUE", message="Solde d'ouverture absent", reconciliation_id=rid)
    date_ref = date.fromisoformat(ob["date_reference"])
    try:
        solde_ref_sage = sage.solde_client(ct, date_ref)
        ecritures = sage.ecritures_client(ct, date_ref + timedelta(days=1), d)
        solde_sage = sage.solde_client(ct, d)
    except (SageIndisponible, SageExtractionIncomplete) as exc:
        with db.transaction():
            rid = _enregistrer(db, user, ct, d, "EN_ATTENTE_SAGE", f"Sage non interrogeable : {exc}")
        return ResultatClient(ct, "EN_ATTENTE_SAGE", message=str(exc), reconciliation_id=rid)

    if solde_ref_sage + sum(e.signe for e in ecritures) != solde_sage:
        with db.transaction():
            rid = _enregistrer(db, user, ct, d, "EN_ATTENTE_SAGE",
                               "Extraction Sage incoherente (solde != ouverture + ecritures)")
        return ResultatClient(ct, "EN_ATTENTE_SAGE", message="Extraction incoherente", reconciliation_id=rid)

    fiche = fiche_client(db, ct, d)
    solde_erp = fiche.solde_final
    mvts = mouvements_client(db, ct, ob["date_reference"], d.isoformat())
    paires, ecarts = apparier(mvts, ecritures)
    if solde_ref_sage != ob["solde"]:
        ecarts.append({"type": "RETROACTIF", "movement_id": None, "sage_ec_no": None,
                       "montant_erp": ob["solde"], "montant_sage": solde_ref_sage,
                       "description": f"Solde Sage au {date_ref} modifie depuis l'import du solde d'ouverture "
                                      "(ecriture retroactive ?)"})
    ecart = solde_erp - solde_sage
    statut = "RAPPROCHE" if ecart == 0 and not ecarts else "ECART_A_ANALYSER"
    empreinte = empreinte_ecritures(solde_ref_sage, ecritures)
    preuve = json.dumps({"date_reference": ob["date_reference"], "solde_ouverture": ob["solde"],
                         "solde_sage_reference": solde_ref_sage, "nb_ecritures_sage": len(ecritures),
                         "nb_mouvements_erp": len(mvts), "paires": paires, "source": sage.nom,
                         "ec_nos": [e.ec_no for e in ecritures]})
    with db.transaction():
        rid = _enregistrer(db, user, ct, d, statut,
                           "Concordance ERP/Sage" if statut == "RAPPROCHE" else f"{len(ecarts)} ecart(s) a analyser",
                           solde_erp=solde_erp, solde_sage=solde_sage, ecart=ecart, empreinte=empreinte, preuve=preuve)
        ts = now_iso()
        for e in ecritures:
            db.execute("INSERT INTO sage_accounting_entries_snapshot(reconciliation_id, ec_no, ct_num, journal, "
                       "date_ecriture, numero_piece, reference_piece, libelle, sens, montant, capture_le) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (rid, e.ec_no, ct, e.journal, e.date_ecriture.isoformat(), e.numero_piece,
                        e.reference_piece, e.libelle, e.sens, e.montant, ts))
        for x in ecarts:
            db.execute("INSERT INTO reconciliation_discrepancies(reconciliation_id, type, movement_id, sage_ec_no, "
                       "montant_erp, montant_sage, description) VALUES (?,?,?,?,?,?,?)",
                       (rid, x["type"], x["movement_id"], x["sage_ec_no"], x["montant_erp"],
                        x["montant_sage"], x["description"]))
        for p in paires:
            mid, ec_nos = p[0], p[1]
            for ec in ec_nos:
                db.execute("INSERT OR IGNORE INTO movement_sage_links VALUES (?,?,?,?)", (mid, ec, rid, ts))
        db.audit(user.login, "RAPPROCHEMENT", ct, {"date": d.isoformat(), "statut": statut, "ecart": ecart,
                                                   "reco": rid})
        if statut == "RAPPROCHE" and auto_valider and user.peut("valider_fiche"):
            _valider(db, user, rid, auto=True)
            statut = "VALIDE"
    return ResultatClient(ct, statut, solde_erp, solde_sage, ecart, reconciliation_id=rid, ecarts=ecarts)


def _valider(db, user, rid, auto=False):
    r = db.one("SELECT * FROM daily_reconciliations WHERE id=?", (rid,))
    db.execute("UPDATE daily_reconciliations SET statut='VALIDE', valide_le=?, valide_par=? WHERE id=?",
               (now_iso(), ("AUTO:" if auto else "") + user.login, rid))
    ob = solde_ouverture(db, r["ct_num"], date.fromisoformat(r["date_arrete"]))
    db.execute("UPDATE normalized_movements SET statut='VALIDE' WHERE ct_num=? AND statut='PROVISOIRE' "
               "AND date_piece>? AND date_piece<=?", (r["ct_num"], ob["date_reference"], r["date_arrete"]))
    db.audit(user.login, "VALIDATION_FICHE", r["ct_num"],
             {"reco": rid, "date": r["date_arrete"], "solde": r["solde_sage"], "auto": auto})


def valider_fiche(db, user: Utilisateur, reconciliation_id: int) -> None:
    exiger(user, "valider_fiche")
    r = db.one("SELECT * FROM daily_reconciliations WHERE id=?", (reconciliation_id,))
    if r is None or r["obsolete"]:
        raise ValueError("Rapprochement introuvable ou perime : relancer le rapprochement")
    if r["statut"] != "RAPPROCHE":
        raise ValueError(f"Validation impossible : statut {r['statut']} (seul RAPPROCHE est validable)")
    with db.transaction():
        _valider(db, user, reconciliation_id)


def dernier_statut(db, date_arrete: date):
    return db.query("SELECT r.*, c.intitule FROM daily_reconciliations r JOIN clients c ON c.ct_num=r.ct_num "
                    "WHERE r.date_arrete=? AND r.obsolete=0 ORDER BY c.intitule", (date_arrete.isoformat(),))


def ecarts_ouverts(db, reconciliation_id: int):
    return db.query("SELECT d.*, s.journal, s.numero_piece, s.date_ecriture, s.libelle AS libelle_sage "
                    "FROM reconciliation_discrepancies d LEFT JOIN sage_accounting_entries_snapshot s "
                    "ON s.reconciliation_id=d.reconciliation_id AND s.ec_no=d.sage_ec_no "
                    "WHERE d.reconciliation_id=? ORDER BY d.id", (reconciliation_id,))


# -- Ecritures Sage absentes du rapport ---------------------------------------------------
def reprendre_ecriture_sage(db, user: Utilisateur, discrepancy_id: int, motif: str,
                            justificatif: str = "") -> int:
    """Option A : reprise dans le suivi ERP d'une ecriture Sage EXISTANTE, liee a son EC_No.
    Rien n'est ecrit dans Sage. Le mouvement est cree PROVISOIRE ; relancer le rapprochement."""
    exiger(user, "reprise_sage")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    d = db.one("SELECT * FROM reconciliation_discrepancies WHERE id=?", (discrepancy_id,))
    if d is None or d["type"] != "SAGE_ABSENT_ERP" or d["statut"] != "OUVERT":
        raise ValueError("Seul un ecart ouvert de type SAGE_ABSENT_ERP peut etre repris")
    s = db.one("SELECT * FROM sage_accounting_entries_snapshot WHERE reconciliation_id=? AND ec_no=?",
               (d["reconciliation_id"], d["sage_ec_no"]))
    if db.one("SELECT 1 FROM normalized_movements WHERE sage_ec_no=? AND statut<>'ANNULE'", (s["ec_no"],)):
        raise ValueError("Ecriture Sage deja reprise : double comptabilisation refusee")
    ref = s["numero_piece"] or f"EC{s['ec_no']}"
    if db.one("SELECT id FROM normalized_movements WHERE ct_num=? AND statut<>'ANNULE' AND reference_piece=? "
              "AND sens=?", (s["ct_num"], ref, s["sens"])):
        raise ValueError(f"Un mouvement ERP porte deja la reference {ref} : verifier l'appariement "
                         "plutot que de reprendre l'ecriture")
    agence = db.scalar("SELECT agence FROM import_batches ORDER BY id DESC LIMIT 1", default="")
    ts = now_iso()
    with db.transaction():
        cur = db.execute(
            "INSERT INTO normalized_movements(agence, nature, reference_piece, ct_num, date_piece, date_comptable, "
            "sens, montant, libelle, source, sage_ec_no, statut, cree_le, cree_par, motif) "
            "VALUES (?, 'COMPLEMENT_SAGE', ?,?,?,?,?,?,?, 'SAGE_COMPLEMENT', ?, 'PROVISOIRE', ?,?,?)",
            (agence, ref, s["ct_num"], s["date_ecriture"], s["date_ecriture"], s["sens"], s["montant"],
             f"[{s['journal']}] {s['libelle']}", s["ec_no"], ts, user.login, motif))
        mid = cur.lastrowid
        db.execute("INSERT INTO discrepancy_resolutions(discrepancy_id, decision, motif, justificatif, decideur, "
                   "decide_le, movement_id) VALUES (?, 'OPTION_A_REPRISE', ?,?,?,?,?)",
                   (discrepancy_id, motif, justificatif, user.login, ts, mid))
        db.execute("UPDATE reconciliation_discrepancies SET statut='RESOLU' WHERE id=?", (discrepancy_id,))
        db.audit(user.login, "REPRISE_ECRITURE_SAGE", s["ct_num"], {"ec_no": s["ec_no"], "mouvement": mid,
                                                                    "motif": motif})
    return mid


def resoudre_ecart(db, user: Utilisateur, discrepancy_id: int, decision: str, motif: str,
                   justificatif: str = "") -> None:
    """Option B (facture Gescom a etablir apres examen) ou explication documentee.
    Ne modifie aucun montant : le rapprochement reste en ecart jusqu'a concordance reelle."""
    exiger(user, "reprise_sage")
    if decision not in ("OPTION_B_FACTURE_GESCOM", "EXPLIQUE", "AUTRE"):
        raise ValueError("Decision inconnue")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    with db.transaction():
        db.execute("INSERT INTO discrepancy_resolutions(discrepancy_id, decision, motif, justificatif, decideur, "
                   "decide_le) VALUES (?,?,?,?,?,?)", (discrepancy_id, decision, motif, justificatif,
                                                       user.login, now_iso()))
        db.execute("UPDATE reconciliation_discrepancies SET statut=? WHERE id=?",
                   ("EN_ATTENTE_FACTURE" if decision == "OPTION_B_FACTURE_GESCOM" else "DOCUMENTE",
                    discrepancy_id))
        db.audit(user.login, "RESOLUTION_ECART", str(discrepancy_id), {"decision": decision, "motif": motif})


# -- Retroactivite ------------------------------------------------------------------------
def verifier_retroactivite(db, user: Utilisateur, sage) -> list[dict]:
    """Recalcule l'empreinte Sage des fiches validees ; alerte si elle a change."""
    alertes = []
    rows = db.query("SELECT r.* FROM daily_reconciliations r WHERE r.statut='VALIDE' AND r.obsolete=0")
    for r in rows:
        d = date.fromisoformat(r["date_arrete"])
        ob = solde_ouverture(db, r["ct_num"], d)
        date_ref = date.fromisoformat(ob["date_reference"])
        try:
            sref = sage.solde_client(r["ct_num"], date_ref)
            ecr = sage.ecritures_client(r["ct_num"], date_ref + timedelta(days=1), d)
        except (SageIndisponible, SageExtractionIncomplete):
            continue
        if empreinte_ecritures(sref, ecr) != r["empreinte_sage"]:
            anciens = set(json.loads(r["preuve_json"]).get("ec_nos", []))
            nouveaux = [e for e in ecr if e.ec_no not in anciens]
            msg = (f"Ecritures Sage modifiees apres validation du {r['date_arrete']} "
                   f"({len(nouveaux)} nouvelle(s)) : fiche a reverifier")
            with db.transaction():
                db.execute("UPDATE daily_reconciliations SET statut='A_RAPPROCHER', message=? WHERE id=?",
                           (msg, r["id"]))
                db.execute("INSERT INTO reconciliation_discrepancies(reconciliation_id, type, description) "
                           "VALUES (?, 'RETROACTIF', ?)", (r["id"], msg))
                db.execute("INSERT INTO alertes(cree_le, type, ct_num, message) VALUES (?,?,?,?)",
                           (now_iso(), "ECRITURE_RETROACTIVE", r["ct_num"], msg))
                db.execute("UPDATE client_balance_confirmations SET alerte_retroactive=1 "
                           "WHERE ct_num=? AND date_arrete>=?",
                           (r["ct_num"], min([e.date_ecriture for e in nouveaux], default=d).isoformat()))
                db.audit(user.login, "ALERTE_RETROACTIVE", r["ct_num"], msg)
            alertes.append({"ct_num": r["ct_num"], "date_arrete": r["date_arrete"], "message": msg})
    return alertes
