"""Etat comparatif mensuel (modele de la feuille RECAP du rapport commercial) et rapprochement quotidien
des ventes avec Sage Comptabilite.

Pour chaque journee :
  vente comptant (colonne H), vente a credit (colonne I), total ventes = comptant + credit,
  recouvrements (recus), recette totale = recouvrements + vente comptant (regle GTC ; parametre
  `etat_comparatif.recette` = "acompte+recouvrement" pour reproduire la formule du modele RECAP).
Le total des ventes du CR doit etre egal aux ventes comptabilisees dans Sage pour ce jour (factures comptant
+ factures a credit, avoirs deduits, apres mise a jour). Sinon : erreur dans le CR ou probleme de mise a jour.
Lecture seule sur Sage.
"""
from __future__ import annotations

import json
from datetime import date

from ..db import now_iso
from ..sage.base import SageExtractionIncomplete, SageIndisponible
from ..text import normaliser_reference
from .auth import Utilisateur

COLONNES = ["vente_comptant", "vente_credit", "total_ventes", "recouvrements", "recette", "acompte"]


def valeurs_jour(res, regles: dict, mode_recette: str = "comptant+recouvrement") -> dict:
    """Chiffres d'une journee a partir de l'analyse du CR (sommes des lignes de detail du rapport)."""
    ctl = res.stats.get("controle_totaux", {})
    cols_f = regles["colonnes_facture"]
    col_c = (regles.get("factures_comptant", {}).get("colonnes") or [cols_f[0]])[0]
    col_t = next((c for c in cols_f if c != col_c), cols_f[-1])
    comptant = (ctl.get(f"documents_{col_c}") or {}).get("lignes", 0) or 0
    credit = (ctl.get(f"documents_{col_t}") or {}).get("lignes", 0) or 0
    recouv = (ctl.get(f"recus_{regles['colonne_montant_recu']}") or {}).get("lignes", 0) or 0
    acompte = res.stats.get("total_acompte_cr") or 0
    retenu = sum(m.montant for m in res.factures)
    recette = recouv + (acompte if mode_recette == "acompte+recouvrement" else comptant)
    return {"date_jour": res.date_rapport.isoformat(), "agence": res.agence, "vente_comptant": comptant,
            "vente_credit": credit, "total_ventes": comptant + credit, "recouvrements": recouv,
            "recette": recette, "acompte": acompte,
            "total_ventes_cellule_cr": res.stats.get("total_ventes_cellule_cr"), "total_ventes_retenu": retenu,
            "pieces_cr": _pieces_cr(res, cols_f)}


def _pieces_cr(res, cols_f) -> list:
    """Factures / avoirs du CR : lignes retenues + lignes de facture bloquees (une seule fois par ligne)."""
    lignes_retenues = {m.ligne for m in res.factures}
    out = [[m.reference_piece, m.client_libelle, m.montant] for m in res.factures]
    vues = set()
    for a in res.anomalies:
        if (a.gravite == "BLOQUANT" and a.montant and a.colonne in cols_f and a.ligne > 0
                and a.ligne not in lignes_retenues and a.ligne not in vues):
            vues.add(a.ligne)
            out.append([a.reference or "(sans n°)", a.client, a.montant])
    return out


def enregistrer_jour(db, v: dict, source: str = "", batch_id: int | None = None) -> None:
    """Enregistre (ou remplace) les chiffres CR d'une journee ; le resultat Sage est conserve s'il existe
    et que les chiffres n'ont pas change, sinon il repasse a NON_VERIFIE."""
    ex = db.one("SELECT * FROM etat_comparatif_jours WHERE agence=? AND date_jour=?", (v["agence"], v["date_jour"]))
    garder = ex is not None and ex["total_ventes"] == v["total_ventes"]
    db.execute(
        "INSERT INTO etat_comparatif_jours(agence, date_jour, vente_comptant, vente_credit, total_ventes, recouvrements, "
        "recette, acompte, total_ventes_cellule_cr, total_ventes_retenu, pieces_cr, source, batch_id, maj_le) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(agence, date_jour) DO UPDATE SET "
        "vente_comptant=excluded.vente_comptant, vente_credit=excluded.vente_credit, total_ventes=excluded.total_ventes, "
        "recouvrements=excluded.recouvrements, recette=excluded.recette, acompte=excluded.acompte, "
        "total_ventes_cellule_cr=excluded.total_ventes_cellule_cr, total_ventes_retenu=excluded.total_ventes_retenu, "
        "pieces_cr=excluded.pieces_cr, source=excluded.source, batch_id=excluded.batch_id, maj_le=excluded.maj_le",
        (v["agence"], v["date_jour"], v["vente_comptant"], v["vente_credit"], v["total_ventes"], v["recouvrements"],
         v["recette"], v["acompte"], v.get("total_ventes_cellule_cr"), v.get("total_ventes_retenu"),
         json.dumps(v.get("pieces_cr") or [], ensure_ascii=False), source, batch_id,
         now_iso()))
    if not garder:
        db.execute("UPDATE etat_comparatif_jours SET statut_sage='NON_VERIFIE', ventes_sage=NULL, ecart_sage=NULL, "
                   "detail_sage=NULL WHERE agence=? AND date_jour=?", (v["agence"], v["date_jour"]))


def charger_rapport_mensuel(db, user: Utilisateur, rapport, regles: dict, agence: str, mois: int | None = None,
                            annee: int | None = None, mode_recette: str = "comptant+recouvrement") -> int:
    """Alimente l'etat comparatif depuis un rapport mensuel (lecture seule, sans creer de mouvement).
    La date de chaque feuille est deduite du mois et du n° de feuille si `mois` est fourni (la date imprimee
    en A4 n'est pas fiable : en mai 2026, toutes les feuilles portaient une date d'avril)."""
    from openpyxl import load_workbook
    from ..excel.report_parser import ParseurRapport
    wb = load_workbook(rapport, read_only=True, data_only=True)
    n = 0
    try:
        with db.transaction():
            for f in [x for x in wb.sheetnames if x.isdigit()]:
                attendu = None
                if mois and annee:
                    try:
                        attendu = date(annee, mois, int(f))
                    except ValueError:
                        continue
                res = ParseurRapport(regles, {}).analyser([list(r) for r in wb[f].iter_rows(values_only=True)],
                                                          f, agence, attendu)
                if res.date_rapport is None:
                    continue
                enregistrer_jour(db, valeurs_jour(res, regles, mode_recette), source=str(rapport))
                n += 1
            if mois and annee:
                enregistrer_references_recap(db, agence, annee, mois, rapport, mode_recette)
            db.audit(user.login, "ETAT_COMPARATIF_CHARGE", str(rapport), {"jours": n})
    finally:
        wb.close()
    return n


def enregistrer_references_recap(db, agence: str, annee: int, mois: int, rapport, mode_recette: str) -> dict:
    """Lit les lignes TOTAL N-1 et TOTAL M-1 saisies dans la feuille RECAP du rapport du mois (annee, mois)."""
    from openpyxl import load_workbook
    from ..text import normaliser
    wb = load_workbook(rapport, read_only=True, data_only=True)
    out = {}
    try:
        if "RECAP" not in wb.sheetnames:
            return out
        for r in wb["RECAP"].iter_rows(values_only=True):
            if not r or not isinstance(r[0], str):
                continue
            lib = normaliser(r[0])
            typ = {"TOTAL N-1": "N-1_SAISI_RECAP", "TOTAL M-1": "M-1_SAISI_RECAP"}.get(lib)
            if typ is None or all(v in (None, "") for v in r[1:7]):
                continue
            acompte, comptant, credit, total, recouv = (int(v or 0) for v in r[1:6])
            recette = recouv + (acompte if mode_recette == "acompte+recouvrement" else comptant)
            ref = (annee - 1, mois) if typ.startswith("N-1") else ((annee, mois - 1) if mois > 1 else (annee - 1, 12))
            db.execute("INSERT INTO etat_comparatif_references VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(agence, annee, "
                       "mois, type) DO UPDATE SET vente_comptant=excluded.vente_comptant, vente_credit=excluded.vente_credit, "
                       "total_ventes=excluded.total_ventes, recouvrements=excluded.recouvrements, recette=excluded.recette, "
                       "acompte=excluded.acompte, source=excluded.source, maj_le=excluded.maj_le",
                       (agence, ref[0], ref[1], typ, comptant, credit, total, recouv, recette, acompte, str(rapport),
                        now_iso()))
            out[typ] = {"vente_comptant": comptant, "vente_credit": credit, "total_ventes": total,
                        "recouvrements": recouv, "recette": recette, "acompte": acompte}
    finally:
        wb.close()
    return out


def reference(db, agence, annee, mois, typ):
    r = db.one("SELECT * FROM etat_comparatif_references WHERE agence=? AND annee=? AND mois=? AND type=?",
               (agence, annee, mois, typ))
    return {c: r[c] for c in COLONNES} if r else None


def rapprocher_ventes_jour(db, user: Utilisateur, sage, agence: str, jour: date) -> dict:
    """Compare le total des ventes du CR avec les ventes comptabilisees dans Sage ce jour-la, piece par piece."""
    e = db.one("SELECT * FROM etat_comparatif_jours WHERE agence=? AND date_jour=?", (agence, jour.isoformat()))
    if e is None:
        raise ValueError(f"Aucun chiffre du CR pour le {jour:%d/%m/%Y}")
    try:
        pieces_sage = sage.ventes_du_jour(jour)
    except (SageIndisponible, SageExtractionIncomplete) as exc:
        with db.transaction():
            db.execute("UPDATE etat_comparatif_jours SET statut_sage='SAGE_INDISPONIBLE', detail_sage=?, verifie_le=?, "
                       "verifie_par=? WHERE agence=? AND date_jour=?",
                       (json.dumps({"erreur": str(exc)}), now_iso(), user.login, agence, jour.isoformat()))
        return {"statut": "SAGE_INDISPONIBLE", "message": str(exc)}
    total_sage = sum(p["montant"] for p in pieces_sage)
    sage_par_piece: dict[str, int] = {}
    for p in pieces_sage:
        k = normaliser_reference(p["piece"])
        sage_par_piece[k] = sage_par_piece.get(k, 0) + p["montant"]
    cr_par_piece: dict[str, int] = {}
    for piece, _client, montant in json.loads(e["pieces_cr"] or "[]"):
        k = normaliser_reference(piece)
        cr_par_piece[k] = cr_par_piece.get(k, 0) + (montant or 0)
    retenu = db.scalar("SELECT SUM(montant) FROM normalized_movements WHERE agence=? AND date_piece=? "
                       "AND nature IN ('FACTURE','AVOIR') AND statut<>'ANNULE'", (agence, jour.isoformat()), 0)
    absentes_sage = sorted((k, v) for k, v in cr_par_piece.items() if k not in sage_par_piece)
    absentes_cr = sorted((k, v) for k, v in sage_par_piece.items() if k not in cr_par_piece)
    differentes = sorted((k, cr_par_piece[k], sage_par_piece[k]) for k in cr_par_piece
                         if k in sage_par_piece and cr_par_piece[k] != sage_par_piece[k])
    ecart = e["total_ventes"] - total_sage
    statut = "CONCORDANT" if ecart == 0 else "ECART"
    detail = {"pieces_cr_absentes_de_sage": absentes_sage, "pieces_sage_absentes_du_cr": absentes_cr,
              "montants_differents": differentes, "nb_pieces_sage": len(sage_par_piece),
              "nb_pieces_cr": len(cr_par_piece), "total_retenu_fiches": retenu}
    with db.transaction():
        db.execute("UPDATE etat_comparatif_jours SET ventes_sage=?, ecart_sage=?, statut_sage=?, detail_sage=?, "
                   "verifie_le=?, verifie_par=?, total_ventes_retenu=? WHERE agence=? AND date_jour=?",
                   (total_sage, ecart, statut, json.dumps(detail), now_iso(), user.login, retenu, agence,
                    jour.isoformat()))
        db.audit(user.login, "RAPPROCHEMENT_VENTES_JOUR", jour.isoformat(), {"cr": e["total_ventes"], "sage": total_sage,
                                                                             "ecart": ecart})
    return {"statut": statut, "ventes_cr": e["total_ventes"], "ventes_sage": total_sage, "ecart": ecart, **detail}


def rapprocher_ventes_mois(db, user: Utilisateur, sage, agence: str, annee: int, mois: int) -> dict:
    out = {}
    for r in jours_du_mois(db, agence, annee, mois):
        out[r["date_jour"]] = rapprocher_ventes_jour(db, user, sage, agence, date.fromisoformat(r["date_jour"]))["statut"]
    return out


def jours_du_mois(db, agence: str, annee: int, mois: int):
    return db.query("SELECT * FROM etat_comparatif_jours WHERE agence=? AND date_jour LIKE ? ORDER BY date_jour",
                    (agence, f"{annee:04d}-{mois:02d}-%"))


def mois_disponibles(db, agence: str) -> list[tuple[int, int]]:
    return [(int(r[0][:4]), int(r[0][5:7])) for r in db.query(
        "SELECT DISTINCT substr(date_jour,1,7) FROM etat_comparatif_jours WHERE agence=? ORDER BY 1 DESC", (agence,))]


def _totaux(rows) -> dict:
    return {c: sum(r[c] or 0 for r in rows) for c in COLONNES}


def tableau_mois(db, agence: str, annee: int, mois: int) -> dict:
    """Lignes journalieres + TOTAL M, TOTAL M-1, EVOLUTION, TOTAL N-1, ECART N/(N-1) (modele RECAP)."""
    rows = jours_du_mois(db, agence, annee, mois)
    m1 = (annee, mois - 1) if mois > 1 else (annee - 1, 12)
    rows_m1 = jours_du_mois(db, agence, *m1)
    rows_n1 = jours_du_mois(db, agence, annee - 1, mois)
    tm = _totaux(rows)
    t_m1 = _totaux(rows_m1) if rows_m1 else None
    t_n1 = _totaux(rows_n1) if rows_n1 else reference(db, agence, annee - 1, mois, "N-1_SAISI_RECAP")
    return {"jours": rows, "total_m": tm, "total_m1": t_m1,
            "source_n1": "rapports" if rows_n1 else ("saisi" if t_n1 else None),
            "m1_saisi_recap": reference(db, agence, *m1, "M-1_SAISI_RECAP"),
            "evolution": {c: tm[c] - t_m1[c] for c in COLONNES} if t_m1 else None,
            "total_n1": t_n1, "ecart_n1": {c: tm[c] - t_n1[c] for c in COLONNES} if t_n1 else None,
            "creance_fin": creance(db, agence, annee, mois), "creance_debut": creance(db, agence, *m1),
            "sage": {"ventes_sage": sum(r["ventes_sage"] or 0 for r in rows if r["ventes_sage"] is not None),
                     "jours_concordants": sum(1 for r in rows if r["statut_sage"] == "CONCORDANT"),
                     "jours_ecart": sum(1 for r in rows if r["statut_sage"] == "ECART"),
                     "jours_non_verifies": sum(1 for r in rows if r["statut_sage"] in ("NON_VERIFIE", "SAGE_INDISPONIBLE"))}}


NOMS_MOIS = ["JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE",
             "NOVEMBRE", "DECEMBRE"]


# Modele GTC « ETAT CHIFFRE D'AFFAIRE » : DATES | CHIFFRE D'AFFAIRE (TOTAL, COMPTANT, CREDIT, RECOUVREMENT,
# TOTAL RECETTE). CREDIT = TOTAL - COMPTANT ; TOTAL RECETTE = COMPTANT + RECOUVREMENT.
COLONNES_ETAT = ["total_ventes", "vente_comptant", "vente_credit", "recouvrements", "recette"]
ENTETE_ETAT = ["DATES", "TOTAL", "COMPTANT", "CREDIT", "RECOUVREMENT", "TOTAL RECETTE"]


def exporter_excel(db, agence: str, mois_liste: list[tuple[int, int]], dest, societe: str = "") -> str:
    """Classeur Excel :
    - une feuille par mois : l'ETAT CHIFFRE D'AFFAIRE au modele GTC (jusqu'au TOTAL RECETTE, puis creances) ;
    - RAPPROCHEMENT VENTES SAGE : total des ventes du CR / ventes comptabilisees dans Sage, par jour ;
    - CONTROLES : TOTAL M-1 saisi dans RECAP compare au M-1 calcule, acompte et cellule du CR (information)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    wb = Workbook()
    wb.remove(wb.active)
    gras = Font(bold=True)
    bleu = PatternFill("solid", fgColor="DDEBF7")
    rouge = PatternFill("solid", fgColor="FFEBEE")
    vert = PatternFill("solid", fgColor="E8F5E9")
    fin = Side(style="thin", color="999999")
    cadre = Border(left=fin, right=fin, top=fin, bottom=fin)

    def entete(ws, cols):
        ws.append(cols)
        for c in ws[ws.max_row]:
            c.font, c.fill, c.border = gras, bleu, cadre
            c.alignment = Alignment(wrap_text=True, horizontal="center")

    def montants(ws, debut):
        for row in ws.iter_rows(min_row=debut, max_row=ws.max_row):
            for c in row:
                if isinstance(c.value, int) and not isinstance(c.value, bool):
                    c.number_format = "# ##0"
                elif isinstance(c.value, date):
                    c.number_format = "DD/MM/YYYY"

    tableaux = {}
    for annee, mois in sorted(mois_liste):
        t = tableaux[(annee, mois)] = tableau_mois(db, agence, annee, mois)
        feuille_modele(wb, t, annee, mois)

    ws = wb.create_sheet("RAPPROCHEMENT VENTES SAGE")
    ws.append(["Total des ventes du CR / ventes comptabilisees dans Sage le meme jour (factures comptant + credit, "
               "avoirs deduits)"])
    ws["A1"].font = gras
    entete(ws, ["DATE", "TOTAL VENTES CR", "VENTES SAGE", "ECART CR - SAGE", "STATUT", "INTEGRE AUX FICHES",
                "PIECES CR ABSENTES DE SAGE", "PIECES SAGE ABSENTES DU CR", "MONTANTS DIFFERENTS"])
    for (annee, mois), t in tableaux.items():
        for r in t["jours"]:
            d = json.loads(r["detail_sage"]) if r["detail_sage"] else {}
            ws.append([date.fromisoformat(r["date_jour"]), r["total_ventes"], r["ventes_sage"], r["ecart_sage"],
                       r["statut_sage"], r["total_ventes_retenu"],
                       ", ".join(f"{p} ({m})" for p, m in d.get("pieces_cr_absentes_de_sage", [])),
                       ", ".join(f"{p} ({m})" for p, m in d.get("pieces_sage_absentes_du_cr", [])),
                       ", ".join(f"{p} (CR {a} / Sage {b})" for p, a, b in d.get("montants_differents", []))])
            if r["statut_sage"] in ("ECART", "CONCORDANT"):
                ws[ws.max_row][4].fill = rouge if r["statut_sage"] == "ECART" else vert
    montants(ws, 3)
    for col, larg in zip("ABCDEFGHI", (12, 17, 17, 16, 18, 17, 45, 45, 45)):
        ws.column_dimensions[col].width = larg
    ws.freeze_panes = "B3"

    ws = wb.create_sheet("CONTROLES")
    entete(ws, ["MOIS", "CONTROLE", "VENTE COMPTANT", "VENTE A CREDIT", "TOTAL VENTES", "RECOUVREMENTS",
                "RECETTE TOTALE"])
    for (annee, mois), t in tableaux.items():
        lib = f"{NOMS_MOIS[mois - 1]} {annee}"
        if t.get("m1_saisi_recap"):
            ws.append([lib, "TOTAL M-1 saisi dans RECAP"] + [t["m1_saisi_recap"][c] for c in COLONNES_ETAT])
            if t["total_m1"]:
                ws.append([lib, "Ecart M-1 saisi - M-1 calcule"]
                          + [t["m1_saisi_recap"][c] - t["total_m1"][c] for c in COLONNES_ETAT])
        acompte = sum(r["acompte"] or 0 for r in t["jours"])
        cellule = [r for r in t["jours"] if r["total_ventes_cellule_cr"] is not None
                   and r["total_ventes_cellule_cr"] != r["total_ventes"]]
        ws.append([lib, f"Acompte du mois (colonne ENTREE des BC, information) : {acompte}"])
        ws.append([lib, "Cellule 'vente totale' du CR = comptant + credit" if not cellule else
                   "Cellule 'vente totale' du CR differente : " + ", ".join(r["date_jour"] for r in cellule)])
    montants(ws, 2)
    for col, larg in zip("ABCDEFG", (16, 60, 17, 17, 17, 17, 17)):
        ws.column_dimensions[col].width = larg
    wb.save(dest)
    return str(dest)



# -- Creances clients de fin de mois --------------------------------------------------------------
def creance(db, agence: str, annee: int, mois: int) -> int | None:
    r = db.one("SELECT vente_credit FROM etat_comparatif_references WHERE agence=? AND annee=? AND mois=? "
               "AND type='CREANCE_FIN_MOIS'", (agence, annee, mois))
    return r[0] if r else None


def enregistrer_creance(db, agence: str, annee: int, mois: int, montant: int, source: str) -> None:
    db.execute("INSERT INTO etat_comparatif_references(agence, annee, mois, type, vente_credit, source, maj_le) "
               "VALUES (?,?,?, 'CREANCE_FIN_MOIS', ?,?,?) ON CONFLICT(agence, annee, mois, type) DO UPDATE SET "
               "vente_credit=excluded.vente_credit, source=excluded.source, maj_le=excluded.maj_le",
               (agence, annee, mois, int(montant), source, now_iso()))


def fin_de_mois(annee: int, mois: int) -> date:
    import calendar
    return date(annee, mois, calendar.monthrange(annee, mois)[1])


def calculer_creance(db, user: Utilisateur, sage, agence: str, annee: int, mois: int) -> dict:
    """Creance clients au dernier jour du mois : somme des soldes des comptes clients dans Sage (lecture seule).
    A defaut de Sage, somme des soldes des fiches si TOUS les clients mouvementes ont un solde d'ouverture.
    Sinon : non disponible (jamais de creance approximative)."""
    jour = fin_de_mois(annee, mois)
    try:
        montant = sum(sage.soldes_a_date(jour).values())
        source = f"Sage ({sage.nom}) au {jour:%d/%m/%Y}"
    except (SageIndisponible, SageExtractionIncomplete) as exc:
        from .ledger import fiche_client
        cts = [r[0] for r in db.query("SELECT DISTINCT ct_num FROM normalized_movements WHERE statut<>'ANNULE' "
                                      "AND date_piece<=?", (jour.isoformat(),))]
        sans = [ct for ct in cts if not db.one("SELECT 1 FROM opening_balances WHERE ct_num=? AND date_reference<=?",
                                               (ct, jour.isoformat()))]
        if not cts or sans:
            return {"statut": "NON_DISPONIBLE", "message": f"Sage indisponible ({exc}) et {len(sans)} client(s) sans "
                                                           "solde d'ouverture : creance non calculable"}
        montant = sum(fiche_client(db, ct, jour).solde_final for ct in cts)
        source = f"fiches clients au {jour:%d/%m/%Y} (Sage indisponible)"
    with db.transaction():
        enregistrer_creance(db, agence, annee, mois, montant, source)
        db.audit(user.login, "CREANCE_FIN_MOIS", f"{annee}-{mois:02d}", {"montant": montant, "source": source})
    return {"statut": "OK", "montant": montant, "source": source}


# -- Feuille au modele « ETAT CHIFFRE D'AFFAIRE » ------------------------------------------------------
def _libelle_mois(annee, mois):
    return f"{NOMS_MOIS[mois - 1]} {annee}"


def feuille_modele(wb, t: dict, annee: int, mois: int):
    """Reproduit la feuille mensuelle du modele GTC, avec formules Excel vivantes comme dans le modele :
    CREDIT = TOTAL - COMPTANT ; TOTAL RECETTE = COMPTANT + RECOUVREMENT ; TOTAL = somme ; VARIATION = difference.
    Les lignes M-1, N-1 et creances ne sont plus saisies a la main : elles sont calculees par le logiciel."""
    from openpyxl.styles import Alignment, Border, Font, Side
    fmt = '_-* #,##0\\ _€_-;\\-* #,##0\\ _€_-;_-* "-"??\\ _€_-;_-@_-'
    fin = Side(style="thin")
    cadre = Border(left=fin, right=fin, top=fin, bottom=fin)
    police = Font(name="Calibri", size=14)
    gras = Font(name="Calibri", size=14, bold=True)
    centre = Alignment(horizontal="center", vertical="center")
    ws = wb.create_sheet(NOMS_MOIS[mois - 1] if annee is None else f"{NOMS_MOIS[mois - 1]} {annee}"[:31])
    ws["A1"] = f"ETAT CHIFFRE D'AFFAIRE MOIS {NOMS_MOIS[mois - 1]} {annee}"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True)
    ws["A1"].alignment = centre
    ws.merge_cells("A1:F1")
    ws["A2"], ws["B2"] = "DATES", "CHIFFRE D'AFFAIRE"
    ws.merge_cells("A2:A3")
    ws.merge_cells("B2:F2")
    for i, lib in enumerate(ENTETE_ETAT[1:], 2):
        ws.cell(3, i, lib)
    for r in (2, 3):
        for c in range(1, 7):
            cell = ws.cell(r, c)
            cell.font, cell.alignment, cell.border = gras, centre, cadre
    import calendar
    par_jour = {x["date_jour"]: x for x in t["jours"]}
    ligne = 4
    for j in range(1, calendar.monthrange(annee, mois)[1] + 1):
        d = date(annee, mois, j)
        x = par_jour.get(d.isoformat())
        ws.cell(ligne, 1, d).number_format = "DD/MM/YYYY"
        ws.cell(ligne, 2, x["total_ventes"] if x else 0)
        ws.cell(ligne, 3, x["vente_comptant"] if x else 0)
        ws.cell(ligne, 4, f"=B{ligne}-C{ligne}")
        ws.cell(ligne, 5, x["recouvrements"] if x else 0)
        ws.cell(ligne, 6, f"=C{ligne}+E{ligne}")
        ligne += 1
    l_tot = ligne
    ws.cell(l_tot, 1, "TOTAL")
    for c, col in zip(range(2, 7), "BCDEF"):
        ws.cell(l_tot, c, f"=SUM({col}4:{col}{l_tot - 1})")
    m1 = (annee, mois - 1) if mois > 1 else (annee - 1, 12)

    def ligne_valeurs(r, lib, vals):
        ws.cell(r, 1, lib)
        for c, cle in zip(range(2, 7), COLONNES_ETAT):
            ws.cell(r, c, vals[cle] if vals else None)

    ligne_valeurs(l_tot + 1, f"Total {_libelle_mois(*m1)}", t["total_m1"])
    ws.cell(l_tot + 2, 1, "VARIATION")
    for c, col in zip(range(2, 7), "BCDEF"):
        ws.cell(l_tot + 2, c, f"={col}{l_tot}-{col}{l_tot + 1}" if t["total_m1"] else None)
    ligne_valeurs(l_tot + 3, f"Total {_libelle_mois(annee - 1, mois)}"
                  + (" (saisi)" if t.get("source_n1") == "saisi" else ""), t["total_n1"])
    ws.cell(l_tot + 4, 1, "VARIATION")
    for c, col in zip(range(2, 7), "BCDEF"):
        ws.cell(l_tot + 4, c, f"={col}{l_tot}-{col}{l_tot + 3}" if t["total_n1"] else None)
    fin_m, fin_m1 = fin_de_mois(annee, mois), fin_de_mois(*m1)
    lc = l_tot + 5
    for k, (lib, val) in enumerate(((f"CREANCE AU {fin_m:%d-%m-%y}", t.get("creance_fin")),
                                    (f"CREANCE AU {fin_m1:%d-%m-%y}", t.get("creance_debut")),
                                    ("VARIATION", None))):
        r = lc + k
        ws.cell(r, 1, lib)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        if k < 2:
            ws.cell(r, 4, val if val is not None else "n/d")
        elif t.get("creance_fin") is not None and t.get("creance_debut") is not None:
            ws.cell(r, 4, f"=D{lc}-D{lc + 1}")
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
    for row in ws.iter_rows(min_row=4, max_row=lc + 2, max_col=6):
        for cell in row:
            cell.border = cadre
            cell.font = gras if row[0].row >= l_tot else police
            if cell.column > 1:
                cell.number_format = fmt
    for col, larg in zip("ABCDEF", (33.6, 25.4, 23, 23, 23, 25.4)):
        ws.column_dimensions[col].width = larg
    ws.freeze_panes = "B4"
    return ws


# -- Import d'un etat existant au modele « ETAT CHIFFRE D'AFFAIRE » -------------------------------------
def charger_etat_modele(db, user: Utilisateur, path, agence: str) -> dict:
    """Charge un classeur au modele GTC (une feuille par mois) comme historique de l'etat comparatif d'une
    agence (ex. annee N-1), et controle ses lignes saisies a la main (Total M-1 et creances)."""
    import re
    from openpyxl import load_workbook
    from ..text import normaliser
    wb = load_workbook(path, data_only=True)
    controles, jours, mois_vus = [], 0, []
    precedent = None
    try:
        with db.transaction():
            for ws in wb.worksheets:
                rows = list(ws.iter_rows(values_only=True))
                lignes = [r for r in rows[3:] if r and hasattr(r[0], "year")]
                if not lignes:
                    continue
                annee, mois = lignes[0][0].year, lignes[0][0].month
                mois_vus.append((annee, mois))
                for r in lignes:
                    total, comptant, recouv = (int(r[k] or 0) for k in (1, 2, 4))
                    enregistrer_jour(db, {"agence": agence, "date_jour": r[0].date().isoformat(), "total_ventes": total,
                                          "vente_comptant": comptant, "vente_credit": total - comptant,
                                          "recouvrements": recouv, "recette": comptant + recouv, "acompte": 0,
                                          "total_ventes_cellule_cr": None, "total_ventes_retenu": None,
                                          "pieces_cr": []}, source=f"etat CA : {path}")
                    jours += 1
                calc = _totaux(jours_du_mois(db, agence, annee, mois))
                dates_creances = []
                for r in rows:
                    if r and isinstance(r[0], str):
                        m0 = re.match(r"^CREANCE AU (\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", normaliser(r[0]))
                        if m0:
                            dates_creances.append((int(m0.group(3)) % 100 + 2000, int(m0.group(2)), int(m0.group(1))))
                fm = fin_de_mois(annee, mois)
                if dates_creances and (fm.year, fm.month, fm.day) not in dates_creances:
                    controles.append([ws.title, "CREANCES", "Creance au " + fm.strftime("%d-%m-%y") + " absente : les lignes "
                                      "CREANCE n'ont pas ete mises a jour pour ce mois (libelles "
                                      + ", ".join(f"{j:02d}-{m:02d}-{a % 100:02d}" for a, m, j in dates_creances)
                                      + ") ; variation des creances fausse"])
                for r in rows:
                    if not r or not isinstance(r[0], str):
                        continue
                    lib = normaliser(r[0])
                    m = re.match(r"^CREANCE AU (\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", lib)
                    if m and r[3] is not None:
                        j, mo, an = int(m.group(1)), int(m.group(2)), int(m.group(3)) % 100 + 2000
                        if (j, mo) == (1, 1) and mois != 1:
                            controles.append([ws.title, lib, "Libelle de date incoherent (creance de fin de mois "
                                                             "precedent attendue)"])
                            mo, an = (mois - 1, annee) if mois > 1 else (12, annee - 1)
                        deja = creance(db, agence, an, mo)
                        if deja is not None and deja != int(r[3]):
                            controles.append([ws.title, lib, f"Creance saisie {int(r[3])} differente de celle de "
                                                             f"l'autre feuille ({deja}) : ecart {int(r[3]) - deja}"])
                        elif deja is None:
                            enregistrer_creance(db, agence, an, mo, int(r[3]), f"saisi dans {ws.title}")
                    elif lib.startswith("TOTAL ") and normaliser(NOMS_MOIS[mois - 1]) in lib and str(annee - 1) in lib \
                            and r[1] is not None:
                        # Total du meme mois N-1 saisi dans l'etat : reference N-1 (faute de donnees detaillees)
                        tot, cpt, cre, rec, ret = (int(v or 0) for v in r[1:6])
                        db.execute("INSERT INTO etat_comparatif_references VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                                   "ON CONFLICT(agence, annee, mois, type) DO UPDATE SET total_ventes=excluded.total_ventes, "
                                   "vente_comptant=excluded.vente_comptant, vente_credit=excluded.vente_credit, "
                                   "recouvrements=excluded.recouvrements, recette=excluded.recette, source=excluded.source, "
                                   "maj_le=excluded.maj_le",
                                   (agence, annee - 1, mois, "N-1_SAISI_RECAP", cpt, cre, tot, rec, ret, 0,
                                    f"saisi dans {ws.title}", now_iso()))
                    elif lib.startswith("TOTAL ") and lib != "TOTAL" and precedent and \
                            normaliser(NOMS_MOIS[precedent[1] - 1]) in lib.replace("DECEMBRE N-1", "DECEMBRE"):
                        saisi = {"total_ventes": r[1], "vente_comptant": r[2], "vente_credit": r[3],
                                 "recouvrements": r[4], "recette": r[5]}
                        ref = _totaux(jours_du_mois(db, agence, *precedent))
                        ecarts = {c: int(saisi[c] or 0) - ref[c] for c in COLONNES_ETAT if int(saisi[c] or 0) != ref[c]}
                        if ecarts:
                            controles.append([ws.title, r[0], "Total du mois precedent saisi different du TOTAL de "
                                                              f"la feuille precedente : {ecarts}"])
                precedent = (annee, mois)
                del calc
            db.audit(user.login, "ETAT_CA_IMPORTE", str(path), {"jours": jours, "controles": len(controles)})
    finally:
        wb.close()
    return {"jours": jours, "mois": mois_vus, "controles": controles}
