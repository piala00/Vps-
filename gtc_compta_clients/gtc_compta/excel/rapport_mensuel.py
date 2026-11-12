"""Lecture d'un rapport commercial mensuel complet (lecture seule) : mois du fichier, feuille RECAP."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

from ..text import normaliser


def mois_du_fichier(path, wb) -> tuple[int | None, int]:
    """Mois du rapport : prefixe du nom de fichier (« 05_RC_MAI », « 05 RC MAI »), sinon mois majoritaire des
    dates imprimees (A4). Annee : celle des dates imprimees. La date A4 seule n'est pas fiable (mai 2026)."""
    dates = []
    for f in [x for x in wb.sheetnames if x.isdigit()][:31]:
        for r in wb[f].iter_rows(min_row=1, max_row=8, values_only=True):
            v = next((x for x in r[:3] if hasattr(x, "year")), None)
            if v is not None:
                dates.append(v)
                break
    annee = Counter(d.year for d in dates).most_common(1)[0][0] if dates else date.today().year
    m = re.match(r"^(\d{1,2})[ _.-]", Path(path).name)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), annee
    return (Counter(d.month for d in dates).most_common(1)[0][0] if dates else None), annee


def lire_recap(wb) -> dict:
    """{date ISO : {colonne normalisee : valeur}} depuis la feuille RECAP (valeurs calculees par Excel)."""
    if "RECAP" not in wb.sheetnames:
        return {}
    out = {}
    rows = list(wb["RECAP"].iter_rows(values_only=True))
    entete = next((i for i, r in enumerate(rows) if r and r[0] and "DATE" in normaliser(r[0])), None)
    if entete is None:
        return {}
    noms = [normaliser(c) if c else "" for c in rows[entete]]
    for r in rows[entete + 1:]:
        if r and hasattr(r[0], "date"):
            out.setdefault(r[0].date().isoformat(), {n: r[k] for k, n in enumerate(noms) if n})
    return out


def formules_recap(path) -> dict:
    """Formules de la feuille RECAP par jour : {jour : {colonne : formule}} (diagnostic des references)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False)
    if "RECAP" not in wb.sheetnames:
        return {}
    ws = wb["RECAP"]
    out = {}
    for r in range(4, 35):
        out[r - 3] = {c: ws.cell(r, c).value for c in range(2, 8)}
    return out
