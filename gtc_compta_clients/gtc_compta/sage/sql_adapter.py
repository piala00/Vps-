"""Adaptateur Sage 100 SQL Server - LECTURE SEULE via pyodbc.

STATUT : NON VERIFIE SUR L'INSTALLATION REELLE.
Les noms de tables/champs ci-dessous (F_ECRITUREC, F_COMPTET, F_DOCENTETE, CT_Num,
EC_Sens, EC_Montant, CG_Num, JO_Num, EC_RefPiece, DO_Tiers...) sont ceux deja
utilises par le connecteur GTC ERP PILOT V3 (core/sage_connector.py du depot) ;
ils doivent etre controles sur la base reelle (voir docs/SAGE_ADAPTATEUR.md et
tools/verifier_sage.py). Chaque requete peut etre remplacee par la cle
sage.requetes.<nom> de config.json sans modifier le code.
"""
from __future__ import annotations

import os
import re
from datetime import date

from .base import (SageClient, SageEntry, SageExtractionIncomplete, SageIndisponible,
                   SagePurchaseOrder, SolvencyComponents)

REQUETES = {
    # A VERIFIER : CT_Type=0 = client ; CT_Encours = encours autorise
    "clients": "SELECT CT_Num, CT_Intitule, CT_Telephone, CT_Ville, CT_Encours "
               "FROM F_COMPTET WHERE CT_Type = 0",
    # A VERIFIER : EC_Sens 0=debit 1=credit ; ecritures de simulation/brouillard a exclure ?
    "ecritures": "SELECT EC_No, CT_Num, JO_Num, EC_Date, EC_Piece, EC_RefPiece, EC_Intitule, "
                 "EC_Sens, EC_Montant, EC_Echeance, EC_Lettre "
                 "FROM F_ECRITUREC WHERE CT_Num = ? AND CG_Num LIKE ? "
                 "AND EC_Date >= ? AND EC_Date <= ? ORDER BY EC_Date, EC_No",
    "nb_ecritures": "SELECT COUNT(*) FROM F_ECRITUREC WHERE CT_Num = ? AND CG_Num LIKE ? "
                    "AND EC_Date >= ? AND EC_Date <= ?",
    # Toutes les ecritures clients portant un numero de piece (tous comptes tiers confondus)
    "ecritures_piece": "SELECT EC_No, CT_Num, JO_Num, EC_Date, EC_Piece, EC_RefPiece, EC_Intitule, "
                       "EC_Sens, EC_Montant, EC_Echeance, EC_Lettre FROM F_ECRITUREC "
                       "WHERE CG_Num LIKE ? AND (EC_Piece = ? OR EC_RefPiece = ?) ORDER BY EC_Date, EC_No",
    # A VERIFIER : DO_Domaine=0 vente, DO_Type=1 bon de commande ; champ total TTC
    "bon_commande": "SELECT DO_Piece, DO_Tiers, DO_Date, DO_TotalTTC FROM F_DOCENTETE "
                    "WHERE DO_Domaine = 0 AND DO_Type = 1 AND (DO_Piece = ? OR DO_Piece LIKE ?)",
}

_INTERDIT = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|EXECUTE|DROP|ALTER|CREATE|TRUNCATE|"
                       r"GRANT|REVOKE|DENY|BACKUP|RESTORE|INTO|OPENROWSET|OPENQUERY|DBCC)\b", re.I)
DATE_MIN = date(1900, 1, 1)


def verifier_lecture_seule(sql: str) -> None:
    s = sql.strip().rstrip(";")
    if ";" in s:
        raise PermissionError("Requete multiple interdite")
    if not re.match(r"^\s*(SELECT|WITH)\b", s, re.I) or _INTERDIT.search(s):
        raise PermissionError("Seules les requetes SELECT sont autorisees sur Sage")


class SqlSageAdapter:
    est_demo = False

    def __init__(self, cfg_sage: dict):
        self.cfg = cfg_sage
        self.nom = f"Sage SQL {cfg_sage.get('server')}/{cfg_sage.get('database_compta')}"
        self.requetes = {**REQUETES, **cfg_sage.get("requetes", {})}
        for q in self.requetes.values():
            verifier_lecture_seule(q)
        self.compte = cfg_sage.get("compte_collectif_clients", "411") + "%"

    # -- connexion ----------------------------------------------------------------
    def _connect(self, base_key="database_compta"):
        try:
            import pyodbc
        except ImportError as exc:
            raise SageIndisponible("Module pyodbc non installe") from exc
        c = self.cfg
        driver = c.get("odbc_driver") or next(
            (d for d in reversed(pyodbc.drivers()) if "SQL Server" in d), None)
        if not driver:
            raise SageIndisponible("Aucun pilote ODBC SQL Server installe")
        if not c.get(base_key):
            raise SageIndisponible(f"Base non configuree ({base_key})")
        parts = [f"DRIVER={{{driver}}}", f"SERVER={c['server']}", f"DATABASE={c[base_key]}",
                 "ApplicationIntent=ReadOnly", "TrustServerCertificate=yes"]
        if c.get("trusted_connection", True):
            parts.append("Trusted_Connection=yes")
        else:
            pwd = os.environ.get(c.get("password_env", "GTC_SAGE_PASSWORD"), "")
            parts += [f"UID={c['username']}", f"PWD={pwd}"]
        try:
            cn = pyodbc.connect(";".join(parts), timeout=int(c.get("timeout_s", 10)),
                                autocommit=False, readonly=True)
        except TypeError:
            cn = pyodbc.connect(";".join(parts), timeout=int(c.get("timeout_s", 10)), autocommit=False)
        except Exception as exc:  # pyodbc.Error
            raise SageIndisponible(f"Connexion Sage impossible : {exc}") from exc
        return cn

    def _query(self, nom: str, params=(), base_key="database_compta"):
        sql = self.requetes[nom]
        verifier_lecture_seule(sql)
        cn = self._connect(base_key)
        try:
            cur = cn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        except SageIndisponible:
            raise
        except Exception as exc:
            raise SageExtractionIncomplete(f"Requete '{nom}' en echec : {exc}") from exc
        finally:
            try:
                cn.rollback()
            finally:
                cn.close()

    # -- interface ----------------------------------------------------------------
    def ping(self):
        cn = self._connect()
        cn.close()

    def lister_clients(self):
        return [SageClient(ct_num=str(r[0]).strip(), intitule=str(r[1] or "").strip(),
                           telephone=str(r[2] or "").strip(), ville=str(r[3] or "").strip(),
                           encours_autorise=int(r[4]) if r[4] is not None else None)
                for r in self._query("clients")]

    def ecritures_client(self, ct_num, date_debut, date_fin):
        p = (ct_num, self.compte, date_debut or DATE_MIN, date_fin)
        rows = self._query("ecritures", p)
        attendu = self._query("nb_ecritures", p)[0][0]
        if attendu != len(rows):
            raise SageExtractionIncomplete(f"{len(rows)} ecritures lues sur {attendu} attendues")
        return [self._entree(r) for r in rows]

    @staticmethod
    def _entree(r) -> SageEntry:
        return SageEntry(ec_no=int(r[0]), ct_num=str(r[1]).strip(), journal=str(r[2] or ""),
                         date_ecriture=r[3].date() if hasattr(r[3], "date") else r[3],
                         numero_piece=str(r[4] or "").strip(), reference_piece=str(r[5] or "").strip(),
                         libelle=str(r[6] or "").strip(), sens="D" if int(r[7]) == 0 else "C",
                         montant=round(float(r[8])),
                         date_echeance=r[9].date() if r[9] is not None and hasattr(r[9], "date") else None,
                         lettre=bool(r[10] and int(r[10])))

    def ecritures_par_piece(self, piece):
        p = piece.strip()
        return [self._entree(r) for r in self._query("ecritures_piece", (self.compte, p, p))]

    def solde_client(self, ct_num, date_arrete):
        return sum(e.signe for e in self.ecritures_client(ct_num, None, date_arrete))

    def soldes_a_date(self, date_ref):
        return {c.ct_num: self.solde_client(c.ct_num, date_ref) for c in self.lister_clients()}

    def chercher_bon_commande(self, reference):
        ref = reference.strip().upper()
        rows = self._query("bon_commande", (ref, "%" + ref), base_key="database_gescom")
        return [SagePurchaseOrder(piece=str(r[0]).strip(), ct_num=str(r[1]).strip(),
                                  date_doc=r[2].date() if hasattr(r[2], "date") else r[2],
                                  montant_ttc=round(float(r[3] or 0))) for r in rows]

    def composantes_solvabilite(self, bc):
        # La formule de la fenetre Sage "Solvabilite" n'est pas encore etablie :
        # on ne renvoie volontairement aucun risque -> avis DONNEES_INSUFFISANTES.
        return SolvencyComponents(plafond=None, risque_sage=None, bc_deja_inclus=None,
                                  details={"motif": "Formule de solvabilite Sage non encore "
                                                    "reproduite ni verifiee (voir docs)."})

    def chemin_pdf_facture(self, piece):
        return None  # liaison Sage <-> PDF non inventoriee
