"""Test de concordance A EXECUTER SUR L'INSTALLATION SAGE REELLE (lecture seule).

1) verifie l'existence des tables/colonnes utilisees par l'adaptateur (INFORMATION_SCHEMA) ;
2) execute chaque requete configuree (sans rien ecrire) ;
3) calcule le solde de quelques clients a une date pour comparaison MANUELLE avec
   l'interface Sage (Comptabilite > consultation / balance des tiers).
Produit docs/concordance_sage_<date>.txt a joindre au dossier de recette.

Usage : python tools/verifier_sage.py --config config.json --date 31/10/2026 --clients CL001,CL002
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gtc_compta.config import load_config  # noqa: E402
from gtc_compta.sage.sql_adapter import SqlSageAdapter, verifier_lecture_seule  # noqa: E402

COLONNES = {
    "F_COMPTET": ["CT_Num", "CT_Intitule", "CT_Telephone", "CT_Ville", "CT_Encours", "CT_Type"],
    "F_ECRITUREC": ["EC_No", "CT_Num", "CG_Num", "JO_Num", "EC_Date", "EC_Piece", "EC_RefPiece", "EC_Intitule",
                    "EC_Sens", "EC_Montant", "EC_Echeance", "EC_Lettre"],
    "F_DOCENTETE": ["DO_Domaine", "DO_Type", "DO_Piece", "DO_Tiers", "DO_Date", "DO_TotalTTC"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--clients", default="")
    a = ap.parse_args()
    cfg = load_config(a.config)
    d = datetime.strptime(a.date, "%d/%m/%Y").date()
    sage = SqlSageAdapter(cfg["sage"])
    out = [f"Concordance Sage - {datetime.now():%Y-%m-%d %H:%M} - {sage.nom}", ""]
    for base_key in ("database_compta", "database_gescom"):
        cn = sage._connect(base_key)
        cur = cn.cursor()
        out.append(f"== Base {cfg['sage'][base_key]}")
        for table, cols in COLONNES.items():
            q = ("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?")
            verifier_lecture_seule(q)
            cur.execute(q, table)
            reel = {r[0]: r[1] for r in cur.fetchall()}
            if not reel:
                out.append(f"  {table} : ABSENTE")
                continue
            manq = [c for c in cols if c not in reel]
            out.append(f"  {table} : presente ; colonnes manquantes : {manq or 'aucune'}")
        cn.rollback()
        cn.close()
    out.append("")
    for ct in [c for c in a.clients.split(",") if c]:
        try:
            ecr = sage.ecritures_client(ct, None, d)
            out.append(f"{ct} : {len(ecr)} ecritures, solde calcule au {d:%d/%m/%Y} = {sum(e.signe for e in ecr)}"
                       "   -> COMPARER avec Sage : ______________  OK / ECART")
        except Exception as exc:  # noqa: BLE001
            out.append(f"{ct} : ERREUR {exc}")
    p = ROOT / "docs" / f"concordance_sage_{datetime.now():%Y%m%d_%H%M}.txt"
    p.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\nRapport : {p}")


if __name__ == "__main__":
    main()
