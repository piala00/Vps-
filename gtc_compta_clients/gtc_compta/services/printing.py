"""Fiches clients PDF A4 recto verso et registre d'impression.

MODELE PROVISOIRE : le format papier reel n'a pas encore ete fourni (photos/scans
recto et verso a recevoir). Ce modele ne pretend pas reproduire l'original.

Regles :
- seules les lignes VALIDEES (apres rapprochement Sage) sont imprimees ;
- mode "nouveaux" : uniquement les mouvements jamais imprimes (+ contre-passations
  des mouvements imprimes puis annules), avec report du dernier solde imprime ;
- chaque client commence sur une nouvelle FEUILLE : nombre de pages pair par client
  (page blanche ajoutee si necessaire) ;
- marge de reliure alternee recto (gauche) / verso (droite) ;
- le PDF ne force pas le recto verso : choisir "Recto verso - bord long" a l'impression.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..db import now_iso
from ..money import fmt_fcfa
from .auth import Utilisateur, exiger
from .clients import solde_ouverture

W, H = A4
HAUT_LIGNE = 6.2 * mm
Y_HAUT_TABLE = H - 62 * mm
Y_BAS_TABLE = 34 * mm


def lignes_par_page(cfg_impr: dict | None = None) -> int:
    n = int((cfg_impr or {}).get("lignes_par_page") or 0)
    return n or int((Y_HAUT_TABLE - Y_BAS_TABLE) // HAUT_LIGNE) - 2   # -2 : report en tete / a reporter


@dataclass
class LigneImpr:
    date: str
    piece: str
    libelle: str
    debit: int
    credit: int
    movement_id: int | None = None
    type: str = "NORMAL"


@dataclass
class LotClient:
    ct_num: str
    intitule: str
    zone: str
    solde_reporte: int
    solde_garanti: bool
    lignes: list[LigneImpr] = field(default_factory=list)
    retroactif: bool = False
    version: int = 1

    @property
    def solde_final(self):
        return self.solde_reporte + sum(l.debit - l.credit for l in self.lignes)


def _derniere_impression(db, ct):
    return db.one("SELECT * FROM print_history WHERE ct_num=? AND statut IN ('GENERE','IMPRIME') "
                  "ORDER BY id DESC LIMIT 1", (ct,))


def preparer_lot(db, ct: str) -> LotClient:
    c = db.one("SELECT c.intitule, m.zone FROM clients c LEFT JOIN client_manual_fields m ON m.ct_num=c.ct_num "
               "WHERE c.ct_num=?", (ct,))
    last = _derniere_impression(db, ct)
    ob = solde_ouverture(db, ct)
    apres = ob["date_reference"] if ob else None
    if last:
        reporte, garanti = last["solde_final"], ob is not None
    else:
        reporte, garanti = (ob["solde"], True) if ob else (0, False)
    lot = LotClient(ct, c[0], c[1] or "", reporte, garanti,
                    version=(db.scalar("SELECT MAX(version) FROM print_history WHERE ct_num=?", (ct,), 0) + 1))
    sql = ("SELECT m.* FROM normalized_movements m WHERE m.ct_num=? AND m.statut='VALIDE' AND NOT EXISTS "
           "(SELECT 1 FROM printed_movements p WHERE p.movement_id=m.id AND p.type='NORMAL')")
    p = [ct]
    if apres:
        sql += " AND m.date_piece > ?"
        p.append(apres)
    rows = db.query(sql + " ORDER BY m.date_piece, CASE WHEN m.nature IN ('REGLEMENT','ACOMPTE','ANNULATION_RECU') THEN 1 ELSE 0 END, m.id", p)
    if last and rows and rows[0]["date_piece"] < (last["periode_fin"] or ""):
        lot.retroactif = True
    for m in rows:
        lot.lignes.append(LigneImpr(m["date_piece"], m["reference_piece"], m["libelle"] or m["nature"],
                                    m["montant"] if m["sens"] == "D" else 0,
                                    m["montant"] if m["sens"] == "C" else 0, m["id"]))
    annules = db.query("SELECT m.* FROM normalized_movements m JOIN printed_movements p ON p.movement_id=m.id "
                       "AND p.type='NORMAL' WHERE m.ct_num=? AND m.statut='ANNULE' AND NOT EXISTS "
                       "(SELECT 1 FROM printed_movements q WHERE q.movement_id=m.id AND q.type='ANNULATION')", (ct,))
    for m in annules:
        lot.lignes.append(LigneImpr(date.today().isoformat(), m["reference_piece"],
                                    f"ANNULATION {m['reference_piece']} ({m['motif'] or ''})"[:60],
                                    m["montant"] if m["sens"] == "C" else 0,
                                    m["montant"] if m["sens"] == "D" else 0, m["id"], "ANNULATION"))
    return lot


def file_attente(db, cfg_impr: dict | None = None):
    """Clients ayant des lignes validees non imprimees, tries par zone puis nom."""
    lpp = lignes_par_page(cfg_impr)
    seuil = int((cfg_impr or {}).get("seuil_alerte_pages", 2)) * lpp
    out = []
    rows = db.query("SELECT DISTINCT m.ct_num FROM normalized_movements m WHERE (m.statut='VALIDE' AND NOT EXISTS "
                    "(SELECT 1 FROM printed_movements p WHERE p.movement_id=m.id AND p.type='NORMAL')) OR "
                    "(m.statut='ANNULE' AND EXISTS (SELECT 1 FROM printed_movements p WHERE p.movement_id=m.id "
                    "AND p.type='NORMAL') AND NOT EXISTS (SELECT 1 FROM printed_movements q WHERE "
                    "q.movement_id=m.id AND q.type='ANNULATION'))")
    for (ct,) in rows:
        lot = preparer_lot(db, ct)
        if lot.lignes:
            out.append({"ct_num": ct, "intitule": lot.intitule, "zone": lot.zone, "nb_lignes": len(lot.lignes),
                        "pret_recto_verso": len(lot.lignes) >= seuil, "retroactif": lot.retroactif,
                        "plus_ancienne": min(l.date for l in lot.lignes)})
    return sorted(out, key=lambda x: (x["zone"] or "~", x["intitule"]))


# -- rendu PDF ------------------------------------------------------------------------
class _Rendu:
    def __init__(self, path, societe, agence, marge_reliure_mm):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle("Fiches clients")
        self.societe, self.agence = societe, agence
        self.reliure = marge_reliure_mm * mm
        self.pages = 0

    def _marges(self, page_client):
        recto = page_client % 2 == 1
        g = self.reliure if recto else 12 * mm
        d = 12 * mm if recto else self.reliure
        return g, W - d

    def client(self, lot: LotClient, lpp: int, controle: str) -> int:
        chunks = [lot.lignes[i:i + lpp] for i in range(0, len(lot.lignes), lpp)] or [[]]
        total = len(chunks) + (len(chunks) % 2)
        solde = lot.solde_reporte
        for i, chunk in enumerate(chunks, 1):
            x0, x1 = self._marges(i)
            self._entete(lot, i, total, x0, x1)
            y = Y_HAUT_TABLE
            cols = self._colonnes(x0, x1)
            self._ligne_titres(cols, y)
            y -= HAUT_LIGNE
            lib = ("Solde anterieur" + ("" if lot.solde_garanti else " (NON GARANTI : solde d'ouverture absent)")
                   if i == 1 else "Report")
            self._ligne(cols, y, "", "", lib, None, None, solde, bold=True)
            for l in chunk:
                y -= HAUT_LIGNE
                solde += l.debit - l.credit
                self._ligne(cols, y, _fmt_date(l.date), l.piece, l.libelle, l.debit, l.credit, solde)
            y -= HAUT_LIGNE
            if i < len(chunks):
                self._ligne(cols, y, "", "", "A reporter", None, None, solde, bold=True)
            else:
                self._ligne(cols, y, "", "", "TOTAUX / SOLDE FINAL", sum(l.debit for l in lot.lignes),
                            sum(l.credit for l in lot.lignes), solde, bold=True)
                self._pied(lot, x0, x1, controle)
            self._num(i, total, x0, x1)
            self.c.showPage()
            self.pages += 1
        if total > len(chunks):                       # page blanche : separation physique
            x0, x1 = self._marges(total)
            self.c.setFont("Helvetica-Oblique", 8)
            self.c.drawCentredString(W / 2, 20 * mm, f"{lot.ct_num} - verso laisse blanc (separation des clients)")
            self.c.showPage()
            self.pages += 1
        return total

    def _entete(self, lot, i, total, x0, x1):
        c = self.c
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x0, H - 18 * mm, self.societe)
        c.setFont("Helvetica", 9)
        c.drawString(x0, H - 23 * mm, f"Agence : {self.agence}")
        c.drawRightString(x1, H - 18 * mm, "FICHE CLIENT")
        c.drawRightString(x1, H - 23 * mm, f"Edition du {datetime.now():%d/%m/%Y %H:%M} - version {lot.version}")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x0, H - 33 * mm, f"{lot.intitule}")
        c.setFont("Helvetica", 9)
        c.drawString(x0, H - 38 * mm, f"Code tiers : {lot.ct_num}    Zone : {lot.zone or '-'}")
        if lot.lignes:
            c.drawString(x0, H - 43 * mm, f"Periode : {_fmt_date(min(l.date for l in lot.lignes))} au "
                                          f"{_fmt_date(max(l.date for l in lot.lignes))}")
        c.line(x0, H - 47 * mm, x1, H - 47 * mm)

    @staticmethod
    def _colonnes(x0, x1):
        w = x1 - x0
        return {"date": x0, "piece": x0 + 0.11 * w, "lib": x0 + 0.27 * w, "debit": x0 + 0.70 * w,
                "credit": x0 + 0.85 * w, "solde": x1, "x0": x0, "x1": x1}

    def _ligne_titres(self, cols, y):
        c = self.c
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(cols["date"], y, "Date")
        c.drawString(cols["piece"], y, "Piece")
        c.drawString(cols["lib"], y, "Libelle")
        c.drawRightString(cols["debit"], y, "Debit")
        c.drawRightString(cols["credit"], y, "Credit")
        c.drawRightString(cols["solde"], y, "Solde")
        c.line(cols["x0"], y - 1.8 * mm, cols["x1"], y - 1.8 * mm)

    def _ligne(self, cols, y, d, piece, lib, debit, credit, solde, bold=False):
        c = self.c
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8.5)
        c.drawString(cols["date"], y, d)
        c.drawString(cols["piece"], y, (piece or "")[:16])
        c.drawString(cols["lib"], y, (lib or "")[:48])
        if debit:
            c.drawRightString(cols["debit"], y, fmt_fcfa(debit))
        if credit:
            c.drawRightString(cols["credit"], y, fmt_fcfa(credit))
        c.drawRightString(cols["solde"], y, fmt_fcfa(solde))

    def _pied(self, lot, x0, x1, controle):
        c = self.c
        c.setFont("Helvetica", 8)
        c.drawString(x0, 26 * mm, f"Controle : {controle}"[:130])
        c.drawString(x0, 21 * mm, "Solde > 0 : client debiteur. Montants en FCFA.")
        c.drawRightString(x1, 16 * mm, "Visa comptable : ____________________")

    def _num(self, i, total, x0, x1):
        self.c.setFont("Helvetica", 8)
        self.c.drawCentredString((x0 + x1) / 2, 12 * mm, f"Page {i}/{total}")

    def save(self):
        self.c.save()


def _fmt_date(iso):
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def _controle(db, ct):
    r = db.one("SELECT date_arrete, solde_sage, valide_le, valide_par FROM daily_reconciliations WHERE ct_num=? "
               "AND statut='VALIDE' AND obsolete=0 ORDER BY date_arrete DESC LIMIT 1", (ct,))
    if not r:
        return "aucun rapprochement Sage valide"
    return (f"rapproche avec Sage au {_fmt_date(r[0])} (solde {fmt_fcfa(r[1])}), valide le "
            f"{r[2][:10]} par {r[3]}")


def generer_fiches(db, user: Utilisateur, ct_nums: list[str], dest, cfg: dict) -> dict:
    """Genere un PDF groupe (tri zone / nom) et inscrit le registre (statut GENERE)."""
    exiger(user, "impression")
    lots = [preparer_lot(db, ct) for ct in ct_nums]
    lots = sorted([l for l in lots if l.lignes], key=lambda l: (l.zone or "~", l.intitule))
    if not lots:
        raise ValueError("Aucune ligne validee non imprimee pour les clients selectionnes")
    impr = cfg.get("impression", {})
    lpp = lignes_par_page(impr)
    r = _Rendu(dest, cfg.get("societe", ""), cfg.get("agence", ""), impr.get("marge_reliure_mm", 20))
    pages = {}
    for lot in lots:
        pages[lot.ct_num] = r.client(lot, lpp, _controle(db, lot.ct_num))
    r.save()
    ts = now_iso()
    with db.transaction():
        job = db.execute("INSERT INTO print_jobs(cree_le, cree_par, type, fichier_pdf, nb_pages, statut) "
                         "VALUES (?,?,?,?,?, 'GENERE')", (ts, user.login, "NOUVEAUX_MOUVEMENTS", str(dest),
                                                          r.pages)).lastrowid
        for lot in lots:
            normales = [l for l in lot.lignes if l.type == "NORMAL"]
            ph = db.execute(
                "INSERT INTO print_history(job_id, ct_num, periode_debut, periode_fin, dernier_mouvement_id, "
                "solde_reporte, solde_final, nb_pages, version, statut, imprime_le, imprime_par) "
                "VALUES (?,?,?,?,?,?,?,?,?, 'GENERE', ?, ?)",
                (job, lot.ct_num, min(l.date for l in lot.lignes), max(l.date for l in lot.lignes),
                 max((l.movement_id for l in normales), default=None), lot.solde_reporte, lot.solde_final,
                 pages[lot.ct_num], lot.version, ts, user.login)).lastrowid
            for l in lot.lignes:
                db.execute("INSERT INTO printed_movements VALUES (?,?,?)", (l.movement_id, ph, l.type))
        db.audit(user.login, "GENERATION_FICHES", str(job), {"clients": [l.ct_num for l in lots], "pages": r.pages})
    return {"job_id": job, "pages": r.pages, "clients": len(lots), "fichier": str(dest), "pages_par_client": pages}


def confirmer_impression(db, user: Utilisateur, job_id: int) -> None:
    exiger(user, "impression")
    with db.transaction():
        db.execute("UPDATE print_jobs SET statut='IMPRIME' WHERE id=?", (job_id,))
        db.execute("UPDATE print_history SET statut='IMPRIME' WHERE job_id=?", (job_id,))
        db.audit(user.login, "IMPRESSION_CONFIRMEE", str(job_id))


def annuler_job(db, user: Utilisateur, job_id: int, motif: str) -> None:
    """Impression ratee : libere les lignes pour qu'elles soient reimprimees."""
    exiger(user, "impression")
    with db.transaction():
        ids = [r[0] for r in db.query("SELECT id FROM print_history WHERE job_id=?", (job_id,))]
        for i in ids:
            db.execute("DELETE FROM printed_movements WHERE print_history_id=?", (i,))
        db.execute("UPDATE print_history SET statut='ANNULE' WHERE job_id=?", (job_id,))
        db.execute("UPDATE print_jobs SET statut='ANNULE' WHERE id=?", (job_id,))
        db.audit(user.login, "IMPRESSION_ANNULEE", str(job_id), {"motif": motif})


def registre(db, limite=200):
    return db.query("SELECT h.*, c.intitule FROM print_history h JOIN clients c ON c.ct_num=h.ct_num "
                    "ORDER BY h.id DESC LIMIT ?", (limite,))


def generer_apercu(db, ct: str, dest, cfg: dict) -> int:
    """Apercu de la fiche complete (lignes provisoires incluses), SANS inscription au registre."""
    from .ledger import fiche_client
    f = fiche_client(db, ct)
    lot = LotClient(ct, f.intitule, f.zone, f.solde_ouverture, f.solde_garanti, version=0)
    for l in f.lignes:
        lib = l.libelle + (" [PROVISOIRE]" if l.statut == "PROVISOIRE" else "")
        lot.lignes.append(LigneImpr(l.date, l.piece, lib, l.debit, l.credit, l.id))
    impr = cfg.get("impression", {})
    r = _Rendu(dest, cfg.get("societe", ""), cfg.get("agence", "") + " - APERCU NON ENREGISTRE",
               impr.get("marge_reliure_mm", 20))
    r.client(lot, lignes_par_page(impr), _controle(db, ct))
    r.save()
    return r.pages
