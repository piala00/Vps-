"""Configuration externe (JSON). Les secrets ne sont jamais stockes dans le depot.

Ordre de recherche : variable GTC_COMPTA_CONFIG, puis ./config.json, puis
%APPDATA%/GTC_Compta/config.json. Le mot de passe SQL eventuel est lu dans la
variable d'environnement designee par sage.password_env (jamais dans le fichier).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULTS: dict = {
    "societe": "GLOBAL TRADE COMPANY SARL",
    "agence": "BERTOUA",
    "data_dir": "data",
    "utilisateur": {"login": "comptable", "nom": "Comptable", "role": "comptable_controleur"},
    "sage": {
        # "demo" : adaptateur fictif clairement signale ; "sql" : SQL Server lecture seule
        "mode": "demo",
        "server": "GTC-LISTENER,1433",
        "database_compta": "",
        "database_gescom": "",
        "trusted_connection": True,
        "username": "",
        "password_env": "GTC_SAGE_PASSWORD",
        "odbc_driver": "",
        "timeout_s": 10,
        "compte_collectif_clients": "411",
        "journal_report_nouveau": "RAN",
    },
    "rapport": {
        # Regles etablies a partir du classeur reel "10 RC OCT.xlsx" (analyse du 12/11/2026).
        # "confirme": False = interpretation deduite du rapport, a confirmer par la comptabilite.
        # Regle de la comptabilite (12/11/2026) : toutes les factures (y compris retours / avoirs)
        # au DEBIT avec leur signe ; tous les recus et acomptes au CREDIT avec leur signe.
        # Colonnes : F = ACOMPTE (BC, "ENTREE"), G = BP (BC a credit), H = VENTE COMPTANT,
        # I = VENTE A TERME ("VAT") ; recus : F = RECOUVREMENTS (cf. feuille RECAP).
        "entete_recus": "RECUS DE VERSEMENTS",
        "libelle_total_ventes": "TOTAL VENTES",
        "libelle_total_recus": "TOTAL DE VERSEMENTS",
        "motif_document": r"^(?:\d+)?[A-Z]{2,5}\d*[-/ ]?\d+",
        "motif_recu": r"^(?:\d+)?RCB",
        "types_documents": {
            "FACB": {"nature": "FACTURE", "sens": "D", "confirme": True},
            "FRCB": {"nature": "AVOIR", "sens": "D", "confirme": True},
            "FVCB": {"nature": "AVOIR", "sens": "D", "confirme": True}
        },
        "prefixes_bons": ["BCCB", "BLCB"],
        "valeurs_annulee": ["ANNULEE", "ANNULE"],
        "colonnes_facture": ["H", "I"],
        "colonnes_bc": ["F", "G"],
        "acomptes": {"integrer": True, "colonne": "F", "confirme": False},
        "colonne_montant_recu": "F",
        "mots_exclusion": ["TOTAL", "SOUS-TOTAL", "S/TOTAL", "REPORT", "VERSEMENT CAISSE",
                            "VERSEMENT BANQUE", "LIAISON", "CAISSE CENTRALE", "SOLDE"],
        "comptes_collectifs": ["CLIENTS DETAILS BTA"],
        "correspondance_auto_intitule_exact": False,
        "lignes_vides_fin_section": 8
    },
    "solvabilite": {
        "politique_factures_echues": "signaler",
        "plafond_zero": "donnees_insuffisantes",
        "depassement_max_sous_condition": None
    },
    "impression": {
        "lignes_par_page": 0,
        "marge_reliure_mm": 20,
        "seuil_alerte_pages": 2
    },
    "documents": {"dossiers_pdf": [], "dossier_export": ""},
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in (extra or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def config_path() -> Path:
    env = os.environ.get("GTC_COMPTA_CONFIG")
    if env:
        return Path(env)
    local = Path.cwd() / "config.json"
    if local.exists():
        return local
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "GTC_Compta" / "config.json"
    return local


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else config_path()
    data = {}
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    if "password" in data.get("sage", {}):
        raise ValueError("Le mot de passe SQL ne doit pas figurer dans config.json : "
                         "utilisez la variable d'environnement sage.password_env.")
    cfg = _deep_merge(DEFAULTS, data)
    cfg["_path"] = str(p)
    return cfg


def save_config(cfg: dict, path: str | os.PathLike | None = None) -> Path:
    p = Path(path or cfg.get("_path") or config_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return p
