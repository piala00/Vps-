"""Factures PDF et communication assistee (WhatsApp / Telegram).

La liaison Sage <-> PDF n'est pas encore inventoriee. Strategie retenue :
1) index local de dossiers PDF configures (nom de fichier contenant le numero de piece) ;
2) adaptateur Sage (chemin_pdf_facture) quand la source reelle sera connue.
Aucun document n'est jamais invente : si le fichier n'existe pas, message explicite.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

from ..db import now_iso
from ..text import normaliser, normaliser_reference
from .auth import Utilisateur

_PIECE = re.compile(r"\d*[A-Z]{2,5}\d+")


class PdfIntrouvable(FileNotFoundError):
    pass


def indexer_dossiers(db, dossiers: list[str]) -> int:
    n = 0
    ts = now_iso()
    with db.transaction():
        for d in dossiers:
            for p in Path(d).rglob("*.pdf"):
                toks = {t for t in re.split(r"[^A-Z0-9]+", normaliser(p.stem)) if _PIECE.fullmatch(t)}
                for tok in toks:
                    db.execute("INSERT INTO invoice_pdf_links VALUES (?,?,?,?,?) ON CONFLICT(piece) DO UPDATE "
                               "SET chemin=excluded.chemin, indexe_le=excluded.indexe_le, taille=excluded.taille",
                               (tok, str(p), "INDEX_DOSSIER", ts, p.stat().st_size))
                    n += 1
    return n


def trouver_pdf(db, sage, piece: str) -> Path:
    key = normaliser_reference(piece)
    row = db.one("SELECT chemin FROM invoice_pdf_links WHERE piece=?", (key,))
    candidats = [row[0]] if row else []
    if sage is not None:
        try:
            c = sage.chemin_pdf_facture(piece)
            if c:
                candidats.append(c)
        except Exception:
            pass
    for c in candidats:
        if Path(c).is_file():
            return Path(c)
    if candidats:
        raise PdfIntrouvable(f"PDF de la piece {piece} reference mais fichier absent : {candidats[0]}")
    raise PdfIntrouvable(f"Aucun PDF disponible pour la piece {piece} (ni index local, ni lien Sage)")


def ouvrir_fichier(path, imprimer: bool = False) -> None:
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path, "print" if imprimer else "open")  # type: ignore[attr-defined]
    elif imprimer:
        subprocess.Popen(["lp", path])
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


def exporter_copie(db, user: Utilisateur, src: Path, dossier: str) -> Path:
    if not dossier:
        raise ValueError("Dossier d'export non configure (Parametres > documents.dossier_export)")
    dest = Path(dossier) / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    db.audit(user.login, "EXPORT_PDF", src.name, {"destination": str(dest)})
    return dest


def normaliser_telephone(tel: str, indicatif: str = "237") -> str:
    digits = re.sub(r"\D", "", tel or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9:
        digits = indicatif + digits
    return digits


def message_facture(client: str, piece: str, solde: int | None = None) -> str:
    txt = f"Bonjour {client},\nVeuillez trouver ci-joint la facture {piece}."
    if solde is not None:
        txt += f"\nSolde de votre compte a ce jour : {solde:,} FCFA.".replace(",", " ")
    return txt + "\nCordialement,\nService comptable GTC SARL"


def lien_whatsapp(tel: str, message: str) -> str:
    num = normaliser_telephone(tel)
    if len(num) < 11:
        raise ValueError("Numero WhatsApp absent ou invalide (fiche client > champs manuels)")
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}"


def lien_telegram(identifiant: str, message: str) -> str:
    ident = (identifiant or "").strip().lstrip("@")
    if ident:
        return f"https://t.me/{ident}"
    return "https://t.me/share/url?url=" + urllib.parse.quote(" ") + "&text=" + urllib.parse.quote(message)


def journaliser_transmission(db, user: Utilisateur, canal: str, ct_num: str, piece: str) -> None:
    db.audit(user.login, "TRANSMISSION_PREPAREE", ct_num, {"canal": canal, "piece": piece,
                                                            "note": "envoi a confirmer par l'utilisateur"})


def extrait_grand_livre_pdf(sage, ct_num: str, intitule: str, date_arrete, dest, societe: str = "") -> Path:
    """Extrait des ecritures Sage du client (lecture seule). Ce n'est pas l'edition officielle
    Sage : pour transmission formelle, imprimer le grand livre depuis Sage."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from ..money import fmt_fcfa
    ecr = sage.ecritures_client(ct_num, None, date_arrete)
    c = canvas.Canvas(str(dest), pagesize=A4)
    W, H = A4
    y = 0
    solde = 0

    def entete():
        c.setFont("Helvetica-Bold", 11)
        c.drawString(15 * mm, H - 15 * mm, f"{societe} - Extrait des ecritures Sage (compte client)")
        c.setFont("Helvetica", 9)
        c.drawString(15 * mm, H - 21 * mm, f"{intitule} ({ct_num}) - arrete au {date_arrete:%d/%m/%Y} - source : {sage.nom}")
        c.drawString(15 * mm, H - 26 * mm, "Document informatif, non substituable a l'edition officielle du grand livre Sage.")
        return H - 36 * mm

    y = entete()
    for e in ecr:
        if y < 20 * mm:
            c.showPage()
            y = entete()
        solde += e.signe
        c.setFont("Helvetica", 8)
        c.drawString(15 * mm, y, e.date_ecriture.strftime("%d/%m/%Y"))
        c.drawString(35 * mm, y, e.journal[:6])
        c.drawString(50 * mm, y, e.numero_piece[:14])
        c.drawString(78 * mm, y, e.libelle[:40])
        c.drawRightString(150 * mm, y, fmt_fcfa(e.montant) if e.sens == "D" else "")
        c.drawRightString(172 * mm, y, fmt_fcfa(e.montant) if e.sens == "C" else "")
        c.drawRightString(195 * mm, y, fmt_fcfa(solde))
        y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(195 * mm, y - 3 * mm, f"Solde au {date_arrete:%d/%m/%Y} : {fmt_fcfa(solde)} FCFA")
    c.save()
    return Path(dest)
