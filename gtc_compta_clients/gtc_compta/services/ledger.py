"""Fiche client numerique : mouvements et solde progressif.

Convention : solde > 0 = client debiteur (doit a GTC). D augmente, C diminue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .clients import solde_ouverture


@dataclass
class LigneFiche:
    id: int
    date: str
    piece: str
    libelle: str
    debit: int
    credit: int
    solde: int
    nature: str
    statut: str
    source: str
    sage_ec_no: int | None


@dataclass
class Fiche:
    ct_num: str
    intitule: str
    zone: str
    date_ouverture: str | None
    solde_ouverture: int
    solde_garanti: bool
    lignes: list[LigneFiche] = field(default_factory=list)

    @property
    def total_debit(self):
        return sum(l.debit for l in self.lignes)

    @property
    def total_credit(self):
        return sum(l.credit for l in self.lignes)

    @property
    def solde_final(self):
        return self.lignes[-1].solde if self.lignes else self.solde_ouverture


def mouvements_client(db, ct_num, apres: str | None, jusqua: str | None, statuts=None):
    sql = "SELECT * FROM normalized_movements WHERE ct_num=? AND statut<>'ANNULE'"
    p: list = [ct_num]
    if apres:
        sql += " AND date_piece > ?"
        p.append(apres)
    if jusqua:
        sql += " AND date_piece <= ?"
        p.append(jusqua)
    if statuts:
        sql += f" AND statut IN ({','.join('?'*len(statuts))})"
        p += list(statuts)
    return db.query(sql + " ORDER BY date_piece, CASE WHEN nature IN ('REGLEMENT','ACOMPTE') THEN 1 ELSE 0 END, id", p)


def fiche_client(db, ct_num: str, date_fin: date | None = None) -> Fiche:
    c = db.one("SELECT c.intitule, m.zone FROM clients c LEFT JOIN client_manual_fields m "
               "ON m.ct_num=c.ct_num WHERE c.ct_num=?", (ct_num,))
    if c is None:
        raise KeyError(f"Client {ct_num} inconnu")
    ob = solde_ouverture(db, ct_num, date_fin)
    f = Fiche(ct_num=ct_num, intitule=c[0], zone=c[1] or "",
              date_ouverture=ob["date_reference"] if ob else None,
              solde_ouverture=ob["solde"] if ob else 0, solde_garanti=ob is not None)
    solde = f.solde_ouverture
    for m in mouvements_client(db, ct_num, f.date_ouverture, date_fin.isoformat() if date_fin else None):
        d = m["montant"] if m["sens"] == "D" else 0
        cr = m["montant"] if m["sens"] == "C" else 0
        solde += d - cr
        f.lignes.append(LigneFiche(m["id"], m["date_piece"], m["reference_piece"], m["libelle"] or "",
                                   d, cr, solde, m["nature"], m["statut"], m["source"], m["sage_ec_no"]))
    return f
