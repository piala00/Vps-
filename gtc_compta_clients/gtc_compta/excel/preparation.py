"""Classeur de preparation journaliere : lecture du COLLAGE, ecriture des feuilles
FACTURES / REGLEMENTS / ANOMALIES / EXPORT_ERP, et relecture de EXPORT_ERP.

Traitement Python equivalent au bouton VBA "Trier et preparer" (secours si les
macros sont desactivees). Les memes regles sont utilisees des deux cotes.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from .. import EXPORT_FORMAT_VERSION
from .report_parser import ParseurRapport, ResultatPreparation, empreinte_mouvement

EXPORT_COLONNES = [
    "format_version", "id_import", "agence", "date_rapport", "type_mouvement",
    "reference_piece", "code_tiers", "nom_client", "acheteur_detail", "montant", "sens",
    "bc_origine", "mode_reference", "source_feuille", "source_ligne", "empreinte_ligne",
]
FEUILLES = ["PARAMETRES", "COLLAGE", "FACTURES", "REGLEMENTS", "ANOMALIES", "EXPORT_ERP"]


class FormatExportInvalide(ValueError):
    pass


def _to_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date illisible : {v!r}")


def lire_parametres(wb) -> dict:
    p = {}
    if "PARAMETRES" in wb.sheetnames:
        for row in wb["PARAMETRES"].iter_rows(min_row=1, max_col=2, values_only=True):
            if row and row[0]:
                p[str(row[0]).strip().upper()] = row[1]
    return p


def preparer_depuis_classeur(path, regles: dict, correspondances: dict,
                             agence_defaut: str = "") -> ResultatPreparation:
    """Lit COLLAGE + PARAMETRES d'un classeur de preparation (.xlsm ou .xlsx)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "COLLAGE" not in wb.sheetnames:
            raise FormatExportInvalide("Feuille COLLAGE absente : ce n'est pas un classeur de preparation")
        params = lire_parametres(wb)
        rows = [list(r) for r in wb["COLLAGE"].iter_rows(values_only=True)]
    finally:
        wb.close()
    d = _to_date(params.get("DATE DU RAPPORT"))
    agence = str(params.get("AGENCE") or agence_defaut)
    res = ParseurRapport(regles, correspondances).analyser(rows, "COLLAGE", agence, d)
    if d is None:
        from .report_parser import Anomalie
        res.anomalies.append(Anomalie("PARAMETRES", 0, "PARAMETRES", "BLOQUANT",
            "Date du rapport non renseignee dans PARAMETRES", "", "Saisir la date"))
    return res


def id_import(res: ResultatPreparation) -> str:
    base = f"{res.agence}|{res.date_rapport}|" + "|".join(
        empreinte_mouvement(res.agence, m) for m in res.mouvements)
    return f"{res.agence}-{res.date_rapport}-" + hashlib.sha256(base.encode()).hexdigest()[:10]


def lignes_export(res: ResultatPreparation) -> list[dict]:
    imp = id_import(res)
    out = []
    for m in res.mouvements:
        out.append({
            "format_version": EXPORT_FORMAT_VERSION, "id_import": imp, "agence": res.agence,
            "date_rapport": res.date_rapport.isoformat() if res.date_rapport else "",
            "type_mouvement": m.nature, "reference_piece": m.reference_piece,
            "code_tiers": m.ct_num, "nom_client": m.client_libelle,
            "acheteur_detail": m.acheteur_detail, "montant": m.montant, "sens": m.sens,
            "bc_origine": m.bc_origine, "mode_reference": m.mode_reference,
            "source_feuille": m.feuille, "source_ligne": m.ligne,
            "empreinte_ligne": empreinte_mouvement(res.agence, m),
        })
    return out


def ecrire_classeur_prepare(res: ResultatPreparation, rows_collage: list[list], dest,
                            utilisateur: str = "") -> Path:
    """Produit un classeur .xlsx de preparation complet (sans macro)."""
    dest = Path(dest)
    if dest.suffix.lower() == ".xlsm":
        raise ValueError("Un classeur sans projet VBA ne doit pas porter l'extension .xlsm")
    wb = Workbook()
    ws = wb.active
    ws.title = "PARAMETRES"
    for k, v in [("AGENCE", res.agence), ("DATE DU RAPPORT", res.date_rapport),
                 ("PERIODE", res.date_rapport.strftime("%Y-%m") if res.date_rapport else ""),
                 ("UTILISATEUR", utilisateur), ("VERSION DU FORMAT", EXPORT_FORMAT_VERSION),
                 ("PREPARE LE", datetime.now().strftime("%Y-%m-%d %H:%M"))]:
        ws.append([k, v])
    wc = wb.create_sheet("COLLAGE")
    for r in rows_collage:
        wc.append(list(r))
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDEBF7")
    cols_m = ["ct_num", "client_libelle", "reference_piece", "bc_origine", "type_document",
              "montant", "sens", "mode_reference", "acheteur_detail", "feuille", "ligne", "notes"]
    for titre, items in (("FACTURES", res.factures), ("REGLEMENTS", res.reglements)):
        s = wb.create_sheet(titre)
        s.append(cols_m)
        for m in items:
            d = m.to_dict()
            s.append([d[c] for c in cols_m])
    sa = wb.create_sheet("ANOMALIES")
    sa.append(["feuille", "ligne", "section", "gravite", "motif", "contenu", "proposition", "statut"])
    for a in res.anomalies:
        sa.append([a.feuille, a.ligne, a.section, a.gravite, a.motif, a.contenu, a.proposition, a.statut])
    se = wb.create_sheet("EXPORT_ERP")
    se.append(EXPORT_COLONNES)
    for l in lignes_export(res):
        se.append([l[c] for c in EXPORT_COLONNES])
    for s in wb.worksheets:
        if s.title not in ("PARAMETRES", "COLLAGE"):
            for c in s[1]:
                c.font, c.fill = bold, fill
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


def lire_export_erp(path) -> list[dict]:
    """Relit et valide la feuille EXPORT_ERP (schema stable versionne)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "EXPORT_ERP" not in wb.sheetnames:
            raise FormatExportInvalide("Feuille EXPORT_ERP absente")
        it = wb["EXPORT_ERP"].iter_rows(values_only=True)
        entete = [str(c).strip() if c else "" for c in next(it, [])]
        manquantes = [c for c in EXPORT_COLONNES if c not in entete]
        if manquantes:
            raise FormatExportInvalide("Colonnes manquantes dans EXPORT_ERP : " + ", ".join(manquantes))
        out = []
        for row in it:
            if not row or all(v in (None, "") for v in row):
                continue
            d = _normaliser_ligne(dict(zip(entete, row)))
            if d["format_version"] != EXPORT_FORMAT_VERSION:
                raise FormatExportInvalide(f"Version de format non supportee : {d['format_version']}")
            out.append(d)
        return out
    finally:
        wb.close()


def _normaliser_ligne(d: dict) -> dict:
    """Valeurs ecrites par Excel/VBA : dates converties, nombres flottants, cellules vides."""
    from ..money import parse_montant
    v = d.get("date_rapport")
    if isinstance(v, (datetime, date)):
        d["date_rapport"] = _to_date(v).isoformat()
    elif v:
        d["date_rapport"] = _to_date(v).isoformat()
    d["montant"] = parse_montant(d.get("montant"))
    if d.get("source_ligne") not in (None, ""):
        d["source_ligne"] = int(d["source_ligne"])
    for k in ("id_import", "agence", "type_mouvement", "reference_piece", "code_tiers", "nom_client",
              "acheteur_detail", "sens", "bc_origine", "mode_reference", "source_feuille"):
        val = d.get(k)
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        d[k] = "" if val is None else str(val).strip()
    return d
