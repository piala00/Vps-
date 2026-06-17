"""NEXORA v2.0 — Base de données SQLite"""
import sqlite3, hashlib, hmac, os, logging
from functools import wraps

log = logging.getLogger('NEXORA.DB')
_DB_PATH = None

def init_db(db_path):
    global _DB_PATH
    _DB_PATH = db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS configuration (
    cle TEXT PRIMARY KEY, valeur TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT DEFAULT '',
    nom TEXT NOT NULL, prenom TEXT DEFAULT '',
    email TEXT DEFAULT '', telephone TEXT DEFAULT '',
    agence TEXT DEFAULT 'BERTOUA',
    role TEXT DEFAULT 'commercial',
    poste TEXT DEFAULT '',
    categorie TEXT DEFAULT '',
    commercial_name TEXT DEFAULT '',
    telegram_id TEXT DEFAULT '',
    actif INTEGER DEFAULT 1,
    cree_le TEXT DEFAULT (datetime('now'))
);
/* Migration colonnes utilisateurs si DB existante */

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
    module TEXT NOT NULL, sous_module TEXT NOT NULL,
    action TEXT NOT NULL, autorise INTEGER DEFAULT 0,
    UNIQUE(user_id, module, sous_module, action)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT, module TEXT, action TEXT,
    detail TEXT, ip TEXT DEFAULT '',
    date_op TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS mouvements_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_mouvement TEXT NOT NULL,
    no_doc_sage TEXT DEFAULT '', no_doc_manuel TEXT DEFAULT '',
    date_mvt TEXT, depot TEXT DEFAULT 'BERTOUA',
    code_article TEXT, designation TEXT,
    qte_saisie REAL DEFAULT 0, qte_doc_sage REAL DEFAULT 0,
    ecart REAL DEFAULT 0, code_client TEXT DEFAULT '',
    client_nom TEXT DEFAULT '', statut TEXT DEFAULT 'en_attente',
    regularise INTEGER DEFAULT 0, regularise_le TEXT,
    no_sage_lie TEXT DEFAULT '', saisi_par TEXT,
    agence TEXT DEFAULT 'BERTOUA',
    cree_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS camions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    immatriculation TEXT UNIQUE NOT NULL,
    marque TEXT, modele TEXT, type_flotte TEXT DEFAULT 'MAISON',
    proprietaire TEXT, compte_sage TEXT,
    capacite_tonnes REAL DEFAULT 0, annee_mise_service INTEGER,
    observations TEXT, actif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS personnel_logistique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL, prenom TEXT, role TEXT DEFAULT 'CHAUFFEUR',
    telephone TEXT, permis TEXT,
    camion_id INTEGER REFERENCES camions(id), actif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS voyages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no_voyage TEXT UNIQUE, camion_id INTEGER REFERENCES camions(id),
    chauffeur_id INTEGER REFERENCES personnel_logistique(id),
    convoyeur_id INTEGER REFERENCES personnel_logistique(id),
    origine TEXT, destination TEXT, date_depart TEXT, date_retour TEXT,
    marchandises TEXT, client_fournisseur TEXT,
    statut TEXT DEFAULT 'planifie', observations TEXT,
    cree_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transactions_camion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camion_id INTEGER REFERENCES camions(id),
    voyage_id INTEGER REFERENCES voyages(id),
    type_transaction TEXT DEFAULT 'DEPENSE',
    categorie TEXT DEFAULT 'AUTRE', date_transaction TEXT,
    montant REAL DEFAULT 0, libelle TEXT,
    reference_sage TEXT, saisi_par TEXT,
    cree_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS entretiens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camion_id INTEGER REFERENCES camions(id),
    type_entretien TEXT, date_entretien TEXT,
    kilometrage INTEGER DEFAULT 0, cout REAL DEFAULT 0,
    prestataire TEXT, description TEXT, prochaine_revision TEXT,
    cree_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rapports_caisse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_rapport TEXT, commercial TEXT,
    agence TEXT DEFAULT 'BERTOUA',
    total_ventes REAL DEFAULT 0, total_encaisse REAL DEFAULT 0,
    total_credit REAL DEFAULT 0, observations TEXT,
    statut TEXT DEFAULT 'brouillon', saisi_par TEXT,
    cree_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lignes_rapport_caisse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rapport_id INTEGER REFERENCES rapports_caisse(id),
    no_facture TEXT, code_client TEXT, client_nom TEXT,
    montant_facture REAL DEFAULT 0, montant_encaisse REAL DEFAULT 0,
    mode_paiement TEXT DEFAULT 'ESPECES', observations TEXT
);
CREATE TABLE IF NOT EXISTS fiches_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_client TEXT UNIQUE NOT NULL, nom TEXT NOT NULL,
    prenom TEXT, telephone TEXT, telephone2 TEXT,
    email TEXT, adresse TEXT, ville TEXT, quartier TEXT,
    activite TEXT, secteur TEXT, commercial_attitree TEXT,
    plafond_credit REAL DEFAULT 0, delai_paiement INTEGER DEFAULT 30,
    observations TEXT, actif INTEGER DEFAULT 1,
    cree_le TEXT DEFAULT (datetime('now')),
    modifie_le TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS objectifs_commerciaux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commercial TEXT, periode TEXT,
    objectif_ca REAL DEFAULT 0,
    objectif_recouvrement REAL DEFAULT 0,
    objectif_nb_clients INTEGER DEFAULT 0,
    UNIQUE(commercial, periode)
);
CREATE TABLE IF NOT EXISTS employes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricule TEXT UNIQUE NOT NULL, nom TEXT NOT NULL,
    prenom TEXT, poste TEXT, departement TEXT,
    date_embauche TEXT, salaire_base REAL DEFAULT 0,
    telephone TEXT, email TEXT, actif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS presences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employe_id INTEGER REFERENCES employes(id),
    date_presence TEXT, statut TEXT DEFAULT 'PRESENT',
    observations TEXT,
    UNIQUE(employe_id, date_presence)
);
CREATE TABLE IF NOT EXISTS nx_transferts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT UNIQUE NOT NULL,
    agence_source_id INTEGER, agence_dest_id INTEGER,
    statut TEXT DEFAULT 'SOUMISE', urgence INTEGER DEFAULT 0,
    date_demande TEXT DEFAULT (date('now')),
    demande_par TEXT, date_validation TEXT,
    valide_par TEXT, motif_refus TEXT,
    nb_lignes INTEGER DEFAULT 0, valeur_totale REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nx_transferts_lignes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfert_id INTEGER REFERENCES nx_transferts(id),
    ar_ref TEXT, designation TEXT, unite TEXT,
    qte_demandee REAL DEFAULT 0, qte_livree REAL DEFAULT 0,
    prix_unitaire REAL DEFAULT 0, stock_dispo_src REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nx_demandes_achat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT UNIQUE NOT NULL,
    agence_id INTEGER, fournisseur_code TEXT, fournisseur_nom TEXT,
    statut TEXT DEFAULT 'SOUMISE', urgence INTEGER DEFAULT 0,
    livraison_agence INTEGER,
    date_demande TEXT DEFAULT (date('now')),
    demande_par TEXT, date_validation TEXT,
    valide_par TEXT, motif_refus TEXT,
    bc_numero TEXT, observations TEXT, valeur_totale REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nx_agences (
    id INTEGER PRIMARY KEY, nom TEXT NOT NULL,
    ville TEXT, type_site TEXT DEFAULT 'AGENCE',
    depot_sage_no INTEGER, actif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS nx_bi_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT, indicateur TEXT, periode TEXT,
    valeur REAL DEFAULT 0,
    date_snapshot TEXT DEFAULT (datetime('now'))
);
""")
    # Données initiales
    conn.executescript("""

        CREATE TABLE IF NOT EXISTS ref_clients (
            code TEXT PRIMARY KEY, nom TEXT DEFAULT '',
            zone TEXT DEFAULT '', commercial TEXT DEFAULT '',
            plafond REAL DEFAULT 0, delai INTEGER DEFAULT 30,
            telephone TEXT DEFAULT '', com_source TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS liste_commerciaux (
            nom TEXT PRIMARY KEY, objectif REAL DEFAULT 0, ordre INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY, value TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS data_snapshot (
            key TEXT PRIMARY KEY, value TEXT,
            updated_at TEXT DEFAULT(datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS bot_inscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT, telegram_nom TEXT,
            nom TEXT, poste TEXT, agence TEXT,
            statut TEXT DEFAULT 'EN_ATTENTE',
            created_at TEXT DEFAULT(datetime('now')),
            validated_by TEXT DEFAULT '',
            validated_at TEXT
        );
        INSERT OR IGNORE INTO nx_agences VALUES (2,'Bertoua (Siege)','Bertoua','SIEGE',7,1);
INSERT OR IGNORE INTO nx_agences VALUES (3,'Douala','Douala','AGENCE',NULL,1);
INSERT OR IGNORE INTO nx_agences VALUES (4,'Yaounde','Yaounde','AGENCE',NULL,1);
INSERT OR IGNORE INTO nx_agences VALUES (5,'Garoua-Boulai','Garoua-Boulai','AGENCE',NULL,1);
INSERT OR IGNORE INTO nx_agences VALUES (6,'Bafoussam','Bafoussam','AGENCE',NULL,1);
INSERT OR IGNORE INTO nx_agences VALUES (7,'Batouri','Batouri','AGENCE',NULL,1);
INSERT OR IGNORE INTO nx_agences VALUES (8,'Abong-Mbang','Abong-Mbang','AGENCE',NULL,1);
INSERT OR IGNORE INTO configuration(cle,valeur) VALUES('app_name','NEXORA');
INSERT OR IGNORE INTO configuration(cle,valeur) VALUES('app_version','2.0');
INSERT OR IGNORE INTO configuration(cle,valeur) VALUES('devise','XAF');
""")
    conn.commit()

    # Migration : ajout des colonnes manquantes sur bases deja existantes.
    # CREATE TABLE IF NOT EXISTS ne modifie jamais une table deja creee avec
    # un schema plus ancien, d'ou "no such column" sur les bases anciennes.
    _migrate_columns(conn, 'utilisateurs', [
        ("role", "TEXT DEFAULT 'commercial'"),
        ("poste", "TEXT DEFAULT ''"),
        ("categorie", "TEXT DEFAULT ''"),
        ("commercial_name", "TEXT DEFAULT ''"),
        ("telegram_id", "TEXT DEFAULT ''"),
    ])
    _migrate_columns(conn, 'ref_clients', [
        ("com_source", "TEXT DEFAULT ''"),
    ])
    conn.commit()
    _seed_utilisateurs_reels(conn)
    conn.commit()
    conn.close()
    log.info("Base initialisee: %s", db_path)


def _seed_utilisateurs_reels(conn):
    """
    Insere la liste reelle des utilisateurs GTC si la table est vide.
    Donnees confirmees depuis l'ancien logiciel pilote (capture utilisateurs).
    N'ecrase jamais des utilisateurs deja crees par l'admin.
    """
    try:
        nb = conn.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
    except Exception:
        return
    if nb > 0:
        return
    utilisateurs_reels = [
        # username, nom, role, poste, agence, commercial_name, telegram_id
        ("admin",               "admin",                 "admin",      "",                          "",                   "",                       "6259313068"),
        ("aminatou",             "AMINATOU",              "direction",  "Comptable",                 "Direction generale", "",                       "1134826947"),
        ("youssoufa.ousmanou",   "YOUSSOUFA OUSMANOU",    "direction",  "Comptable",                 "Direction generale", "",                       "1889352538"),
        ("khadidja.mouhamadou",  "Khadidja mouhamadou",   "commercial", "Commercial",                "GTC BERTOUA",        "Khadidja mouhamadou",   "5830037240"),
        ("alim.garga",           "ALIM GARGA",            "commercial", "Commercial",                "GTC BERTOUA",        "Alim Garga",            "8005909432"),
        ("abdouramane.mouhamad", "Abdouramane Mouhamad",  "commercial", "Commercial",                "GTC BERTOUA",        "Abdouramane Mouhamad",  "6842970337"),
        ("mohamadou.ahmadou",    "Mohamadou Ahmadou",     "commercial", "Commercial",                "GTC BERTOUA",        "Mohamadou Ahmadou",     "2063660907"),
        ("dadda.aminatou",       "Dadda aminatou",        "commercial", "Commercial",                "GTC BERTOUA",        "Dadda aminatou",        "8310342131"),
        ("ahmadou.baba",         "Ahmadou Baba",          "commercial", "Commercial",                "GTC BERTOUA",        "Ahmadou Baba",          ""),
        ("yaya.bakari",          "YAYA BAKARI",           "direction",  "Auditeur",                  "Direction generale", "",                       "1252256294"),
        ("nfor.roland",          "NFOR ROLAND",           "direction",  "DC - Directeur Commercial", "Direction generale", "Nfor Roland",            ""),
    ]
    for username, nom, role, poste, agence, commercial_name, telegram_id in utilisateurs_reels:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO utilisateurs"
                "(username,password_hash,nom,prenom,agence,role,poste,categorie,"
                "commercial_name,telegram_id,actif) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
                (username, '', nom, '', agence, role, poste, '', commercial_name, telegram_id))
        except Exception as e:
            log.warning("Seed utilisateur %s echoue: %s", username, e)
    log.info("Utilisateurs reels GTC inseres (%d)", len(utilisateurs_reels))


def _migrate_columns(conn, table, columns):
    """Ajoute les colonnes manquantes a une table existante (migration douce)."""
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")").fetchall()}
    except Exception:
        return
    for col_name, col_def in columns:
        if col_name not in existing:
            try:
                conn.execute("ALTER TABLE " + table + " ADD COLUMN " + col_name + " " + col_def)
                log.info("Migration: colonne %s.%s ajoutee", table, col_name)
            except Exception as e:
                log.warning("Migration %s.%s echouee: %s", table, col_name, e)

def _conn():
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def db_all(sql, params=()):
    c = _conn()
    try:
        rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()

def db_one(sql, params=()):
    c = _conn()
    try:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None
    finally:
        c.close()

def db_exec(sql, params=()):
    c = _conn()
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()

def get_config(key, default=''):
    r = db_one("SELECT valeur FROM configuration WHERE cle=?", (key,))
    return r['valeur'] if r else default

def set_config(key, value):
    db_exec("INSERT OR REPLACE INTO configuration(cle,valeur) VALUES(?,?)",
            (key, str(value)))

def hash_pwd(pwd):
    """Hash securise PBKDF2-HMAC-SHA256 avec sel aleatoire.
    Format : 'pbkdf2:<sel_hex>:<hash_hex>'
    Retrocompatible avec anciens hashs SHA-256 simples.
    """
    if not pwd:
        return ''
    import os as _os
    salt = _os.urandom(16)
    key  = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), salt, 260_000)
    return 'pbkdf2:' + salt.hex() + ':' + key.hex()

def verify_pwd(pwd, stored):
    """Verifie un mot de passe contre un hash stocke.
    Accepte PBKDF2 (nouveau) ET SHA-256 simple (retrocompatibilite).
    """
    if not pwd or not stored:
        return False
    if stored.startswith('pbkdf2:'):
        try:
            parts    = stored.split(':')
            salt     = bytes.fromhex(parts[1])
            key_hex  = parts[2]
            key      = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), salt, 260_000)
            return key.hex() == key_hex
        except Exception:
            return False
    # Ancien hash SHA-256 simple
    return hmac.new(b'NEXORA_SALT_2026', pwd.encode(), hashlib.sha256).hexdigest() == stored

def audit(username, module, action, detail='', ip=''):
    try:
        db_exec("INSERT INTO audit_log(username,module,action,detail,ip) VALUES(?,?,?,?,?)",
                (username, module, action, detail, ip))
    except Exception:
        pass

def get_accessible_modules(user_id):
    if user_id <= 1:
        return ['stock','logistique','commercial','comptabilite','caisse',
                'rh','rapports','consolidation','multisite','parametres']
    u = db_one("SELECT username FROM utilisateurs WHERE id=?", (user_id,))
    if u and u['username'] == 'admin':
        return ['stock','logistique','commercial','comptabilite','caisse',
                'rh','rapports','consolidation','multisite','parametres']
    rows = db_all(
        "SELECT DISTINCT module FROM permissions WHERE user_id=? AND autorise=1",
        (user_id,))
    return [r['module'] for r in rows]

def set_all_permissions(user_id, autorise):
    modules = ['stock','logistique','commercial','comptabilite','caisse',
               'rh','rapports','consolidation','multisite','parametres']
    c = _conn()
    for mod in modules:
        c.execute("INSERT OR REPLACE INTO permissions(user_id,module,sous_module,action,autorise)"
                  " VALUES(?,?,'*','view',?)", (user_id, mod, 1 if autorise else 0))
    c.commit()
    c.close()

# ── Types de permission disponibles (par sous-module) ─────────────────────────
PERMISSION_ACTIONS = {
    'lecture':    'Lecture',
    'ecriture':   'Ecriture',
    'suppression':'Suppression',
    'tout':       'Tout autoriser',
}

# ── Arborescence module -> sous-modules (fidele aux fonctionnalites reelles) ──
# Chaque sous-module peut recevoir des permissions fines (lecture/ecriture/suppression).
# Les modules sans sous-module precise utilisent un acces global ('*').
PERMISSIONS_TREE = {
    'stock':        {'label':'Stock & Inventaire', 'sous_modules': {}},
    'logistique':   {'label':'Logistique (Flotte)', 'sous_modules': {}},
    'commercial':   {'label':'Commercial (Ventes)', 'sous_modules': {
        'com-dashboard':  'Tableau de bord',
        'com-classement': 'Classement Commerciaux',
        'com-cockpit':    'Cockpit (Copilote quotidien)',
        'com-tendances':  'Tendances',
        'com-clients':    'Fiches Clients',
        'com-objectifs':  'Objectifs',
        'com-analyse-ca': 'Analyse CA',
    }},
    'comptabilite': {'label':'Comptabilite', 'sous_modules': {
        'gl-vue':         'Grand Livre General',
        'cr-global':      'Creances - Global',
        'cr-aging':       'Creances - Aging',
        'cr-zones':       'Creances - Zones',
        'cr-commerciaux': 'Creances - Commerciaux',
        'cr-clients':     'Creances - Clients (tri FNS)',
        'cr-priorite':    'Creances - Priorite',
        'compta-caisse':  'Rapport de Caisse',
    }},
    'caisse':       {'label':'Caisse (Tresorerie)', 'sous_modules': {}},
    'rh':           {'label':'Ressources Humaines', 'sous_modules': {}},
    'rapports':     {'label':'Rapports', 'sous_modules': {}},
    'consolidation':{'label':'Consolidation Multi-sites', 'sous_modules': {}},
    'multisite':    {'label':'Multi-Sites (DT/DA)', 'sous_modules': {}},
    'parametres':   {'label':'Parametres', 'sous_modules': {}},
}


def get_permission_detail(user_id, module, sous_module='*'):
    """
    Retourne le detail des permissions (lecture/ecriture/suppression) pour
    un utilisateur, un module et un sous-module donnes.
    """
    rows = db_all(
        "SELECT action, autorise FROM permissions WHERE user_id=? AND module=? AND sous_module=?",
        (user_id, module, sous_module))
    detail = {a: False for a in PERMISSION_ACTIONS}
    for r in rows:
        if r['action'] in detail:
            detail[r['action']] = bool(r['autorise'])
        elif r['action'] == 'view':
            # Retrocompatibilite avec l'ancien systeme (action='view')
            detail['lecture'] = bool(r['autorise'])
    return detail


def set_permission_detail(user_id, module, sous_module, actions: dict):
    """
    Definit les permissions fines (lecture/ecriture/suppression/tout) pour
    un utilisateur sur un module/sous-module donne.
    """
    c = _conn()
    for action, autorise in actions.items():
        if action not in PERMISSION_ACTIONS:
            continue
        c.execute(
            "INSERT OR REPLACE INTO permissions(user_id,module,sous_module,action,autorise)"
            " VALUES(?,?,?,?,?)",
            (user_id, module, sous_module, action, 1 if autorise else 0))
    # Conserver la compatibilite avec get_accessible_modules (action='view')
    a_un_droit = any(actions.values())
    c.execute(
        "INSERT OR REPLACE INTO permissions(user_id,module,sous_module,action,autorise)"
        " VALUES(?,?,?,?,?)",
        (user_id, module, sous_module, 'view', 1 if a_un_droit else 0))
    c.commit()
    c.close()


def get_user_permissions_full(user_id):
    """
    Retourne la structure complete des permissions d'un utilisateur :
    {module: {sous_module_ou_*: {lecture, ecriture, suppression, tout}}}
    Pour les modules sans sous-module, la cle est '*'.
    """
    out = {}
    for mod, cfg in PERMISSIONS_TREE.items():
        sous_mods = list(cfg.get('sous_modules', {}).keys()) or ['*']
        out[mod] = {}
        for sm in sous_mods:
            out[mod][sm] = get_permission_detail(user_id, mod, sm)
    return out
