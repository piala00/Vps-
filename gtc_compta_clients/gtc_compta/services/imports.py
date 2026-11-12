"""Import idempotent des lignes EXPORT_ERP en zone provisoire."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..db import now_iso
from ..text import normaliser_reference
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
                 empreinte: str, feuille: str = "EXPORT_ERP") -> RapportImport:
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
        for l in lignes:
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
    if nature not in ("FACTURE", "AVOIR", "REGLEMENT", "ACOMPTE"):
        return "REJET", f"Type de mouvement inconnu : {nature}"
    sens = l["sens"]
    if sens not in ("D", "C"):
        return "REJET", f"Sens invalide : {sens}"
    try:
        montant = int(l["montant"])
    except (TypeError, ValueError):
        return "REJET", f"Montant invalide : {l['montant']!r}"
    if montant <= 0:
        return "REJET", "Montant nul ou negatif"
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
    autre = db.one("SELECT id, ct_num FROM normalized_movements WHERE agence=? AND nature=? AND reference_piece=? "
                   "AND ct_num<>? AND statut<>'ANNULE' LIMIT 1", (agence, nature, ref, ct))
    db.execute(
        "INSERT INTO normalized_movements(agence, nature, reference_piece, ct_num, date_piece, sens, montant, "
        "libelle, bc_origine, mode_reference, acheteur_detail, source, batch_id, source_fichier, source_feuille, "
        "source_ligne, statut, cree_le, cree_par) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'RAPPORT', ?,?,?,?, "
        "'PROVISOIRE', ?, ?)",
        (agence, nature, ref, ct, l["date_rapport"], sens, montant,
         f"{nature.title()} {ref}" + (f" - {l['acheteur_detail']}" if l.get("acheteur_detail") else ""),
         l.get("bc_origine") or None, l.get("mode_reference") or None, l.get("acheteur_detail") or None,
         bid, l.get("source_fichier") or None, l.get("source_feuille"), l.get("source_ligne"), ts, user.login))
    if autre:
        db.execute("INSERT INTO import_conflicts(batch_id, movement_id, champ, valeur_existante, valeur_importee) "
                   "VALUES (?,?,?,?,?)", (bid, autre["id"], "client (meme numero de piece)", autre["ct_num"], ct))
        return "INSERE", f"Attention : numero {ref} deja utilise pour le client {autre['ct_num']}"
    return "INSERE", ""


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
