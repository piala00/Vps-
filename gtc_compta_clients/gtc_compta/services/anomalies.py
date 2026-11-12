"""Registre des anomalies du rapport commercial (CR).

Objectif : le solde de chaque fiche client doit rester juste sans consulter Sage. Toute erreur de CR
qui peut fausser un solde (piece bloquee, client non rattache, numero reutilise...) est conservee
OUVERTE jusqu'a sa resolution, affichee sur la fiche du client concerne, et ne disparait jamais
silencieusement. Aucune ecriture n'est faite dans Sage.
"""
from __future__ import annotations

import json

from ..db import now_iso
from ..text import normaliser, normaliser_reference
from .auth import Utilisateur, exiger

CODES_FACTURE_A_CORRIGER = {"BC_AVEC_FACTURE", "FACTURE_SANS_NUMERO", "TYPE_INCONNU", "CLIENT_ABSENT",
                            "MONTANTS_H_I_DIFFERENTS", "ANNULEE_AVEC_MONTANT", "MONTANT_ILLISIBLE"}


def _alias(db) -> dict[str, str]:
    return {r[0]: r[1] for r in db.query("SELECT libelle_normalise, ct_num FROM client_aliases")}


def enregistrer(db, batch_id, a: dict, alias: dict | None = None) -> int:
    """Ajoute une anomalie au registre (statut INFORMATION si elle n'a pas d'impact sur un solde)."""
    alias = alias if alias is not None else _alias(db)
    ct = a.get("ct_num") or alias.get(normaliser(a.get("client") or ""))
    statut = "OUVERTE" if a.get("impact_solde", True) else "INFORMATION"
    cur = db.execute(
        "INSERT INTO anomalies_cr(batch_id, agence, date_rapport, feuille, ligne, code, gravite, impact_solde, motif, "
        "contenu, client_libelle, ct_num, reference, montant, colonne, statut, cree_le) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, a.get("agence", ""), a.get("date_rapport", ""), a.get("feuille"), a.get("ligne"), a["code"],
         a.get("gravite", "AVERTISSEMENT"), int(bool(a.get("impact_solde", True))), a["motif"],
         (a.get("contenu") or "")[:300], a.get("client") or "", ct, a.get("reference") or "", a.get("montant"),
         a.get("colonne") or "", statut, now_iso()))
    return cur.lastrowid


def enregistrer_lot(db, batch_id, anomalies: list[dict]) -> int:
    alias = _alias(db)
    for a in anomalies:
        enregistrer(db, batch_id, a, alias)
    _resoudre_automatiquement(db, batch_id)
    return len(anomalies)


def _resoudre_automatiquement(db, batch_id):
    """Apres import : les anomalies de la journee reglees par l'import lui-meme sont closes."""
    ts = now_iso()
    # recu negatif lie a son recu d'origine (jour precedent ou plus bas dans la feuille)
    for a in db.query("SELECT * FROM anomalies_cr WHERE batch_id=? AND code='RECU_NEGATIF_SANS_ORIGINE' "
                      "AND statut='OUVERTE'", (batch_id,)):
        lien = db.scalar("SELECT reference_liee FROM normalized_movements WHERE reference_piece=? AND nature='REGLEMENT' "
                         "AND montant<0 AND statut<>'ANNULE' AND reference_liee IS NOT NULL", (a["reference"],))
        if lien:
            db.execute("UPDATE anomalies_cr SET statut='RESOLUE', resolution=?, resolu_par='IMPORT', resolu_le=? "
                       "WHERE id=?", (f"Lie au recu {lien} (import)", ts, a["id"]))
    # client sans correspondance dans le classeur, mais code complete a l'import
    for a in db.query("SELECT * FROM anomalies_cr WHERE batch_id=? AND code='CLIENT_SANS_CORRESPONDANCE' "
                      "AND statut='OUVERTE'", (batch_id,)):
        mid = db.scalar("SELECT id FROM normalized_movements WHERE batch_id=? AND reference_piece=? "
                        "AND statut<>'ANNULE'", (batch_id, a["reference"]))
        if mid:
            db.execute("UPDATE anomalies_cr SET statut='RESOLUE', resolution='Code tiers complete a l''import', "
                       "resolu_par='IMPORT', resolu_le=?, movement_id=? WHERE id=?", (ts, mid, a["id"]))


def lister(db, statut: str | None = "OUVERTE", ct_num: str | None = None, impact: bool | None = None, limite=2000):
    sql = "SELECT * FROM anomalies_cr WHERE 1=1"
    p: list = []
    if statut:
        sql += " AND statut=?"
        p.append(statut)
    if ct_num:
        sql += " AND ct_num=?"
        p.append(ct_num)
    if impact is not None:
        sql += " AND impact_solde=?"
        p.append(int(impact))
    return db.query(sql + " ORDER BY date_rapport, id LIMIT ?", p + [limite])


def resume_client(db, ct_num: str) -> tuple[int, int]:
    """(nombre, montant total) des anomalies OUVERTES pouvant affecter le solde du client."""
    r = db.one("SELECT COUNT(*), COALESCE(SUM(montant),0) FROM anomalies_cr WHERE ct_num=? AND statut='OUVERTE' "
               "AND impact_solde=1", (ct_num,))
    return r[0], r[1]


def ouvertes_sans_client(db) -> int:
    return db.scalar("SELECT COUNT(*) FROM anomalies_cr WHERE statut='OUVERTE' AND impact_solde=1 AND ct_num IS NULL",
                     default=0)


def _clore(db, user, anomalie_id, statut, resolution, movement_id=None):
    db.execute("UPDATE anomalies_cr SET statut=?, resolution=?, resolu_par=?, resolu_le=?, movement_id=? WHERE id=?",
               (statut, resolution, user.login, now_iso(), movement_id, anomalie_id))
    db.audit(user.login, f"ANOMALIE_CR_{statut}", str(anomalie_id), {"resolution": resolution, "mouvement": movement_id})


def ignorer(db, user: Utilisateur, anomalie_id: int, motif: str) -> None:
    """Sans incidence sur les soldes (verifie) : motif obligatoire, trace."""
    exiger(user, "corriger_mouvement")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    with db.transaction():
        _clore(db, user, anomalie_id, "IGNOREE", motif)


def marquer_resolue(db, user: Utilisateur, anomalie_id: int, motif: str) -> None:
    """Resolue hors de ce module (ex. correction faite dans Sage puis reprise au rapprochement)."""
    exiger(user, "corriger_mouvement")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    with db.transaction():
        _clore(db, user, anomalie_id, "RESOLUE", motif)


def integrer_facture_corrigee(db, user: Utilisateur, anomalie_id: int, numero_facture: str, ct_num: str | None = None,
                              montant: int | None = None, comptant: bool | None = None, motif: str = "") -> int:
    """Integre dans la fiche la facture d'une ligne bloquee, avec le n° de facture correct (verifie dans
    Sage par le comptable). Facture au debit (signe conserve) ; si comptant, acompte impute au credit."""
    exiger(user, "corriger_mouvement")
    a = db.one("SELECT * FROM anomalies_cr WHERE id=?", (anomalie_id,))
    if a is None or a["statut"] != "OUVERTE":
        raise ValueError("Anomalie introuvable ou deja traitee")
    if a["code"] not in CODES_FACTURE_A_CORRIGER:
        raise ValueError(f"Integration de facture non prevue pour le code {a['code']}")
    numero = numero_facture.strip().upper()
    if not numero.startswith(("FACB", "FRCB", "FVCB")):
        raise ValueError("Saisir un numero de facture (FACB, FRCB ou FVCB)")
    ct = ct_num or a["ct_num"]
    if not ct or not db.one("SELECT 1 FROM clients WHERE ct_num=?", (ct,)):
        raise ValueError("Code tiers inconnu : indiquer le client")
    mt = int(montant if montant is not None else (a["montant"] or 0))
    if mt == 0:
        raise ValueError("Montant nul")
    if db.one("SELECT 1 FROM normalized_movements WHERE reference_piece=? AND nature IN ('FACTURE','AVOIR') "
              "AND statut<>'ANNULE'", (numero,)):
        raise ValueError(f"La facture {numero} est deja dans le suivi : pas de double integration")
    contenu = a["contenu"] or ""
    est_comptant = comptant if comptant is not None else (a["colonne"] == "H")
    nature = "AVOIR" if numero.startswith(("FRCB", "FVCB")) or mt < 0 else "FACTURE"
    ts = now_iso()
    bc = a["reference"] if normaliser_reference(a["reference"] or "").startswith("BC") else None
    with db.transaction():
        cols = ("agence, nature, reference_piece, ct_num, date_piece, sens, montant, libelle, bc_origine, source, "
                "batch_id, source_feuille, source_ligne, statut, cree_le, cree_par, motif")
        cur = db.execute(f"INSERT INTO normalized_movements({cols}) VALUES (?,?,?,?,?,'D',?,?,?, 'CORRECTION_CR', ?,?,?, "
                         "'PROVISOIRE', ?,?,?)",
                         (a["agence"], nature, numero, ct, a["date_rapport"], mt,
                          f"{nature.title()} {numero} (correction CR : {a['reference'] or 'sans n°'})", bc,
                          a["batch_id"], a["feuille"], a["ligne"], ts, user.login,
                          motif or f"Anomalie {a['code']} : {contenu[:80]}"))
        mid = cur.lastrowid
        if est_comptant:
            db.execute(f"INSERT INTO normalized_movements({cols}) VALUES (?, 'ACOMPTE', ?,?,?,'C',?,?,?, 'CORRECTION_CR', "
                       "?,?,?, 'PROVISOIRE', ?,?,?)",
                       (a["agence"], numero, ct, a["date_rapport"], mt, f"Acompte impute sur {numero} (correction CR)",
                        bc, a["batch_id"], a["feuille"], a["ligne"], ts, user.login, "facture comptant"))
        from .imports import _invalider_rapprochements
        _invalider_rapprochements(db, ct, a["date_rapport"], f"Integration de la facture corrigee {numero}")
        _clore(db, user, anomalie_id, "RESOLUE", f"Facture {numero} integree", mid)
    return mid


def reintegrer_rejets(db, user: Utilisateur, batch_id: int | None = None) -> dict:
    """Rejoue les lignes rejetees faute de code tiers, une fois les correspondances creees.
    Les lignes deja integrees ne sont jamais dupliquees (memes controles qu'a l'import)."""
    exiger(user, "importer")
    from .imports import _importer_ligne, completer_codes
    corr = _alias(db)
    sql = ("SELECT * FROM raw_import_rows WHERE resultat='REJET' AND (motif LIKE 'Code tiers absent%' "
           "OR motif LIKE 'Code tiers % absent du referentiel')")
    p: list = []
    if batch_id:
        sql += " AND batch_id=?"
        p.append(batch_id)
    out = {"integrees": 0, "toujours_rejetees": 0}
    ts = now_iso()
    with db.transaction():
        for r in db.query(sql, p):
            l = json.loads(r["contenu_json"])
            l["code_tiers"] = ""
            completer_codes([l], corr)
            res, motif = _importer_ligne(db, user, r["batch_id"], l, ts, set())
            if res == "REJET":
                out["toujours_rejetees"] += 1
                continue
            db.execute("UPDATE raw_import_rows SET resultat=?, motif=? WHERE id=?",
                       (res, f"reintegree le {ts[:10]} ({motif})" if motif else f"reintegree le {ts[:10]}", r["id"]))
            mid = db.scalar("SELECT id FROM normalized_movements WHERE reference_piece=? AND ct_num=? AND statut<>'ANNULE' "
                            "ORDER BY id DESC LIMIT 1", (l["reference_piece"], l["code_tiers"]))
            for a in db.query("SELECT id FROM anomalies_cr WHERE code='CLIENT_SANS_CORRESPONDANCE' AND statut='OUVERTE' "
                              "AND reference=? AND date_rapport=?", (l["reference_piece"], l["date_rapport"])):
                _clore(db, user, a["id"], "RESOLUE", f"Ligne reintegree sur {l['code_tiers']}", mid)
            out["integrees"] += 1
        db.audit(user.login, "REINTEGRATION_REJETS", str(batch_id or "tous"), out)
    return out
