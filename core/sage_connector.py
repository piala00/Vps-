"""
NEXORA v2.0 — Connecteur Sage SQL Server
Architecture robuste inspirée de GTC ERP PILOT V3
- Essai de tous les drivers ODBC disponibles dans l'ordre
- Fallback TCP (port 1433/1434) si instance nommée échoue
- Test des encodages : cp1252 > latin-1 > utf-8 > utf-16
- Cache JSON local (24h) pour les DONNEES
- Cache memoire de la DERNIERE CONNEXION REUSSIE (driver/serveur/encodage)
  pour eviter de re-tester toutes les combinaisons a chaque appel API
  (sans cela, un Sage inaccessible peut bloquer chaque ecran plusieurs minutes)
- Journal de diagnostic en temps reel (visible dans Parametres > Journal Sage)
- Connexion LECTURE SEULE uniquement
"""
import os, json, logging, time
from collections import deque
from datetime import date, datetime, timedelta
from core.database import get_config

log = logging.getLogger('NEXORA.Sage')

# ── Journal de diagnostic temps reel ──────────────────────────────────────────
# Permet de voir EXACTEMENT ou bloque une connexion Sage (visible cote UI).
SAGE_LOG_QUEUE   = deque(maxlen=300)
_LAST_GOOD_CONN  = {'driver': None, 'variant': None, 'encoding': None, 'ts': None}
_LAST_FAILURE    = {'ts': None}
_FAILURE_COOLDOWN_S = 30  # apres un echec total, ne pas re-balayer avant 30s

# Timeouts realistes : un reseau local repond en < 2s normalement.
# 5s par tentative suffit largement et evite les blocages de plusieurs minutes
# quand Sage est injoignable (mauvais nom serveur, pare-feu, service arrete).
_CONNECT_TIMEOUT_S  = 5
_QUERY_TIMEOUT_S    = 30  # une requete lourde (Grand Livre) peut prendre plus de temps


def _sage_log(msg: str, level: str = 'INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    SAGE_LOG_QUEUE.append({'ts': ts, 'level': level, 'msg': msg})
    if level == 'ERROR':
        log.warning("SAGE: %s", msg)
    else:
        log.info("SAGE: %s", msg)


def get_sage_log(limit=100):
    return list(SAGE_LOG_QUEUE)[-limit:]


def clear_sage_log():
    SAGE_LOG_QUEUE.clear()


def get_last_good_connection():
    return dict(_LAST_GOOD_CONN)

# ── Cache des donnees ─────────────────────────────────────────────────────────
_CACHE_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Data', 'sage_cache.json')
_CACHE_MAX_H    = 24  # heures

os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)

def _save_cache(key, data):
    try:
        cache = {}
        if os.path.exists(_CACHE_FILE):
            try:
                with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
            except Exception:
                cache = {}
        cache[key] = {'ts': datetime.now().isoformat(), 'data': data}
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, default=str)
    except Exception as e:
        log.warning("Erreur sauvegarde cache: %s", e)

def _load_cache(key):
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        for enc in ('utf-8', 'cp1252', 'latin-1'):
            try:
                with open(_CACHE_FILE, 'r', encoding=enc) as f:
                    cache = json.load(f)
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        else:
            return None
        entry = cache.get(key)
        if not entry:
            return None
        ts    = datetime.fromisoformat(entry['ts'])
        age_h = (datetime.now() - ts).total_seconds() / 3600
        if age_h > _CACHE_MAX_H:
            log.info("Cache %s périmé (%.1fh)", key, age_h)
            return None
        log.info("Cache %s chargé (%.1fh)", key, age_h)
        return entry['data']
    except Exception as e:
        log.warning("Erreur lecture cache: %s", e)
        return None

def clear_cache():
    try:
        if os.path.exists(_CACHE_FILE):
            os.remove(_CACHE_FILE)
    except Exception:
        pass

# ── Drivers ODBC ─────────────────────────────────────────────────────────────

def _get_sql_drivers():
    """Retourne les drivers ODBC disponibles, ODBC Driver 17+ en priorité."""
    try:
        import pyodbc
        all_drv = pyodbc.drivers()
        odbc    = sorted([d for d in all_drv if 'ODBC Driver' in d and 'SQL' in d], reverse=True)
        legacy  = [d for d in all_drv if d == 'SQL Server']
        return odbc + legacy or ['SQL Server']
    except ImportError:
        return ['SQL Server']

def _build_cs(drv, server, database, trusted, username, password, timeout=5):
    """Construit la chaîne de connexion pyodbc avec timeout court (echec rapide)."""
    auth = 'Trusted_Connection=yes;' if trusted else f'UID={username};PWD={password};'
    return (
        f'DRIVER={{{drv}}};SERVER={server};DATABASE={database};'
        f'{auth}TrustServerCertificate=yes;'
        f'ApplicationIntent=ReadOnly;Connect Timeout={timeout};'
    )

# ── Connexion principale ──────────────────────────────────────────────────────

def get_connection():
    """
    Connexion robuste à Sage SQL Server.
    Essaie tous les drivers + variantes serveur + encodages.
    Retourne une connexion pyodbc ou None si impossible.
    Timeouts courts (5s) pour echouer vite plutot que bloquer.
    """
    try:
        import pyodbc
    except ImportError:
        log.warning("pyodbc non installé (pip install pyodbc)")
        return None

    server   = get_config('sage_server', '')
    database = get_config('sage_database', '')
    trusted  = get_config('sage_trusted', '1') == '1'
    username = get_config('sage_user', 'sa')
    password = get_config('sage_password', '')

    if not server or not database:
        log.warning("Sage non configuré (serveur ou base manquant)")
        return None

    drivers = _get_sql_drivers()
    if not drivers:
        log.error("Aucun driver ODBC SQL Server trouvé")
        return None

    # Variantes serveur : instance nommée + fallback TCP
    variants = [server]
    if '\\' in server:
        host = server.split('\\')[0]
        variants += [f'{host},1433', f'{host},1434', f'tcp:{server}']

    for drv in drivers:
        for srv in variants:
            cs = _build_cs(drv, srv, database, trusted, username, password, timeout=_CONNECT_TIMEOUT_S)
            try:
                cx = pyodbc.connect(cs, timeout=_CONNECT_TIMEOUT_S)
                log.info("Connexion Sage OK: %s / %s", drv, srv)
                cx.close()
                # Retourner une connexion fonctionnelle (timeout requete plus long)
                cx2 = pyodbc.connect(cs, timeout=_CONNECT_TIMEOUT_S)
                cx2.timeout = _QUERY_TIMEOUT_S
                return cx2
            except Exception as e:
                log.debug("Échec %s / %s : %s", drv, srv, str(e)[:80])
                continue

    log.error("Impossible de se connecter à Sage SQL Server")
    return None

def test_connection(server='', database='', trusted=True, username='', password=''):
    """
    Test de connexion SQL Server avec diagnostic.
    Retourne (succes:bool, message:str)
    """
    try:
        import pyodbc
    except ImportError:
        return False, "pyodbc non installé. Lancez : pip install pyodbc"

    drivers = _get_sql_drivers()
    if not drivers:
        return False, "Aucun driver ODBC SQL Server sur ce poste.\nInstallez 'ODBC Driver 17 for SQL Server' (Microsoft)."

    variants = [server or get_config('sage_server', '')]
    if '\\' in variants[0]:
        host = variants[0].split('\\')[0]
        variants += [f'{host},1433', f'tcp:{variants[0]}']

    errors = []
    _sage_log(f"Test connexion: {len(drivers[:3])} driver(s) x {len(variants)} variante(s)")
    for drv in drivers[:3]:
        for srv in variants:
            cs = _build_cs(drv, srv,
                           database or get_config('sage_database', ''),
                           trusted,
                           username or get_config('sage_user', 'sa'),
                           password or get_config('sage_password', ''),
                           timeout=_CONNECT_TIMEOUT_S)
            try:
                cx  = pyodbc.connect(cs, timeout=_CONNECT_TIMEOUT_S)
                cur = cx.cursor()
                cur.execute("SELECT DB_NAME()")
                dbname = cur.fetchone()[0]
                cx.close()
                _sage_log(f"Test OK: {drv}/{srv} -> base {dbname}")
                return True, (
                    f"Connexion réussie ✓\n"
                    f"Driver  : {drv}\n"
                    f"Serveur : {srv}\n"
                    f"Base    : {dbname}"
                )
            except Exception as e:
                _sage_log(f"Test echec {drv}/{srv}: {str(e)[:100]}", 'ERROR')
                errors.append(f"[{drv} / {srv}] {str(e)[:120]}")

    msg = "Connexion impossible.\n\nEssais :\n" + "\n".join(errors[:6])
    msg += (
        "\n\nConseils :\n"
        "• Vérifier que SQL Server Browser est démarré\n"
        "• Vérifier que TCP/IP est activé (SQL Server Config Manager)\n"
        "• Essayer SQL Server Management Studio d'abord\n"
        f"• Essayer le nom du serveur sans l'instance : {(server or '').split(chr(92))[0]}"
    )
    return False, msg

# ── Exécution de requêtes ─────────────────────────────────────────────────────

def sage_query(sql, params=(), use_cache=False, cache_key=None):
    """
    Exécute une requête SELECT sur Sage.
    Strategie rapide :
    1. Si une connexion a deja fonctionne recemment, la retente directement
       (evite de re-tester tous les drivers/variantes/encodages a chaque appel).
    2. Sinon, balaye drivers x variantes x encodages avec un timeout COURT
       (5s) pour echouer vite plutot que de bloquer plusieurs minutes.
    Chaque etape est journalisee (visible dans Parametres > Journal Sage).
    """
    if use_cache and cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached

    try:
        import pyodbc
    except ImportError:
        _sage_log("pyodbc non installe — pip install pyodbc", 'ERROR')
        return []

    server   = get_config('sage_server', '')
    database = get_config('sage_database', '')
    trusted  = get_config('sage_trusted', '1') == '1'
    username = get_config('sage_user', 'sa')
    password = get_config('sage_password', '')

    if not server or not database:
        _sage_log("Connexion Sage non configuree (serveur ou base vide)", 'ERROR')
        return []

    # Cooldown : si le dernier balayage complet a echoue il y a moins de 30s,
    # ne pas re-tenter immediatement (evite de bloquer chaque clic plusieurs
    # minutes quand Sage est completement inaccessible).
    if _LAST_FAILURE['ts'] and not _LAST_GOOD_CONN['driver']:
        elapsed = time.time() - _LAST_FAILURE['ts']
        if elapsed < _FAILURE_COOLDOWN_S:
            _sage_log(f"Sage indisponible (echec il y a {elapsed:.0f}s) — "
                      f"nouvel essai dans {_FAILURE_COOLDOWN_S-elapsed:.0f}s", 'ERROR')
            return []

    t0 = time.time()

    # ── Etape 1 : retenter la derniere connexion qui a fonctionne ──
    if _LAST_GOOD_CONN['driver']:
        drv, srv, enc = _LAST_GOOD_CONN['driver'], _LAST_GOOD_CONN['variant'], _LAST_GOOD_CONN['encoding']
        try:
            cs = _build_cs(drv, srv, database, trusted, username, password, timeout=_CONNECT_TIMEOUT_S)
            cx = pyodbc.connect(cs, timeout=_CONNECT_TIMEOUT_S)
            cx.setdecoding(pyodbc.SQL_CHAR,  encoding=enc)
            cx.setdecoding(pyodbc.SQL_WCHAR, encoding=enc)
            try: cx.setencoding(encoding=enc)
            except Exception: pass
            cx.timeout = _QUERY_TIMEOUT_S
            cur = cx.cursor()
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            cx.close()
            result = [dict(zip(cols, row)) for row in rows]
            if use_cache and cache_key:
                _save_cache(cache_key, result)
            _sage_log(f"OK (connexion reutilisee {drv}/{srv}) — {len(result)} lignes en {time.time()-t0:.1f}s")
            return result
        except Exception as e:
            err_str = str(e)
            if '42S22' in err_str or '42S02' in err_str:
                # Erreur de SCHEMA (colonne ou table invalide) : la connexion
                # fonctionne, c'est la requete SQL elle-meme qui est fausse.
                # Changer de driver/serveur/encodage ne resoudra jamais ce
                # type d'erreur — echouer immediatement evite de perdre
                # ~20s a rebalayer pour rien a chaque appel.
                _sage_log(f"Erreur de schema SQL (colonne/table invalide), pas de nouveau balayage: {err_str[:150]}", 'ERROR')
                return []
            _sage_log(f"Connexion reutilisee echouee ({drv}/{srv}): {err_str[:100]} — nouveau balayage", 'ERROR')
            _LAST_GOOD_CONN.update({'driver': None, 'variant': None, 'encoding': None})

    # ── Etape 2 : balayage complet avec timeouts courts ──
    drivers  = _get_sql_drivers()
    variants = [server]
    if '\\' in server:
        host = server.split('\\')[0]
        variants += [f'{host},1433', f'tcp:{server}']

    _sage_log(f"Balayage: {len(drivers)} driver(s) x {len(variants)} variante(s) de '{server}'")

    for drv in drivers:
        for srv in variants:
            cs = _build_cs(drv, srv, database, trusted, username, password, timeout=_CONNECT_TIMEOUT_S)
            for enc in ('cp1252', 'latin-1', 'utf-8', 'utf-16'):
                try:
                    cx  = pyodbc.connect(cs, timeout=_CONNECT_TIMEOUT_S)
                    cx.setdecoding(pyodbc.SQL_CHAR,  encoding=enc)
                    cx.setdecoding(pyodbc.SQL_WCHAR, encoding=enc)
                    try:
                        cx.setencoding(encoding=enc)
                    except Exception:
                        pass
                    cx.timeout = _QUERY_TIMEOUT_S
                    cur  = cx.cursor()
                    cur.execute(sql, params)
                    cols = [c[0] for c in cur.description]
                    rows = cur.fetchall()
                    cx.close()
                    result = [dict(zip(cols, row)) for row in rows]
                    if use_cache and cache_key:
                        _save_cache(cache_key, result)
                    _LAST_GOOD_CONN.update({'driver': drv, 'variant': srv, 'encoding': enc,
                                            'ts': datetime.now().isoformat()})
                    _LAST_FAILURE['ts'] = None
                    _sage_log(f"OK: {drv}/{srv} (enc={enc}) — {len(result)} lignes en {time.time()-t0:.1f}s")
                    return result
                except UnicodeDecodeError:
                    try: cx.close()
                    except Exception: pass
                    continue
                except Exception as e:
                    try: cx.close()
                    except Exception: pass
                    err_str = str(e)
                    if '42S22' in err_str or '42S02' in err_str:
                        # Erreur de schema : la connexion fonctionne (ce
                        # driver/serveur est valide), c'est la requete qui
                        # reference une colonne/table inexistante. Continuer
                        # a tester d'autres encodages/drivers ne changera
                        # jamais le resultat — abandonner tout le balayage.
                        _sage_log(f"Erreur de schema SQL (colonne/table invalide) avec {drv}/{srv} — "
                                  f"abandon du balayage: {err_str[:150]}", 'ERROR')
                        return []
                    _sage_log(f"Echec {drv}/{srv} (enc={enc}): {err_str[:100]}", 'ERROR')
                    break
    _LAST_FAILURE['ts'] = time.time()
    _sage_log(f"ECHEC TOTAL apres {time.time()-t0:.1f}s — Sage non disponible pour cette requete "
              f"(prochain essai dans {_FAILURE_COOLDOWN_S}s)", 'ERROR')
    return []

def sage_one(sql, params=()):
    rows = sage_query(sql, params)
    return rows[0] if rows else None

# ── Requête principale Grand Livre / Créances ─────────────────────────────────
# Requête CTE avancée extraite de GTC_ERP_PILOT V3
# Gère : déduplication, journal RAN, solde cumulé, représentants
SQL_GRAND_LIVRE = """
WITH Doc_Unique AS (
    SELECT * FROM (
        SELECT D.*, ROW_NUMBER() OVER (
            PARTITION BY D.DO_Piece, D.DO_Tiers, D.DO_Domaine
            ORDER BY D.DO_Date DESC, D.DO_Type DESC, D.cbMarq DESC) RN
        FROM F_DOCENTETE D WHERE D.DO_Domaine=0) X WHERE RN=1),
Rep_Ligne_Unique AS (
    SELECT * FROM (
        SELECT L.DO_Domaine, L.DO_Type, L.DO_Piece, L.CT_Num, L.CO_No,
            ROW_NUMBER() OVER (
                PARTITION BY L.DO_Domaine, L.DO_Type, L.DO_Piece
                ORDER BY CASE WHEN ISNULL(L.CO_No,0)<>0 THEN 0 ELSE 1 END,
                         L.DL_Ligne, L.cbMarq) RN
        FROM F_DOCLIGNE L) X WHERE RN=1),
Base AS (
    SELECT E.CT_Num Code_Client, T.CT_Intitule Nom_Client,
        E.EC_Date Date, E.JO_Num Journal, E.EC_Reference Reference,
        E.EC_RefPiece N_Facture, E.EC_Intitule Libelle,
        CASE WHEN E.EC_Sens=0 THEN E.EC_Montant ELSE 0 END Debit,
        CASE WHEN E.EC_Sens=1 THEN E.EC_Montant ELSE 0 END Credit,
        CASE WHEN E.EC_Sens=0 THEN E.EC_Montant ELSE -E.EC_Montant END Mouvement,
        E.EC_No,
        CASE WHEN E.JO_Num='RAN' THEN 0 ELSE 1 END Ordre_RAN,
        ISNULL(CLigne.CO_Nom,'') Representant
    FROM F_ECRITUREC E
    LEFT JOIN F_COMPTET T ON E.CT_Num=T.CT_Num
    LEFT JOIN Doc_Unique D
        ON D.DO_Piece=E.EC_RefPiece AND D.DO_Tiers=E.CT_Num AND D.DO_Domaine=0
    LEFT JOIN Rep_Ligne_Unique RL
        ON RL.DO_Domaine=D.DO_Domaine AND RL.DO_Type=D.DO_Type AND RL.DO_Piece=D.DO_Piece
    LEFT JOIN F_COLLABORATEUR CLigne ON RL.CO_No=CLigne.CO_No
    WHERE E.EC_Date>='20251231' AND E.CG_Num LIKE '411%'
      AND E.CT_Num IS NOT NULL
      AND (E.EC_Date>='20260101' OR E.JO_Num='RAN')),
Cumul AS (
    SELECT *,
        SUM(Mouvement) OVER (
            PARTITION BY Code_Client
            ORDER BY Ordre_RAN, Date, EC_No
            ROWS UNBOUNDED PRECEDING) Solde_Cumule
    FROM Base)
SELECT Code_Client, Nom_Client,
    CAST(Date AS date) Date, Journal,
    Reference, N_Facture, Libelle,
    Debit, Credit,
    CASE WHEN Solde_Cumule>0 THEN Solde_Cumule ELSE 0 END Solde_Debit,
    CASE WHEN Solde_Cumule<0 THEN ABS(Solde_Cumule) ELSE 0 END Solde_Credit,
    Representant
FROM Cumul
ORDER BY Code_Client, Ordre_RAN, Date, EC_No;
"""

def get_grand_livre_complet(use_cache=True):
    """
    Récupère le grand livre complet depuis Sage.
    Utilise la requête CTE avancée de GTC ERP PILOT V3.
    Cache 24h.
    """
    return sage_query(SQL_GRAND_LIVRE, use_cache=use_cache, cache_key='grand_livre')

# ── Requêtes standard ─────────────────────────────────────────────────────────

def get_stock_disponible(depot_no=7, q=''):
    """
    Stock disponible par depot.
    Note : AR_Unite n'existe pas dans le schema F_ARTICLE reel de ce client
    (confirme par l'export CSV du schema Sage) — retiree pour eviter
    l'erreur SQL 42S22 "Nom de colonne non valide" qui faisait echouer
    toute la requete et relancer un balayage complet des drivers (~21s).
    L'unite par defaut 'Unite' est fixee cote applicatif.
    """
    sql = """
        SELECT a.AR_Ref, a.AR_Design, a.FA_CodeFamille,
               COALESCE(s.AS_QteSto, 0) AS stock_physique,
               COALESCE(s.AS_QteRes, 0) AS qte_reservee,
               COALESCE(a.AR_PrixAch, 0) AS prix_achat
        FROM F_ARTICLE a
        LEFT JOIN F_ARTSTOCK s ON s.AR_Ref=a.AR_Ref AND s.DE_No=?
        WHERE a.AR_Sommeil=0
    """
    params = [depot_no]
    if q:
        sql += " AND (a.AR_Ref LIKE ? OR a.AR_Design LIKE ?)"
        params += ['%'+q+'%', '%'+q+'%']
    sql += " ORDER BY a.AR_Ref"
    rows = sage_query(sql, params)
    for r in rows:
        r['unite'] = 'Unite'
    return rows

# ── Types documents Sage 100 (mapping valide StockBridge Suite Pro) ──────────
# DO_Domaine=0 (Ventes), DO_Domaine=1 (Achats), DO_Domaine=2 (Stock interne)
DO_TYPES = {
    # VENTES (Domaine 0)
    0: "Devis", 1: "Bon de Commande", 2: "Preparation Livraison",
    3:  "Bon de Livraison",        # SORTIE STOCK
    4:  "Bon de Retour Client",    # ENTREE STOCK
    5:  "Bon d'Avoir",
    6:  "Facture",                 # SORTIE STOCK
    7:  "Facture Avoir",           # ENTREE STOCK
    # ACHATS (Domaine 1)
    11: "Devis Fournisseur", 12: "Commande Fournisseur", 13: "Preparation Reception",
    14: "Bon de Reception",        # ENTREE STOCK
    15: "Retour Fournisseur",      # SORTIE STOCK
    16: "Avoir Fournisseur",
    17: "Facture Fournisseur",     # ENTREE STOCK
    18: "Avoir Facture Fourn.",    # SORTIE STOCK
    # STOCK INTERNE (Domaine 2)
    19: "Entree de Stock",         # ENTREE
    20: "Sortie de Stock",         # SORTIE
    21: "Transfert Inter-depot",   # TRANSFERT
}

# Types qui constituent une SORTIE de stock (DL_MvtStock=3 normalement, ici par DO_Type)
DO_TYPES_SORTIE = {3, 6, 15, 18, 20}
# Types qui constituent une ENTREE de stock
DO_TYPES_ENTREE = {4, 7, 14, 17, 19}

# Prefixes GTC identifies dans l'ancien logiciel (StockBridge Suite Pro)
PREFIXES_GTC = {
    "BLCB": "BL Client Bertoua", "FACB": "Facture Client Bertoua",
    "BCCB": "BC Client Bertoua", "FRCB": "Retour Client Bertoua",
    "BRCB": "BR Client Bertoua", "FAFB": "Facture Achat Fourn. Bertoua",
    "MESB": "Stock Initial Bertoua", "MSSB": "Sortie Stock Bertoua",
    "MTSB": "Transfert Stock Bertoua",
}

# ── Reconstitution BL (regle metier StockBridge validee) ──────────────────────
# Bug deja resolu dans l'ancien logiciel : DL_QteBL peut etre NULL quand le BL
# a deja ete transforme en facture. Strategie validee :
#   1. Chercher dans les FACTURES (DO_Type=6) ou DL_PieceBL = no_bl (cas normal,
#      le BL a ete factures)
#   2. Fallback : chercher le BL direct (DO_Type=3) s'il n'a pas encore ete facture
# Le parametre no_bl est passe DEUX FOIS (une fois par branche UNION).
SQL_BL_UNIFIE = """
    SELECT
        DL.DL_PieceBL                    AS no_bl,
        DH.DO_Piece                      AS no_facture,
        DH.DO_Type                       AS do_type,
        CONVERT(DATE, DL.DL_DateBL)      AS date_bl,
        DH.DO_Tiers                      AS code_client,
        ISNULL(CT.CT_Intitule,'')        AS client_nom,
        DL.AR_Ref                        AS code_article,
        DL.DL_Design                     AS designation,
        COALESCE(DL.DL_QteBL, DL.DL_Qte) AS quantite,
        DL.DL_PrixUnitaire               AS prix_unitaire,
        DL.DL_MontantHT                  AS montant_ht,
        ISNULL(DEP.DE_Intitule,'')       AS depot,
        DL.DE_No                         AS depot_no
    FROM F_DOCLIGNE DL
    INNER JOIN F_DOCENTETE DH ON DH.DO_Piece=DL.DO_Piece AND DH.DO_Type=DL.DO_Type
    LEFT JOIN F_COMPTET CT  ON CT.CT_Num=DH.DO_Tiers
    LEFT JOIN F_DEPOT DEP   ON DEP.DE_No=DL.DE_No
    WHERE DH.DO_Type=6 AND DL.DL_PieceBL=?

    UNION

    SELECT
        DH.DO_Piece                      AS no_bl,
        DH.DO_Piece                      AS no_facture,
        DH.DO_Type                       AS do_type,
        CONVERT(DATE, DH.DO_Date)        AS date_bl,
        DH.DO_Tiers                      AS code_client,
        ISNULL(CT.CT_Intitule,'')        AS client_nom,
        DL.AR_Ref                        AS code_article,
        DL.DL_Design                     AS designation,
        DL.DL_Qte                        AS quantite,
        DL.DL_PrixUnitaire               AS prix_unitaire,
        DL.DL_MontantHT                  AS montant_ht,
        ISNULL(DEP.DE_Intitule,'')       AS depot,
        DL.DE_No                         AS depot_no
    FROM F_DOCENTETE DH
    JOIN F_DOCLIGNE DL ON DL.DO_Type=DH.DO_Type AND DL.DO_Piece=DH.DO_Piece
    LEFT JOIN F_COMPTET CT ON CT.CT_Num=DH.DO_Tiers
    LEFT JOIN F_DEPOT DEP  ON DEP.DE_No=DL.DE_No
    WHERE DH.DO_Type=3 AND DH.DO_Piece=?

    ORDER BY code_article
"""

def reconstituer_bl(no_bl):
    """
    Reconstitue les lignes d'un BL, qu'il soit deja converti en facture
    (DO_Type=6, retrouve via DL_PieceBL) ou encore autonome (DO_Type=3).
    Regle metier validee dans StockBridge Suite Pro (bug DL_QteBL NULL corrige).
    Le parametre no_bl est passe deux fois (une fois par branche UNION).
    """
    return sage_query(SQL_BL_UNIFIE, (no_bl, no_bl))

def get_mouvements(date_debut=None, date_fin=None, depot_no=7):
    """
    Mouvements de stock reels, bases sur le mapping DO_Type valide
    (sorties: BL/Facture/Retour Fourn./Avoir Facture Fourn./Sortie Stock,
     entrees: Retour Client/Facture Avoir/Reception/Facture Fourn./Entree Stock).
    Note : le champ client sur F_DOCENTETE est DO_Tiers, pas CT_Num
    (CT_Num n'existe que sur F_COMPTET et F_ECRITUREC) — confirme par le
    schema reel via l'erreur SQL 42S22 sur Top Sorties/Dormants.
    """
    types_concernes = sorted(DO_TYPES_SORTIE | DO_TYPES_ENTREE)
    placeholders = ','.join('?' * len(types_concernes))
    sql = f"""
        SELECT e.DO_Piece, e.DO_Date, e.DO_Type,
               e.DO_Tiers AS CT_Num, e.DO_TTC,
               l.AR_Ref, l.DL_Design, l.DL_Qte,
               l.DL_PrixUnitaire, l.DL_MvtStock, l.DE_No
        FROM F_DOCENTETE e
        JOIN F_DOCLIGNE l ON l.DO_Type=e.DO_Type AND l.DO_Piece=e.DO_Piece
        WHERE e.DO_Type IN ({placeholders}) AND l.DE_No=?
    """
    params = list(types_concernes) + [depot_no]
    if date_debut:
        sql += " AND e.DO_Date >= ?"; params.append(str(date_debut))
    if date_fin:
        sql += " AND e.DO_Date <= ?"; params.append(str(date_fin))
    sql += " ORDER BY e.DO_Date DESC"
    return sage_query(sql, params)

def get_factures_vente(date_debut=None, date_fin=None):
    sql = """
        SELECT DO_Piece, DO_Date, DO_Tiers AS CT_Num, DO_TTC, DO_MajCpta, DO_Ref
        FROM F_DOCENTETE WHERE DO_Type=6
    """
    params = []
    if date_debut:
        sql += " AND DO_Date >= ?"; params.append(str(date_debut))
    if date_fin:
        sql += " AND DO_Date <= ?"; params.append(str(date_fin))
    sql += " ORDER BY DO_Date DESC"
    return sage_query(sql, params)

def get_commerciaux():
    return sage_query("SELECT CO_No, CO_Nom FROM F_COLLABORATEUR ORDER BY CO_Nom")

def get_comptes_clients():
    return sage_query(
        "SELECT CT_Num, CT_Intitule, CT_Solde, CT_Telephone, CT_Ville "
        "FROM F_COMPTET WHERE CT_Type=0 ORDER BY CT_Intitule"
    )
