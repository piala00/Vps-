#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/sage_connector.py
NEXORA v2.0 — Connexion Sage 100 v9 SQL Server — LECTURE SEULE

Regles non negociables :
  - Jamais d'INSERT/UPDATE/DELETE sur Sage
  - DO_Type=6  = Facture vente (sortie stock)
  - DE_No=7    = Depot Bertoua
  - DO_MajCpta=0 = document non encore comptabilise
  - DL_MvtStock IN (1,3) = ligne ayant mouvemente le stock
  - Si pyodbc indisponible ou erreur -> retourner des donnees vides, ne jamais planter
"""
import logging
from typing import Optional, Tuple, List, Dict

log = logging.getLogger("NEXORA.Sage")

try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]


def get_config():
    from core.database import get_config as gc
    return {
        "server":   gc("sage_server", ""),
        "database": gc("sage_database", ""),
        "trusted":  gc("sage_trusted", "1") == "1",
        "login":    gc("sage_login", "sa"),
        "password": gc("sage_password", ""),
    }


def get_driver() -> Optional[str]:
    if not HAS_PYODBC:
        return None
    try:
        installed = pyodbc.drivers()
    except Exception:
        return None
    for d in DRIVERS:
        if d in installed:
            return d
    return None


def get_connection(database: str = None):
    if not HAS_PYODBC:
        raise ConnectionError("pyodbc non installe")
    cfg = get_config()
    if not cfg["server"] or not cfg["database"]:
        raise ConnectionError("Connexion Sage non configuree")
    driver = get_driver()
    if not driver:
        raise ConnectionError("Aucun driver ODBC SQL Server trouve")
    db = database or cfg["database"]
    if cfg["trusted"]:
        cs = ("DRIVER={%s};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;"
              "TrustServerCertificate=yes;") % (driver, cfg["server"], db)
    else:
        cs = ("DRIVER={%s};SERVER=%s;DATABASE=%s;UID=%s;PWD=%s;"
              "TrustServerCertificate=yes;") % (driver, cfg["server"], db, cfg["login"], cfg["password"])
    return pyodbc.connect(cs, timeout=10)


def test_connexion() -> Tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True, "Connexion Sage SQL Server OK"
    except Exception as e:
        return False, str(e)


def sage_query(sql: str, params: tuple = ()) -> List[Dict]:
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_drivers_list() -> List[str]:
    if not HAS_PYODBC:
        return []
    try:
        return list(pyodbc.drivers())
    except Exception:
        return []


# ── Types documents Sage 100 ──────────────────────────────────────────────────
DO_TYPES = {
    0: "Devis",
    1: "Bon de Commande",
    2: "Preparation Livraison",
    3: "Bon de Livraison",
    4: "Bon de Retour Client",
    5: "Bon d'Avoir",
    6: "Facture",
    7: "Facture Avoir",
    11: "Devis Fournisseur",
    12: "Commande Fournisseur",
    13: "Preparation Reception",
    14: "Bon de Reception",
    15: "Retour Fournisseur",
    16: "Avoir Fournisseur",
    17: "Facture Fournisseur",
    18: "Avoir Facture Fourn.",
    19: "Entree de Stock",
    20: "Sortie de Stock",
    21: "Transfert Inter-depot",
}

# ── Reconstitution BL ─────────────────────────────────────────────────────────
SQL_BL_DEPUIS_FACTURE = """
    SELECT
        DL.DL_PieceBL                    AS no_bl,
        DH.DO_Piece                      AS no_facture,
        CONVERT(DATE, DL.DL_DateBL)      AS date_bl,
        DH.DO_Tiers                      AS code_client,
        ISNULL(CT.CT_Intitule,'')        AS client_nom,
        DL.AR_Ref                        AS code_article,
        DL.DL_Design                     AS designation,
        DL.DL_QteBL                      AS quantite,
        DL.DL_PrixUnitaire               AS prix_unitaire,
        DL.DL_MontantHT                  AS montant_ht,
        ISNULL(DEP.DE_Intitule,'')       AS depot,
        DL.DE_No                         AS depot_no
    FROM F_DOCLIGNE DL
    INNER JOIN F_DOCENTETE DH ON DH.DO_Piece=DL.DO_Piece AND DH.DO_Type=DL.DO_Type
    LEFT JOIN F_COMPTET CT  ON CT.CT_Num=DH.DO_Tiers
    LEFT JOIN F_DEPOT DEP   ON DEP.DE_No=DL.DE_No
    WHERE DH.DO_Type=6
        AND DL.DL_PieceBL=?
        AND DL.DL_QteBL > 0
        AND DL.AR_Ref IS NOT NULL AND DL.AR_Ref <> ''
    ORDER BY DL.AR_Ref
"""

SQL_BL_DIRECT = """
    SELECT
        BL.DO_Piece                      AS no_bl,
        BL.DO_PieceOrig                  AS no_facture,
        CONVERT(DATE, BL.DO_Date)        AS date_bl,
        BL.DO_Tiers                      AS code_client,
        ISNULL(CT.CT_Intitule,'')        AS client_nom,
        DL.AR_Ref                        AS code_article,
        DL.DL_Design                     AS designation,
        DL.DL_Qte                        AS quantite,
        DL.DL_PrixUnitaire               AS prix_unitaire,
        DL.DL_MontantHT                  AS montant_ht,
        ISNULL(DEP.DE_Intitule,'')       AS depot,
        DL.DE_No                         AS depot_no
    FROM F_DOCENTETE BL
    INNER JOIN F_DOCLIGNE DL ON DL.DO_Piece=BL.DO_Piece AND DL.DO_Type=BL.DO_Type
    LEFT JOIN F_COMPTET CT  ON CT.CT_Num=BL.DO_Tiers
    LEFT JOIN F_DEPOT DEP   ON DEP.DE_No=DL.DE_No
    WHERE BL.DO_Type=3 AND BL.DO_Piece=?
        AND DL.DL_Qte > 0
        AND DL.AR_Ref IS NOT NULL AND DL.AR_Ref <> ''
    ORDER BY DL.AR_Ref
"""


def reconstituer_bl(no_bl: str) -> Tuple[bool, str, List[Dict]]:
    no_bl = no_bl.strip().upper()
    try:
        rows = sage_query(SQL_BL_DEPUIS_FACTURE, (no_bl,))
        source = "facture"
        if not rows:
            rows = sage_query(SQL_BL_DIRECT, (no_bl,))
            source = "bl_direct"
        if not rows:
            return False, "BL '%s' introuvable dans Sage" % no_bl, []

        from core.database import db_exec
        for r in rows:
            db_exec("""INSERT OR REPLACE INTO cache_bl
                (no_bl,no_facture,code_article,designation,quantite,date_bl,depot,
                 code_client,client_nom)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (str(r.get("no_bl") or no_bl),
                 str(r.get("no_facture") or ""),
                 str(r.get("code_article") or ""),
                 str(r.get("designation") or ""),
                 float(r.get("quantite") or 0),
                 str(r.get("date_bl") or ""),
                 str(r.get("depot") or ""),
                 str(r.get("code_client") or ""),
                 str(r.get("client_nom") or "")))
        return True, "BL %s charge (%d articles) - %s" % (no_bl, len(rows), source), rows
    except Exception as e:
        log.error("Erreur BL %s: %s" % (no_bl, e))
        return False, str(e), []


# ── Mouvements stock ──────────────────────────────────────────────────────────
SQL_MOUVEMENTS = """
    SELECT
        L.cbMarq                            AS id_ligne,
        CONVERT(DATE, L.DO_Date)            AS date_mvt,
        D.DE_Intitule                       AS depot,
        D.DE_No                             AS depot_no,
        L.DL_PieceBC                        AS no_bc,
        L.DL_PieceBL                        AS no_bl,
        L.DO_Piece                          AS no_piece,
        L.AR_Ref                            AS code_article,
        L.DL_Design                         AS designation,
        ISNULL(AR.FA_CodeFamille,'')        AS famille,
        L.CT_Num                            AS code_client,
        ISNULL(T.CT_Intitule,'')            AS client_nom,
        L.DL_MvtStock                       AS dl_mvtstock,
        CASE WHEN L.DL_MvtStock=1 THEN ABS(L.DL_Qte) ELSE 0 END AS entree,
        CASE WHEN L.DL_MvtStock=3 THEN ABS(L.DL_Qte) ELSE 0 END AS sortie,
        ABS(L.DL_Qte)                       AS quantite,
        L.DL_MontantHT                      AS montant_ht,
        CASE
            WHEN L.DO_Piece LIKE 'FACB%' THEN 'VENTE'
            WHEN L.DO_Piece LIKE 'FAFB%' THEN 'RECEPTION_FOURN'
            WHEN L.DO_Piece LIKE 'BLCB%' THEN 'LIVRAISON_CLIENT'
            WHEN L.DO_Piece LIKE 'MESB%' THEN 'STOCK_INITIAL'
            WHEN L.DO_Piece LIKE 'MSSB%' THEN 'REGULARISATION'
            WHEN L.DO_Piece LIKE 'FRCB%' THEN 'RETOUR_CLIENT'
            WHEN L.DO_Piece LIKE 'MTSB%' THEN 'TRANSFERT'
            ELSE 'AUTRE'
        END AS type_mouvement
    FROM F_DOCLIGNE L
    LEFT JOIN F_DEPOT D    ON D.DE_No   = L.DE_No
    LEFT JOIN F_COMPTET T  ON T.CT_Num  = L.CT_Num
    LEFT JOIN F_ARTICLE AR ON AR.AR_Ref = L.AR_Ref
    WHERE L.AR_Ref IS NOT NULL AND L.AR_Ref <> ''
        AND L.DL_MvtStock IN (1, 3)
        AND {filtre}
    ORDER BY L.DO_Date DESC, L.cbMarq
"""

FILTRES_PERIODE = {
    "jour":      "CONVERT(DATE,L.DO_Date)=CONVERT(DATE,GETDATE())",
    "semaine":   "L.DO_Date >= DATEADD(DAY,-7,GETDATE())",
    "mois":      "L.DO_Date >= DATEADD(MONTH,-1,GETDATE())",
    "trimestre": "L.DO_Date >= DATEADD(MONTH,-3,GETDATE())",
    "semestre":  "L.DO_Date >= DATEADD(MONTH,-6,GETDATE())",
    "annee":     "L.DO_Date >= DATEADD(YEAR,-1,GETDATE())",
    "3mois":     "L.DO_Date >= DATEADD(MONTH,-3,GETDATE())",
    "6mois":     "L.DO_Date >= DATEADD(MONTH,-6,GETDATE())",
    "12mois":    "L.DO_Date >= DATEADD(MONTH,-12,GETDATE())",
    "24mois":    "L.DO_Date >= DATEADD(MONTH,-24,GETDATE())",
}


def get_mouvements(periode: str = "3mois") -> List[Dict]:
    try:
        filtre = FILTRES_PERIODE.get(periode, FILTRES_PERIODE["3mois"])
        return sage_query(SQL_MOUVEMENTS.format(filtre=filtre))
    except Exception as e:
        log.error("Erreur mouvements: %s" % e)
        return []


# ── Stock disponible (F_ARTSTOCK) ─────────────────────────────────────────────
def get_stock_disponible(depot_no: int = None) -> List[Dict]:
    try:
        sql = """
            SELECT A.AR_Ref AS code_article, A.AR_Design AS designation,
                   A.FA_CodeFamille AS famille, D.DE_Intitule AS depot,
                   S.DE_No AS depot_no, S.AS_QteSto AS stock_actuel,
                   S.AS_QteMini AS stock_mini, S.AS_QteMaxi AS stock_maxi,
                   S.AS_MontSto AS valeur_stock
            FROM F_ARTSTOCK S
            INNER JOIN F_ARTICLE A ON A.AR_Ref=S.AR_Ref
            INNER JOIN F_DEPOT D   ON D.DE_No=S.DE_No
            WHERE A.AR_Sommeil=0 AND A.AR_SuiviStock=1
        """
        params = ()
        if depot_no:
            sql += " AND S.DE_No=?"
            params = (depot_no,)
        sql += " ORDER BY D.DE_Intitule, A.AR_Design"
        return sage_query(sql, params)
    except Exception as e:
        log.error("Erreur stock: %s" % e)
        return []


# Alias retro-compatible
get_stock_actuel = get_stock_disponible


# ── Recherche articles (F_ARTICLE) ────────────────────────────────────────────
def get_articles(q: str = "", limit: int = 50) -> List[Dict]:
    try:
        sql = """
            SELECT TOP (?) AR_Ref AS code_article, AR_Design AS designation,
                   FA_CodeFamille AS famille, AR_PrixVen1 AS prix_vente
            FROM F_ARTICLE
            WHERE AR_Sommeil=0
        """
        params = [limit]
        if q:
            sql += " AND (AR_Ref LIKE ? OR AR_Design LIKE ?)"
            like = "%" + q.strip() + "%"
            params += [like, like]
        sql += " ORDER BY AR_Design"
        return sage_query(sql, tuple(params))
    except Exception as e:
        log.error("Erreur articles: %s" % e)
        return []


# ── Alertes stock ─────────────────────────────────────────────────────────────
def get_alertes_stock() -> List[Dict]:
    try:
        return sage_query("""
            SELECT A.AR_Ref AS code_article, A.AR_Design AS designation,
                   A.FA_CodeFamille AS famille, D.DE_Intitule AS depot,
                   S.AS_QteSto AS stock_actuel,
                   S.AS_QteMini AS stock_mini, S.AS_QteMaxi AS stock_maxi,
                   CASE WHEN S.AS_QteSto<=0 THEN 'RUPTURE'
                        WHEN S.AS_QteMini>0 AND S.AS_QteSto<=S.AS_QteMini THEN 'CRITIQUE'
                        WHEN S.AS_QteMaxi>0 AND S.AS_QteSto>=S.AS_QteMaxi THEN 'SURPLUS'
                   END AS alerte
            FROM F_ARTSTOCK S
            INNER JOIN F_ARTICLE A ON A.AR_Ref=S.AR_Ref
            INNER JOIN F_DEPOT D   ON D.DE_No=S.DE_No
            WHERE A.AR_Sommeil=0 AND A.AR_SuiviStock=1
                AND (S.AS_QteSto<=0
                     OR (S.AS_QteMini>0 AND S.AS_QteSto<=S.AS_QteMini)
                     OR (S.AS_QteMaxi>0 AND S.AS_QteSto>=S.AS_QteMaxi))
            ORDER BY CASE WHEN S.AS_QteSto<=0 THEN 1
                          WHEN S.AS_QteSto<=S.AS_QteMini THEN 2 ELSE 3 END
        """)
    except Exception as e:
        log.error("Erreur alertes: %s" % e)
        return []


# ── Grand livre camion ─────────────────────────────────────────────────────────
def get_grand_livre_camion(compte_sage: str, date_debut: str = "", date_fin: str = "") -> List[Dict]:
    try:
        sql = """
            SELECT E.EC_Date AS date_ecriture, E.JO_Num AS journal,
                   E.EC_Piece AS piece, E.EC_Libelle AS libelle,
                   E.EC_Montant AS montant,
                   CASE WHEN E.EC_Sens=0 THEN E.EC_Montant ELSE 0 END AS debit,
                   CASE WHEN E.EC_Sens=1 THEN E.EC_Montant ELSE 0 END AS credit
            FROM F_ECRITUREC E
            WHERE E.CG_Num=?
        """
        params = [compte_sage]
        if date_debut:
            sql += " AND E.EC_Date>=?"
            params.append(date_debut)
        if date_fin:
            sql += " AND E.EC_Date<=?"
            params.append(date_fin)
        sql += " ORDER BY E.EC_Date"
        return sage_query(sql, tuple(params))
    except Exception as e:
        log.error("Erreur GL camion: %s" % e)
        return []


# ── Creances clients ──────────────────────────────────────────────────────────
def get_creances_clients() -> List[Dict]:
    try:
        return sage_query("""
            SELECT E.CT_Num AS code_client, C.CT_Intitule AS nom,
                   C.CT_Telephone AS telephone,
                   SUM(CASE WHEN E.EC_Sens=0 THEN E.EC_Montant ELSE 0 END) AS total_debit,
                   SUM(CASE WHEN E.EC_Sens=1 THEN E.EC_Montant ELSE 0 END) AS total_credit,
                   SUM(CASE WHEN E.EC_Sens=0 THEN E.EC_Montant
                            ELSE -E.EC_Montant END) AS solde
            FROM F_ECRITUREC E
            LEFT JOIN F_COMPTET C ON C.CT_Num=E.CT_Num
            WHERE E.CT_Num IS NOT NULL AND E.CT_Num <> ''
            GROUP BY E.CT_Num, C.CT_Intitule, C.CT_Telephone
            HAVING SUM(CASE WHEN E.EC_Sens=0 THEN E.EC_Montant
                            ELSE -E.EC_Montant END) > 0.01
            ORDER BY solde DESC
        """)
    except Exception as e:
        log.error("Erreur creances: %s" % e)
        return []


# ── Grand livre client ─────────────────────────────────────────────────────────
def get_grand_livre_client(code_client: str, date_debut: str = "", date_fin: str = "") -> List[Dict]:
    try:
        sql = """
            SELECT E.EC_Date AS date_ecriture, E.JO_Num AS journal,
                   E.EC_Piece AS piece, E.EC_Libelle AS libelle,
                   E.EC_Montant AS montant,
                   CASE WHEN E.EC_Sens=0 THEN E.EC_Montant ELSE 0 END AS debit,
                   CASE WHEN E.EC_Sens=1 THEN E.EC_Montant ELSE 0 END AS credit
            FROM F_ECRITUREC E
            WHERE E.CT_Num=?
        """
        params = [code_client]
        if date_debut:
            sql += " AND E.EC_Date>=?"
            params.append(date_debut)
        if date_fin:
            sql += " AND E.EC_Date<=?"
            params.append(date_fin)
        sql += " ORDER BY E.EC_Date"
        return sage_query(sql, tuple(params))
    except Exception as e:
        log.error("Erreur GL client: %s" % e)
        return []


# ── Reglements clients (F_DOCREGL) ───────────────────────────────────────────────
def get_paiements_clients(code_client: str = "", date_debut: str = "", date_fin: str = "") -> List[Dict]:
    try:
        sql = """
            SELECT R.RG_Date AS date_paiement, R.CT_Num AS code_client,
                   ISNULL(C.CT_Intitule,'') AS client_nom,
                   R.RG_Montant AS montant, R.RG_Mode AS mode_paiement,
                   R.RG_Ref AS reference, R.DO_Piece AS piece
            FROM F_DOCREGL R
            LEFT JOIN F_COMPTET C ON C.CT_Num=R.CT_Num
            WHERE R.CT_Num IS NOT NULL AND R.CT_Num <> ''
        """
        params = []
        if code_client:
            sql += " AND R.CT_Num=?"
            params.append(code_client)
        if date_debut:
            sql += " AND R.RG_Date>=?"
            params.append(date_debut)
        if date_fin:
            sql += " AND R.RG_Date<=?"
            params.append(date_fin)
        sql += " ORDER BY R.RG_Date DESC"
        return sage_query(sql, tuple(params))
    except Exception as e:
        log.error("Erreur paiements clients: %s" % e)
        return []


# ── Ventes clients (factures, F_DOCENTETE DO_Type=6) ─────────────────────────────
def get_ventes(date_debut: str = "", date_fin: str = "", code_client: str = "") -> List[Dict]:
    try:
        sql = """
            SELECT DH.DO_Piece AS no_facture, CONVERT(DATE, DH.DO_Date) AS date_facture,
                   DH.DO_Tiers AS code_client, ISNULL(CT.CT_Intitule,'') AS client_nom,
                   DH.DO_TTC AS montant_ttc
            FROM F_DOCENTETE DH
            LEFT JOIN F_COMPTET CT ON CT.CT_Num=DH.DO_Tiers
            WHERE DH.DO_Type=6
        """
        params = []
        if code_client:
            sql += " AND DH.DO_Tiers=?"
            params.append(code_client)
        if date_debut:
            sql += " AND DH.DO_Date>=?"
            params.append(date_debut)
        if date_fin:
            sql += " AND DH.DO_Date<=?"
            params.append(date_fin)
        sql += " ORDER BY DH.DO_Date DESC"
        return sage_query(sql, tuple(params))
    except Exception as e:
        log.error("Erreur ventes: %s" % e)
        return []
