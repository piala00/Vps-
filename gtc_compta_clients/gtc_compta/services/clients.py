"""Referentiel clients : synchro Sage (lecture seule) + champs manuels persistants."""
from __future__ import annotations

from datetime import date

from ..db import now_iso
from ..text import normaliser
from .auth import Utilisateur, exiger

CHAMPS_MANUELS = ["zone", "delai_reglement_jours", "notes_recouvrement", "contacts",
                  "telephone_whatsapp", "telegram", "preference_communication"]


def synchroniser_clients(db, user: Utilisateur, sage, collectifs: list[str]) -> dict:
    """Met a jour les donnees Sage sans jamais toucher client_manual_fields."""
    exiger(user, "synchro_sage")
    clients = sage.lister_clients()          # leve SageIndisponible si besoin
    coll = {normaliser(c) for c in collectifs}
    n_new = n_upd = 0
    ts = now_iso()
    with db.transaction():
        for c in clients:
            exists = db.one("SELECT 1 FROM clients WHERE ct_num=?", (c.ct_num,))
            db.execute(
                "INSERT INTO clients(ct_num, intitule, telephone, ville, encours_autorise, est_collectif, sage_synchro_le) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(ct_num) DO UPDATE SET intitule=excluded.intitule, "
                "telephone=excluded.telephone, ville=excluded.ville, encours_autorise=excluded.encours_autorise, "
                "est_collectif=excluded.est_collectif, sage_synchro_le=excluded.sage_synchro_le",
                (c.ct_num, c.intitule, c.telephone, c.ville, c.encours_autorise,
                 1 if normaliser(c.intitule) in coll else 0, ts))
            n_upd += 1 if exists else 0
            n_new += 0 if exists else 1
        db.audit(user.login, "SYNCHRO_CLIENTS_SAGE", sage.nom, {"nouveaux": n_new, "maj": n_upd})
    return {"nouveaux": n_new, "mis_a_jour": n_upd, "total": len(clients)}


def maj_champs_manuels(db, user: Utilisateur, ct_num: str, **champs) -> None:
    exiger(user, "champs_manuels")
    inconnus = set(champs) - set(CHAMPS_MANUELS)
    if inconnus:
        raise ValueError(f"Champs inconnus : {inconnus}")
    if not db.one("SELECT 1 FROM clients WHERE ct_num=?", (ct_num,)):
        raise KeyError(f"Client {ct_num} inconnu")
    if "delai_reglement_jours" in champs and champs["delai_reglement_jours"] not in (None, ""):
        champs["delai_reglement_jours"] = int(champs["delai_reglement_jours"])
    with db.transaction():
        db.execute("INSERT OR IGNORE INTO client_manual_fields(ct_num) VALUES (?)", (ct_num,))
        for k, v in champs.items():
            db.execute(f"UPDATE client_manual_fields SET {k}=? WHERE ct_num=?", (v, ct_num))
        db.execute("UPDATE client_manual_fields SET modifie_le=?, modifie_par=? WHERE ct_num=?",
                   (now_iso(), user.login, ct_num))
        db.audit(user.login, "MAJ_CHAMPS_MANUELS", ct_num, champs)


def lister_clients(db, recherche: str = "", zone: str | None = None, limite: int = 500, offset: int = 0):
    """Classement par zone puis ordre alphabetique ; chargement pagine."""
    sql = ("SELECT c.*, m.zone, m.delai_reglement_jours, m.notes_recouvrement, m.contacts, "
           "m.telephone_whatsapp, m.telegram, m.preference_communication FROM clients c "
           "LEFT JOIN client_manual_fields m ON m.ct_num=c.ct_num WHERE 1=1")
    params: list = []
    if recherche:
        sql += " AND (c.ct_num LIKE ? OR c.intitule LIKE ? OR c.telephone LIKE ?)"
        params += [f"%{recherche}%"] * 3
    if zone:
        sql += " AND m.zone = ?"
        params.append(zone)
    sql += " ORDER BY COALESCE(m.zone,'~'), c.intitule LIMIT ? OFFSET ?"
    params += [limite, offset]
    return db.query(sql, params)


def zones(db) -> list[str]:
    return [r[0] for r in db.query("SELECT DISTINCT zone FROM client_manual_fields "
                                   "WHERE zone IS NOT NULL AND zone<>'' ORDER BY zone")]


# -- correspondances libelle rapport -> code tiers ---------------------------------
def correspondances(db) -> dict[str, str]:
    return {r[0]: r[1] for r in db.query("SELECT libelle_normalise, ct_num FROM client_aliases")}


def definir_correspondance(db, user: Utilisateur, libelle: str, ct_num: str) -> None:
    exiger(user, "correspondance_client")
    if not db.one("SELECT 1 FROM clients WHERE ct_num=?", (ct_num,)):
        raise KeyError(f"Code tiers {ct_num} absent du referentiel synchronise")
    with db.transaction():
        db.execute("INSERT INTO client_aliases VALUES (?,?,?,?,?) ON CONFLICT(libelle_normalise) "
                   "DO UPDATE SET ct_num=excluded.ct_num, verifie_par=excluded.verifie_par, "
                   "verifie_le=excluded.verifie_le",
                   (normaliser(libelle), libelle, ct_num, user.login, now_iso()))
        db.audit(user.login, "CORRESPONDANCE_CLIENT", ct_num, {"libelle": libelle})


def suggestions_correspondance(db, libelle: str, n: int = 5):
    """Suggestions a VALIDER par l'utilisateur (jamais d'affectation automatique)."""
    import difflib
    rows = db.query("SELECT ct_num, intitule FROM clients")
    cible = normaliser(libelle)
    scored = sorted(((difflib.SequenceMatcher(None, cible, normaliser(r[1])).ratio(), r[0], r[1])
                     for r in rows), reverse=True)
    return [(ct, nom, round(s, 2)) for s, ct, nom in scored[:n] if s > 0.4]


def correspondances_auto_exactes(db) -> dict[str, str]:
    """Option (desactivee par defaut) : intitule normalise identique ET unique."""
    out, vus = {}, {}
    for ct, nom in db.query("SELECT ct_num, intitule FROM clients"):
        k = normaliser(nom)
        vus[k] = vus.get(k, 0) + 1
        out[k] = ct
    return {k: v for k, v in out.items() if vus[k] == 1}


# -- soldes d'ouverture ------------------------------------------------------------
def importer_soldes_ouverture(db, user: Utilisateur, sage, date_ref: date) -> int:
    exiger(user, "soldes_ouverture")
    soldes = sage.soldes_a_date(date_ref)    # leve SageIndisponible : rien n'est ecrit
    connus = {r[0] for r in db.query("SELECT ct_num FROM clients")}
    ts = now_iso()
    n = 0
    with db.transaction():
        for ct, solde in soldes.items():
            if ct not in connus:
                continue
            db.execute("INSERT INTO opening_balances VALUES (?,?,?,?,?,?) ON CONFLICT(ct_num, date_reference) "
                       "DO UPDATE SET solde=excluded.solde, source=excluded.source, "
                       "importe_le=excluded.importe_le, importe_par=excluded.importe_par",
                       (ct, date_ref.isoformat(), int(solde), sage.nom, ts, user.login))
            n += 1
        db.audit(user.login, "IMPORT_SOLDES_OUVERTURE", date_ref.isoformat(), {"nb": n, "source": sage.nom})
    return n


def solde_ouverture(db, ct_num: str, date_max: date | None = None):
    sql = "SELECT * FROM opening_balances WHERE ct_num=?"
    p: list = [ct_num]
    if date_max:
        sql += " AND date_reference <= ?"
        p.append(date_max.isoformat())
    return db.one(sql + " ORDER BY date_reference DESC LIMIT 1", p)
