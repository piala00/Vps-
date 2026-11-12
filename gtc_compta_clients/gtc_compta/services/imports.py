"""Import idempotent des lignes EXPORT_ERP en zone provisoire."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..db import now_iso
from ..text import normaliser, normaliser_reference
from .auth import Utilisateur, exiger


@dataclass
class RapportImport:
    batch_id: int | None
    cle_lot: str
    deja_importe: bool = False
    inseres: int = 0
    deja_presents: int = 0
    conflits: int = 0
    rejets: list[tuple[int, str]] = field(default_factory=list)
    alertes_comptant: int = 0

    def resume(self) -> str:
        if self.deja_importe:
            return f"Lot {self.cle_lot} deja importe : aucun mouvement ajoute."
        return (f"{self.inseres} mouvement(s) importe(s), {self.deja_presents} deja present(s), "
                f"{self.conflits} conflit(s), {len(self.rejets)} rejet(s).")


def empreinte_fichier(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


SENS_REGLEMENTAIRE = {"FACTURE": "D", "AVOIR": "D", "REGLEMENT": "C", "ACOMPTE": "C"}


def completer_codes(lignes: list[dict], correspondances: dict[str, str]) -> int:
    """Complete code_tiers manquant a partir des correspondances VERIFIEES (le classeur
    .xlsm ne connait pas les codes Sage). Retourne le nombre de lignes completees."""
    from ..text import normaliser
    n = 0
    for l in lignes:
        if not (l.get("code_tiers") or "").strip():
            ct = correspondances.get(normaliser(l.get("nom_client")))
            if ct:
                l["code_tiers"] = ct
                n += 1
    return n


def importer_lot(db, user: Utilisateur, lignes: list[dict], fichier: str,
                 empreinte: str, feuille: str = "EXPORT_ERP", bons: list[dict] | None = None) -> RapportImport:
    exiger(user, "importer")
    if not lignes:
        raise ValueError("Aucune ligne a importer")
    cles = {l["id_import"] for l in lignes}
    if len(cles) != 1:
        raise ValueError("Le fichier contient plusieurs identifiants d'import")
    cle = cles.pop()
    agence = lignes[0]["agence"]
    date_rapport = lignes[0]["date_rapport"]
    if not date_rapport:
        raise ValueError("Date du rapport absente")
    rap = RapportImport(batch_id=None, cle_lot=cle)
    existing = db.one("SELECT id FROM import_batches WHERE cle_lot=?", (cle,))
    if existing:
        rap.batch_id, rap.deja_importe = existing[0], True
        db.audit(user.login, "REIMPORT_IGNORE", cle, {"fichier": fichier})
        return rap
    ts = now_iso()
    with db.transaction():
        cur = db.execute(
            "INSERT INTO import_batches(cle_lot, agence, date_rapport, fichier, feuille, empreinte_fichier, "
            "format_version, operateur, importe_le, statut) VALUES (?,?,?,?,?,?,?,?,?, 'EN_COURS')",
            (cle, agence, date_rapport, Path(fichier).name, feuille, empreinte,
             lignes[0]["format_version"], user.login, ts))
        bid = cur.lastrowid
        rap.batch_id = bid
        vus = set()
        # Les recus negatifs (contre-passations) sont traites apres les recus positifs du lot, quel que
        # soit leur ordre dans le rapport, pour pouvoir etre lies au recu qu'ils annulent.
        def _neg(l):
            try:
                return l["type_mouvement"] == "REGLEMENT" and int(l["montant"]) < 0
            except (TypeError, ValueError):
                return False
        for l in sorted(lignes, key=_neg):
            res, motif = _importer_ligne(db, user, bid, l, ts, vus)
            db.execute("INSERT INTO raw_import_rows(batch_id, feuille, ligne, contenu_json, resultat, motif) "
                       "VALUES (?,?,?,?,?,?)", (bid, l.get("source_feuille"), l.get("source_ligne"),
                                                json.dumps(l, default=str, ensure_ascii=False), res, motif))
            if res == "INSERE":
                rap.inseres += 1
            elif res == "DEJA_PRESENT":
                rap.deja_presents += 1
            elif res == "CONFLIT":
                rap.conflits += 1
            else:
                rap.rejets.append((l.get("source_ligne") or 0, motif))
        if bons:
            enregistrer_bons(db, bons, bid)
        rap.alertes_comptant = controler_factures_comptant(db, bid)
        db.execute("UPDATE import_batches SET statut=?, nb_inseres=?, nb_deja_presents=?, nb_conflits=?, "
                   "nb_rejets=? WHERE id=?",
                   ("IMPORTE_AVEC_REJETS" if rap.rejets or rap.conflits else "IMPORTE",
                    rap.inseres, rap.deja_presents, rap.conflits, len(rap.rejets), bid))
        db.audit(user.login, "IMPORT_LOT", cle, {"batch": bid, "resume": rap.resume()})
    return rap


def _importer_ligne(db, user, bid, l, ts, vus):
    ct = (l.get("code_tiers") or "").strip()
    if not ct:
        return "REJET", "Code tiers absent (correspondance client non verifiee)"
    if not db.one("SELECT 1 FROM clients WHERE ct_num=?", (ct,)):
        return "REJET", f"Code tiers {ct} absent du referentiel"
    nature = l["type_mouvement"]
    sens = l["sens"]
    try:
        montant = int(l["montant"])
    except (TypeError, ValueError):
        return "REJET", f"Montant invalide : {l['montant']!r}"
    if nature == "ANNULATION_RECU":          # ancien format d'export (avant la regle des signes)
        nature, sens, montant = "REGLEMENT", "C", -abs(montant)
    if nature not in SENS_REGLEMENTAIRE:
        return "REJET", f"Type de mouvement inconnu : {nature}"
    if sens != SENS_REGLEMENTAIRE[nature]:
        return "REJET", (f"{nature} au {'debit' if sens == 'D' else 'credit'} : contraire a la regle "
                         f"(factures au debit, recus et acomptes au credit, signe conserve)")
    if montant == 0:
        return "REJET", "Montant nul"
    ref = str(l["reference_piece"]).strip()
    cle = (nature, normaliser_reference(ref), ct)
    if cle in vus:
        return "REJET", "Doublon dans le lot"
    vus.add(cle)
    agence = l["agence"]
    ex = db.one("SELECT * FROM normalized_movements WHERE agence=? AND nature=? AND ct_num=? "
                "AND statut<>'ANNULE' AND reference_piece=?", (agence, nature, ct, ref))
    if ex:
        if ex["montant"] == montant and ex["sens"] == sens:
            return "DEJA_PRESENT", f"mouvement #{ex['id']}"
        db.execute("INSERT INTO import_conflicts(batch_id, movement_id, champ, valeur_existante, valeur_importee) "
                   "VALUES (?,?,?,?,?)", (bid, ex["id"], "montant/sens", f"{ex['montant']} {ex['sens']}",
                                          f"{montant} {sens}"))
        return "CONFLIT", f"Mouvement #{ex['id']} existe avec un montant/sens different"
    lien, avert_lien = None, ""
    if nature == "REGLEMENT" and montant < 0:    # recu negatif : contre-passation d'un recu errone
        lien, avert_lien = _recu_annule(db, agence, ct, -montant, l.get("reference_liee") or "", l["date_rapport"])
    autre = db.one("SELECT id, ct_num FROM normalized_movements WHERE agence=? AND nature=? AND reference_piece=? "
                   "AND ct_num<>? AND statut<>'ANNULE' LIMIT 1", (agence, nature, ref, ct))
    db.execute(
        "INSERT INTO normalized_movements(agence, nature, reference_piece, ct_num, date_piece, sens, montant, "
        "libelle, bc_origine, mode_reference, acheteur_detail, source, batch_id, source_fichier, source_feuille, "
        "source_ligne, statut, cree_le, cree_par, reference_liee) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'RAPPORT', ?,?,?,?, "
        "'PROVISOIRE', ?, ?, ?)",
        (agence, nature, ref, ct, l["date_rapport"], sens, montant,
         (f"Annulation recu {lien} (compte errone)" if nature == "REGLEMENT" and montant < 0 and lien else
          "Annulation recu (recu annule non identifie)" if nature == "REGLEMENT" and montant < 0
          else f"{nature.title()} {ref}")
         + (f" - {l['acheteur_detail']}" if l.get("acheteur_detail") else ""),
         l.get("bc_origine") or None, l.get("mode_reference") or None, l.get("acheteur_detail") or None,
         bid, l.get("source_fichier") or None, l.get("source_feuille"), l.get("source_ligne"), ts, user.login, lien))
    if avert_lien:
        db.execute("INSERT INTO alertes(cree_le, type, ct_num, message) VALUES (?,?,?,?)",
                   (ts, "ANNULATION_RECU_A_VERIFIER", ct, f"{ref} : {avert_lien}"))
        return "INSERE", avert_lien
    if autre:
        db.execute("INSERT INTO import_conflicts(batch_id, movement_id, champ, valeur_existante, valeur_importee) "
                   "VALUES (?,?,?,?,?)", (bid, autre["id"], "client (meme numero de piece)", autre["ct_num"], ct))
        return "INSERE", f"Attention : numero {ref} deja utilise pour le client {autre['ct_num']}"
    return "INSERE", ""


def _recu_annule(db, agence, ct, montant, ref_indiquee, date_piece):
    """Recu positif annule par un recu negatif : meme client, meme montant, anterieur ou du jour,
    pas deja annule. Retourne (reference, avertissement)."""
    deja = "SELECT 1 FROM normalized_movements a WHERE a.nature='REGLEMENT' AND a.montant<0 AND a.statut<>'ANNULE' " \
           "AND a.ct_num=m.ct_num AND a.reference_liee=m.reference_piece"
    base = ("SELECT m.reference_piece FROM normalized_movements m WHERE m.agence=? AND m.ct_num=? "
            "AND m.nature='REGLEMENT' AND m.statut<>'ANNULE' AND m.montant=? AND m.date_piece<=? "
            f"AND NOT EXISTS ({deja})")
    if ref_indiquee:
        r = db.one(base + " AND m.reference_piece=?", (agence, ct, montant, date_piece, ref_indiquee))
        if r:
            return r[0], ""
    r = db.query(base + " ORDER BY m.date_piece DESC, m.id DESC", (agence, ct, montant, date_piece))
    if r:
        return r[0][0], ""
    return None, ("recu negatif sans recu positif de meme montant sur ce compte dans les donnees importees : "
                  "verifier le compte (recu anterieur au demarrage, ou erreur de compte)")


def corriger_mouvement(db, user: Utilisateur, movement_id: int, motif: str,
                       montant: int | None = None, sens: str | None = None, annuler: bool = False) -> int | None:
    """Correction tracee : l'ancien mouvement est annule, un nouveau le remplace.
    Toute fiche deja validee a une date >= date du mouvement repasse a rapprocher."""
    exiger(user, "corriger_mouvement")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    old = db.one("SELECT * FROM normalized_movements WHERE id=?", (movement_id,))
    if old is None or old["statut"] == "ANNULE":
        raise ValueError("Mouvement introuvable ou deja annule")
    ts = now_iso()
    new_id = None
    with db.transaction():
        db.execute("UPDATE normalized_movements SET statut='ANNULE', motif=? WHERE id=?", (motif, movement_id))
        if not annuler:
            cols = [k for k in old.keys() if k not in ("id",)]
            vals = dict(old)
            vals.update(montant=montant if montant is not None else old["montant"],
                        sens=sens or old["sens"], statut="PROVISOIRE", source="CORRECTION",
                        remplace_id=movement_id, cree_le=ts, cree_par=user.login, motif=motif)
            cur = db.execute(f"INSERT INTO normalized_movements({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                             [vals[c] for c in cols])
            new_id = cur.lastrowid
        _invalider_rapprochements(db, old["ct_num"], old["date_piece"], f"Correction du mouvement #{movement_id}")
        db.audit(user.login, "CORRECTION_MOUVEMENT", str(movement_id),
                 {"motif": motif, "nouveau": new_id, "montant": montant, "sens": sens, "annulation": annuler})
    return new_id


def _invalider_rapprochements(db, ct_num, date_piece, raison):
    rows = db.query("SELECT id FROM daily_reconciliations WHERE ct_num=? AND date_arrete>=? AND obsolete=0 "
                    "AND statut IN ('VALIDE','RAPPROCHE')", (ct_num, date_piece))
    for (rid,) in rows:
        db.execute("UPDATE daily_reconciliations SET statut='A_RAPPROCHER', message=? WHERE id=?",
                   (f"A reverifier : {raison}", rid))
    if rows:
        db.execute("INSERT INTO alertes(cree_le, type, ct_num, message) VALUES (?,?,?,?)",
                   (now_iso(), "CORRECTION_RETROACTIVE", ct_num,
                    f"{raison} : {len(rows)} fiche(s) validee(s) a reverifier"))


def lots(db, limite=100):
    return db.query("SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (limite,))


# -- Registre des bons de commande et controle des factures comptant ------------------------
def enregistrer_bons(db, bons: list[dict], batch_id: int | None = None) -> int:
    n = 0
    for b in bons:
        cur = db.execute("INSERT OR IGNORE INTO bons_commande_rapport(agence, bc, piece, client_libelle, acompte, bp, "
                         "date_rapport, source_ligne, batch_id) VALUES (?,?,?,?,?,?,?,?,?)",
                         (b["agence"], b["bc"], b["piece"], b["client"], b["acompte"], b["bp"], b["date_rapport"],
                          b.get("ligne"), batch_id))
        n += cur.rowcount
    return n


def charger_historique_bons(db, user: Utilisateur, rapport, regles: dict, agence: str) -> int:
    """Charge le registre des BC (acomptes, BP) d'un rapport mensuel ANTERIEUR, sans creer de mouvement :
    permet de controler les factures comptant dont l'acompte a ete encaisse avant le demarrage."""
    from openpyxl import load_workbook
    from ..excel.preparation import bons_export
    from ..excel.report_parser import ParseurRapport
    exiger(user, "importer")
    wb = load_workbook(rapport, read_only=True, data_only=True)
    n = 0
    try:
        with db.transaction():
            for f in [x for x in wb.sheetnames if x.isdigit()]:
                res = ParseurRapport(regles, {}).analyser([list(r) for r in wb[f].iter_rows(values_only=True)],
                                                          f, agence, None)
                n += enregistrer_bons(db, bons_export(res))
            db.audit(user.login, "HISTORIQUE_BONS_COMMANDE", str(rapport), {"lignes": n})
    finally:
        wb.close()
    return n


def _cle_bc_mouvement(a) -> str:
    from ..config import DEFAULTS
    from ..excel.report_parser import cle_bc
    return cle_bc(a["bc_origine"] or "", a["reference_piece"], DEFAULTS["rapport"])


def _diagnostic_comptant(db, agence, a, alias, deja, cle):
    """Pourquoi l'acompte d'une facture comptant n'est-il pas retrouve sur son BC ?"""
    from datetime import date, timedelta
    reg = db.query("SELECT * FROM bons_commande_rapport WHERE agence=? AND bc=? AND date_rapport<=? "
                   "ORDER BY date_rapport", (agence, cle, a["date_piece"]))
    d = date.fromisoformat(a["date_piece"])
    cands = [r for r in db.query(
        "SELECT * FROM bons_commande_rapport WHERE agence=? AND acompte=? AND date_rapport BETWEEN ? AND ?",
        (agence, a["montant"], (d - timedelta(days=45)).isoformat(), a["date_piece"]))
        if alias.get(normaliser(r["client_libelle"])) == a["ct_num"] and r["bc"] != cle and r["bc"] not in deja]
    suggestion = (" ; BC probable : " + ", ".join(f"{r['bc'].replace('PIECE:', '')} ({r['piece']} du {r['date_rapport']})"
                                                  for r in cands[:3])) if cands else ""
    b = (a["bc_origine"] or "").strip()
    if cle.startswith("PIECE:"):
        motif = "colonne B vide" if not b else f"colonne B = '{b}' (pas un n° de BC)"
        return f"{motif} et aucun acompte sur la ligne de la facture" + suggestion
    if not reg:
        return (f"{cle} inconnu dans les rapports importes (BC anterieur a l'historique charge, ou erreur de "
                "saisie en colonne B)" + suggestion)
    clients = {alias.get(normaliser(r["client_libelle"])) for r in reg}
    if a["ct_num"] not in clients:
        return (f"{cle} appartient a un autre client ({reg[0]['client_libelle']}) : erreur probable en colonne B"
                + suggestion)
    acpt = sum(r["acompte"] for r in reg)
    if acpt == 0 and any(r["bp"] for r in reg):
        return (f"{cle} est un BC en BP (a credit, sans acompte) facture en COMPTANT : la facture n'est "
                "probablement pas soldee par un acompte dans Sage")
    return f"acompte de {cle} ({acpt}) inferieur aux factures comptant imputees sur ce BC" + suggestion


def controler_factures_comptant(db, batch_id: int) -> int:
    """Pour chaque facture comptant du lot (acompte impute), verifie dans le registre des BC (tous mois
    importes) que l'acompte a bien ete encaisse sur son BC (ou sur la ligne de la facture). Sinon :
    alerte avec diagnostic."""
    acs = db.query("SELECT * FROM normalized_movements WHERE batch_id=? AND nature='ACOMPTE' AND statut<>'ANNULE' "
                   "AND montant>0", (batch_id,))
    if not acs:
        return 0
    alias = {r[0]: r[1] for r in db.query("SELECT libelle_normalise, ct_num FROM client_aliases")}
    imputes: dict[str, int] = {}
    for r in db.query("SELECT * FROM normalized_movements WHERE nature='ACOMPTE' AND statut<>'ANNULE' AND montant>0"):
        k = (r["agence"], _cle_bc_mouvement(r))
        imputes.setdefault(k, []).append((r["date_piece"], r["montant"]))
    n = 0
    for a in acs:
        cle = _cle_bc_mouvement(a)
        dispo = db.scalar("SELECT SUM(acompte) FROM bons_commande_rapport WHERE agence=? AND bc=? AND date_rapport<=?",
                          (a["agence"], cle, a["date_piece"]), 0)
        impute = sum(m for d_, m in imputes.get((a["agence"], cle), []) if d_ <= a["date_piece"])
        if dispo >= impute:
            continue
        deja = {k[1] for k in imputes}
        diag = _diagnostic_comptant(db, a["agence"], a, alias, deja, cle)
        db.execute("INSERT INTO alertes(cree_le, type, ct_num, message) VALUES (?,?,?,?)",
                   (now_iso(), "FACTURE_COMPTANT_SANS_ACOMPTE", a["ct_num"],
                    f"{a['reference_piece']} : facture comptant de {a['montant']} du {a['date_piece']} - {diag}"))
        n += 1
    return n
