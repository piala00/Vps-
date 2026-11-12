"""Verification sur l'installation Sage REELLE - LECTURE SEULE (aucune ecriture, uniquement des SELECT).

Etapes (chacune affiche son resultat ; une erreur n'arrete pas les suivantes) :
  0. pilotes ODBC disponibles ;
  1. (--lister-bases) bases presentes sur le serveur, pour remplir database_compta / database_gescom ;
  2. tables et colonnes utilisees par le logiciel (INFORMATION_SCHEMA) ;
  3. journaux (F_JOURNAUX) et utilisation de chaque journal sur les comptes clients pendant le mois
     -> confirme le code du journal des ventes (sage.journaux_ventes) et la colonne qui porte le n° de facture ;
  4. (--jour) ventes comptabilisees dans Sage ce jour-la ; avec --rapport : comparaison piece par piece
     avec le CR du meme jour (feuille JJ) ;
  5. (--clients) solde de quelques clients a --date, a comparer a l'ecran Sage.

Le compte rendu est enregistre dans data/verification_sage_<date>.txt (dossier non versionne : il contient
des donnees clients). L'envoyer a la personne qui assure le support.

Exemples :
  python tools/verifier_sage.py --config config.json --lister-bases
  python tools/verifier_sage.py --config config.json --jour 01/10/2026 --rapport "C:\\CR\\10 RC OCT.xlsx"
  python tools/verifier_sage.py --config config.json --date 31/10/2026 --clients 411CL001,411CL002
"""
import argparse
import copy
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gtc_compta.config import load_config  # noqa: E402
from gtc_compta.sage.sql_adapter import SqlSageAdapter, verifier_lecture_seule  # noqa: E402

COLONNES = {
    "F_COMPTET": ["CT_Num", "CT_Intitule", "CT_Telephone", "CT_Ville", "CT_Encours", "CT_Type"],
    "F_ECRITUREC": ["EC_No", "CT_Num", "CG_Num", "JO_Num", "EC_Date", "EC_Piece", "EC_RefPiece", "EC_Intitule",
                    "EC_Sens", "EC_Montant", "EC_Echeance", "EC_Lettre"],
    "F_JOURNAUX": ["JO_Num", "JO_Intitule", "JO_Type"],
    "F_DOCENTETE": ["DO_Domaine", "DO_Type", "DO_Piece", "DO_Tiers", "DO_Date", "DO_TotalTTC"],
}
SORTIE: list[str] = []


def dire(txt=""):
    print(txt, flush=True)
    SORTIE.append(str(txt))


def fcfa(v):
    return f"{int(v):,}".replace(",", " ") if v is not None else ""


def requete(sage, sql, params=(), base_key="database_compta"):
    verifier_lecture_seule(sql)
    cn = sage._connect(base_key)
    try:
        cur = cn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cn.rollback()
        cn.close()


def etape(titre, fn):
    dire("")
    dire(f"== {titre}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - on affiche et on continue
        dire(f"  ERREUR : {exc}")


def main():
    ap = argparse.ArgumentParser(description="Verification Sage en lecture seule")
    ap.add_argument("--config", required=True)
    ap.add_argument("--lister-bases", action="store_true", help="liste les bases du serveur SQL")
    ap.add_argument("--jour", help="JJ/MM/AAAA : ventes comptabilisees dans Sage ce jour-la")
    ap.add_argument("--rapport", help="CR du mois (xlsx) pour comparer la journee --jour piece par piece")
    ap.add_argument("--mois", help="MM/AAAA pour l'utilisation des journaux (defaut : mois de --jour ou --date)")
    ap.add_argument("--date", help="JJ/MM/AAAA : date d'arrete des soldes clients (--clients)")
    ap.add_argument("--clients", default="", help="codes clients Sage separes par des virgules")
    a = ap.parse_args()
    cfg = load_config(a.config)
    cs = cfg["sage"]
    sage = SqlSageAdapter(cs)
    jour = datetime.strptime(a.jour, "%d/%m/%Y").date() if a.jour else None
    d_solde = datetime.strptime(a.date, "%d/%m/%Y").date() if a.date else None
    if a.mois:
        mm, aa = (int(x) for x in a.mois.split("/"))
    else:
        ref = jour or d_solde or (date.today().replace(day=1) - timedelta(days=1))
        mm, aa = ref.month, ref.year
    debut = date(aa, mm, 1)
    fin = (date(aa + (mm == 12), mm % 12 + 1, 1) - timedelta(days=1))

    dire(f"Verification Sage (lecture seule) - {datetime.now():%d/%m/%Y %H:%M}")
    dire(f"Serveur {cs.get('server')} ; base compta '{cs.get('database_compta')}' ; base gestion "
         f"'{cs.get('database_gescom')}' ; mode {cs.get('mode')} ; compte clients {cs.get('compte_collectif_clients')}* ;"
         f" journaux de ventes configures {cs.get('journaux_ventes')}")
    if cs.get("mode") != "sql":
        dire("  ATTENTION : sage.mode n'est pas 'sql' dans config.json : l'application restera en demonstration.")

    def pilotes():
        import pyodbc
        drv = pyodbc.drivers()
        dire(f"  Pilotes ODBC : {', '.join(drv) or 'AUCUN'}")
        if not any("SQL Server" in x for x in drv):
            dire("  -> installer 'ODBC Driver 17 (ou 18) for SQL Server' (Microsoft).")
    etape("0. Pilotes ODBC", pilotes)

    if a.lister_bases:
        def bases():
            s2 = SqlSageAdapter({**copy.deepcopy(cs), "database_compta": "master"})
            for (nom,) in requete(s2, "SELECT name FROM sys.databases ORDER BY name"):
                dire(f"  {nom}")
            dire("  -> reporter le nom de la base comptable dans sage.database_compta, et celui de la base "
                 "gestion commerciale dans sage.database_gescom.")
        etape("1. Bases du serveur", bases)

    def tables():
        for base_key in ("database_compta", "database_gescom"):
            if not cs.get(base_key):
                dire(f"  {base_key} : non renseignee (ignoree)")
                continue
            dire(f"  Base {cs[base_key]} :")
            for table, cols in COLONNES.items():
                reel = {r[0] for r in requete(sage, "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                                                    "WHERE TABLE_NAME = ?", (table,), base_key)}
                if not reel:
                    dire(f"    {table} : absente")
                    continue
                manq = [c for c in cols if c not in reel]
                dire(f"    {table} : presente ; colonnes manquantes : {', '.join(manq) or 'aucune'}")
    etape("2. Tables et colonnes", tables)

    def journaux():
        for jo, lib, typ in requete(sage, "SELECT JO_Num, JO_Intitule, JO_Type FROM F_JOURNAUX ORDER BY JO_Num"):
            dire(f"  {str(jo).strip():<8} type {typ}  {str(lib or '').strip()}")
        dire("")
        dire(f"  Utilisation sur les comptes clients du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} :")
        dire(f"  {'Journal':<8} {'Lignes':>7} {'Debit':>16} {'Credit':>16}  Exemples EC_Piece / EC_RefPiece")
        rows = requete(sage, "SELECT JO_Num, COUNT(*), SUM(CASE WHEN EC_Sens = 0 THEN EC_Montant ELSE 0 END), "
                             "SUM(CASE WHEN EC_Sens = 1 THEN EC_Montant ELSE 0 END), MIN(EC_Piece), MAX(EC_Piece), "
                             "MIN(EC_RefPiece), MAX(EC_RefPiece) FROM F_ECRITUREC WHERE CG_Num LIKE ? "
                             "AND EC_Date BETWEEN ? AND ? GROUP BY JO_Num ORDER BY JO_Num", (sage.compte, debut, fin))
        for jo, n, deb, cre, p1, p2, r1, r2 in rows:
            dire(f"  {str(jo).strip():<8} {n:>7} {fcfa(deb):>16} {fcfa(cre):>16}  {str(p1).strip()} .. "
                 f"{str(p2).strip()} / {str(r1 or '').strip()} .. {str(r2 or '').strip()}")
        dire("  -> le journal des ventes est celui dont les pieces sont des FACB/FRCB/FVCB ; indiquer son code "
             "dans sage.journaux_ventes.")
        dire("  -> si les n° FACB sont dans EC_RefPiece et non dans EC_Piece, le signaler (requete a adapter).")
    etape("3. Journaux", journaux)

    if jour:
        def ventes():
            pieces = sage.ventes_du_jour(jour)
            total = sum(p["montant"] for p in pieces)
            dire(f"  Sage, journaux {cs.get('journaux_ventes')} le {jour:%d/%m/%Y} : {len(pieces)} piece(s), "
                 f"total {fcfa(total)}")
            for p in pieces[:15]:
                dire(f"    {p['piece']:<14} {p['ct_num']:<14} {fcfa(p['montant']):>14}")
            if len(pieces) > 15:
                dire(f"    ... ({len(pieces) - 15} autres)")
            if not a.rapport:
                return
            from gtc_compta.excel.report_parser import ParseurRapport, lire_feuille
            from gtc_compta.services import etat_comparatif as ec
            feuille = f"{jour.day:02d}"
            res = ParseurRapport(cfg["rapport"], {}).analyser(lire_feuille(a.rapport, feuille), feuille,
                                                              cfg["agence"], jour)
            v = ec.valeurs_jour(res, cfg["rapport"], cfg["etat_comparatif"]["recette"])
            c = ec.comparer_pieces(v["pieces_cr"], pieces)
            dire("")
            dire(f"  CR feuille {feuille} : comptant {fcfa(v['vente_comptant'])} + credit {fcfa(v['vente_credit'])} "
                 f"= TOTAL VENTES {fcfa(v['total_ventes'])}")
            ecart = v["total_ventes"] - total
            dire(f"  ECART CR - SAGE : {fcfa(ecart)}  -> {'CONCORDANT' if ecart == 0 else 'ECART A ANALYSER'}")
            for titre, cle in (("Pieces du CR absentes de Sage", "pieces_cr_absentes_de_sage"),
                               ("Pieces Sage absentes du CR", "pieces_sage_absentes_du_cr")):
                dire(f"  {titre} : {len(c[cle])}")
                for k, m in c[cle][:30]:
                    dire(f"    {k:<14} {fcfa(m):>14}")
            dire(f"  Montants differents : {len(c['montants_differents'])}")
            for k, m1, m2 in c["montants_differents"][:30]:
                dire(f"    {k:<14} CR {fcfa(m1):>14}  Sage {fcfa(m2):>14}")
        etape(f"4. Ventes du {jour:%d/%m/%Y}", ventes)

    if a.clients:
        def soldes():
            if not d_solde:
                dire("  --date obligatoire avec --clients")
                return
            for ct in [c.strip() for c in a.clients.split(",") if c.strip()]:
                ecr = sage.ecritures_client(ct, None, d_solde)
                dire(f"  {ct} : {len(ecr)} ecritures, solde au {d_solde:%d/%m/%Y} = {fcfa(sum(e.signe for e in ecr))}"
                     "   -> comparer avec Sage : ____________ OK / ECART")
        etape("5. Soldes clients", soldes)

    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    p = out / f"verification_sage_{datetime.now():%Y%m%d_%H%M}.txt"
    p.write_text("\n".join(SORTIE), encoding="utf-8")
    print(f"\nCompte rendu : {p}")


if __name__ == "__main__":
    main()
