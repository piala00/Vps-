"""Construit le MODELE (sans macro) GTC_PREPARATION_JOURNALIERE_modele.xlsx a partir de la
configuration. Le .xlsm est ensuite produit sous Windows par vba/CONSTRUIRE_XLSM.ps1, qui
importe le module VBA dans Excel et enregistre au format macro (FileFormat 52).
Usage : python tools/build_template.py [config.json] [dossier_sortie]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from gtc_compta import EXPORT_FORMAT_VERSION  # noqa: E402
from gtc_compta.config import load_config  # noqa: E402

ENTETES = {
    "FACTURES": "ct_num|client_libelle|nature|reference_piece|bc_origine|type_document|montant|sens|mode_reference|acheteur_detail|feuille|ligne|notes",
    "REGLEMENTS": "ct_num|client_libelle|nature|reference_piece|bc_origine|type_document|montant|sens|mode_reference|acheteur_detail|feuille|ligne|notes",
    "ANOMALIES": "feuille|ligne|section|gravite|motif|contenu|proposition|statut",
    "EXPORT_ERP": "format_version|id_import|agence|date_rapport|type_mouvement|reference_piece|code_tiers|nom_client|acheteur_detail|montant|sens|bc_origine|mode_reference|source_feuille|source_ligne|empreinte_ligne",
}


def build(cfg, dest: Path) -> Path:
    r = cfg["rapport"]
    wb = Workbook()
    ws = wb.active
    ws.title = "PARAMETRES"
    rows = [("AGENCE", cfg["agence"]), ("DATE DU RAPPORT", None), ("PERIODE", None), ("UTILISATEUR", None),
            ("VERSION DU FORMAT", EXPORT_FORMAT_VERSION), (None, None),
            ("REGLES (identiques a config.json - a modifier des deux cotes)", None),
            ("ENTETE_RECUS", r["entete_recus"]), ("COLONNES_FACTURE", ",".join(r["colonnes_facture"])),
            ("COLONNES_BC", ",".join(r["colonnes_bc"])), ("COLONNE_MONTANT_RECU", r["colonne_montant_recu"]),
            ("LIGNES_VIDES_FIN_SECTION", r["lignes_vides_fin_section"])]
    for k, v in rows:
        ws.append([k, v])
    for pref, t in r["types_documents"].items():
        ws.append(["TYPE_DOCUMENT", pref, t["nature"], t["sens"], "confirme" if t.get("confirme") else "A CONFIRMER"])
    fc = r.get("factures_comptant", {})
    if fc.get("mode") == "solder_par_acompte":
        for c in fc.get("colonnes", []):
            ws.append(["COLONNE_FACTURE_COMPTANT", c, "acompte impute sur la facture",
                       "confirme" if fc.get("confirme") else "A CONFIRMER"])
    for pb in r.get("prefixes_bons", []):
        ws.append(["PREFIXE_BON", pb])
    for va in r.get("valeurs_annulee", []):
        ws.append(["VALEUR_ANNULEE", va])
    for m in r["mots_exclusion"]:
        ws.append(["EXCLUSION", m])
    for c in r["comptes_collectifs"]:
        ws.append(["COMPTE_COLLECTIF", c])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 30
    ws["B2"].number_format = "DD/MM/YYYY"
    ws["B2"].fill = PatternFill("solid", fgColor="FFF2CC")
    c = wb.create_sheet("COLLAGE")
    c["A1"] = None
    for name, h in ENTETES.items():
        s = wb.create_sheet(name)
        s.append(h.split("|"))
        for cell in s[1]:
            cell.font = Font(bold=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "vba"
    print(build(cfg, out / "GTC_PREPARATION_JOURNALIERE_modele.xlsx"))
