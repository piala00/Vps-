#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/parametres/routes.py
NEXORA v2.0 — Module Parametres : configuration generale, connexion Sage,
etat de la base, utilisateurs, droits d'acces, controle IP, journal d'audit,
licence et compte personnel.
"""
import json
import os
import shutil
import socket
from datetime import datetime

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import (
    db_all, db_one, db_exec,
    get_config, set_config, has_permission,
    hash_pwd, verify_pwd, audit,
    PERMISSIONS_TREE, set_all_permissions, get_user_permissions,
    get_db_path,
)
from core.nexora_security import login_required
from core.nexora_licence import get_licence_manager
import core.sage_connector as sage


def _peut(uid, sous_module, action="lire"):
    return session.get("is_master") or has_permission(uid, "parametres", sous_module, action)


@bp.route('/module/parametres')
@login_required
def module_parametres():
    uid = session['user_id']
    if not _peut(uid, 'config_generale', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/parametres.html', module='parametres',
                            module_label='⚙️ Parametres',
                            societe_nom=get_config('societe_nom', 'NEXORA'))


# ── Configuration generale ───────────────────────────────────────────────
@bp.route('/api/config/generale', methods=['GET', 'POST'])
@login_required
def api_config_generale():
    uid = session['user_id']
    if request.method == 'GET':
        if not _peut(uid, 'config_generale', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        return jsonify(ok=True, config={
            'societe_nom': get_config('societe_nom', ''),
            'societe_ville': get_config('societe_ville', ''),
            'agence_locale': get_config('agence_locale', 'BERTOUA'),
            'depot_defaut': get_config('depot_defaut', '7'),
            'app_version': get_config('app_version', '2.0.0'),
        })

    if not _peut(uid, 'config_generale', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    for cle in ('societe_nom', 'societe_ville', 'agence_locale', 'depot_defaut'):
        if cle in data:
            set_config(cle, str(data[cle]).strip())
    audit(session['username'], 'PARAMETRES', 'CONFIG_GENERALE', 'Mise a jour configuration generale')
    return jsonify(ok=True)


# ── Connexion Sage ────────────────────────────────────────────────────────
@bp.route('/api/config/sage', methods=['GET', 'POST'])
@login_required
def api_config_sage():
    uid = session['user_id']
    if request.method == 'GET':
        if not _peut(uid, 'config_sage', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        cfg = sage.get_config()
        return jsonify(ok=True, config={
            'server': cfg['server'],
            'database': cfg['database'],
            'trusted': cfg['trusted'],
            'login': cfg['login'],
            'password_defini': bool(cfg['password']),
            'driver': sage.get_driver() or '',
            'drivers_disponibles': sage.get_drivers_list(),
            'pyodbc_disponible': sage.HAS_PYODBC,
        })

    if not _peut(uid, 'config_sage', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    set_config('sage_server', str(data.get('server', '')).strip())
    set_config('sage_database', str(data.get('database', '')).strip())
    set_config('sage_trusted', '1' if data.get('trusted') else '0')
    set_config('sage_login', str(data.get('login', 'sa')).strip())
    if data.get('password'):
        set_config('sage_password', data.get('password'))
    audit(session['username'], 'PARAMETRES', 'CONFIG_SAGE', 'Mise a jour connexion Sage')
    return jsonify(ok=True)


@bp.route('/api/config/test-sage')
@login_required
def api_config_test_sage():
    uid = session['user_id']
    if not _peut(uid, 'config_sage', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    ok, msg = sage.test_connexion()
    return jsonify(ok=ok, msg=msg)


# ── Utilisateurs ──────────────────────────────────────────────────────────
@bp.route('/api/utilisateurs', methods=['GET', 'POST'])
@login_required
def api_utilisateurs():
    uid = session['user_id']
    if request.method == 'GET':
        if not _peut(uid, 'utilisateurs', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        rows = db_all(
            "SELECT id,username,nom,prenom,email,telephone,agence,actif,cree_le"
            " FROM utilisateurs WHERE masque=0 ORDER BY nom,prenom")
        return jsonify(ok=True, utilisateurs=rows)

    if not _peut(uid, 'utilisateurs', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    nom = (data.get('nom') or '').strip()
    if not username or not nom:
        return jsonify(ok=False, msg='Identifiant et nom requis')
    if db_one("SELECT id FROM utilisateurs WHERE username=?", (username,)):
        return jsonify(ok=False, msg='Cet identifiant existe deja')
    new_id = db_exec(
        "INSERT INTO utilisateurs(username,password_hash,nom,prenom,email,telephone,agence)"
        " VALUES(?,?,?,?,?,?,?)",
        (username, hash_pwd(data.get('password', '')), nom,
         (data.get('prenom') or '').strip(), (data.get('email') or '').strip(),
         (data.get('telephone') or '').strip(),
         (data.get('agence') or get_config('agence_locale', 'BERTOUA')).strip()))
    set_all_permissions(new_id, False)
    audit(session['username'], 'PARAMETRES', 'UTILISATEUR_CREATION', username)
    return jsonify(ok=True, id=new_id)


@bp.route('/api/utilisateurs/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
def api_utilisateur_detail(user_id):
    uid = session['user_id']
    target = db_one("SELECT * FROM utilisateurs WHERE id=? AND masque=0", (user_id,))
    if not target:
        return jsonify(ok=False, msg='Utilisateur introuvable'), 404

    if request.method == 'DELETE':
        if not _peut(uid, 'utilisateurs', 'supprimer'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        db_exec("UPDATE utilisateurs SET actif=0 WHERE id=?", (user_id,))
        audit(session['username'], 'PARAMETRES', 'UTILISATEUR_DESACTIVATION', target['username'])
        return jsonify(ok=True)

    if not _peut(uid, 'utilisateurs', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    champs = {}
    for cle in ('nom', 'prenom', 'email', 'telephone', 'agence'):
        if cle in data:
            champs[cle] = str(data[cle]).strip()
    if 'actif' in data:
        champs['actif'] = 1 if data['actif'] else 0
    if data.get('password'):
        champs['password_hash'] = hash_pwd(data['password'])
    if champs:
        sets = ','.join('%s=?' % k for k in champs)
        params = tuple(champs.values()) + (user_id,)
        db_exec("UPDATE utilisateurs SET %s WHERE id=?" % sets, params)
    audit(session['username'], 'PARAMETRES', 'UTILISATEUR_MODIFICATION', target['username'])
    return jsonify(ok=True)


# ── Droits d'acces ────────────────────────────────────────────────────────
@bp.route('/api/parametres/permissions-tree')
@login_required
def api_permissions_tree():
    uid = session['user_id']
    if not _peut(uid, 'droits', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, tree=PERMISSIONS_TREE)


@bp.route('/api/utilisateurs/<int:user_id>/permissions', methods=['GET', 'POST'])
@login_required
def api_utilisateur_permissions(user_id):
    uid = session['user_id']
    target = db_one("SELECT id,username FROM utilisateurs WHERE id=? AND masque=0", (user_id,))
    if not target:
        return jsonify(ok=False, msg='Utilisateur introuvable'), 404

    if request.method == 'GET':
        if not _peut(uid, 'droits', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        return jsonify(ok=True, permissions=get_user_permissions(user_id))

    if not _peut(uid, 'droits', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    perms = data.get('permissions') or {}
    for module, m in PERMISSIONS_TREE.items():
        for sm, smdata in m['sous_modules'].items():
            for action in smdata['actions']:
                autorise = bool(perms.get(module, {}).get(sm, {}).get(action))
                db_exec(
                    "INSERT OR REPLACE INTO permissions"
                    " (user_id,module,sous_module,action,autorise) VALUES(?,?,?,?,?)",
                    (user_id, module, sm, action, 1 if autorise else 0))
    audit(session['username'], 'PARAMETRES', 'DROITS_MODIFICATION', target['username'])
    return jsonify(ok=True)


@bp.route('/api/utilisateurs/<int:user_id>/permissions/tout', methods=['POST'])
@login_required
def api_utilisateur_permissions_tout(user_id):
    uid = session['user_id']
    target = db_one("SELECT id,username FROM utilisateurs WHERE id=? AND masque=0", (user_id,))
    if not target:
        return jsonify(ok=False, msg='Utilisateur introuvable'), 404
    if not _peut(uid, 'droits', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    autorise = bool(data.get('autorise'))
    set_all_permissions(user_id, autorise)
    audit(session['username'], 'PARAMETRES', 'DROITS_TOUT',
          '%s -> %s' % (target['username'], 'AUTORISE' if autorise else 'REVOQUE'))
    return jsonify(ok=True)


# ── Controle IP ───────────────────────────────────────────────────────────
@bp.route('/api/config/ip-whitelist', methods=['GET', 'POST'])
@login_required
def api_ip_whitelist():
    uid = session['user_id']
    if request.method == 'GET':
        if not _peut(uid, 'config_generale', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        try:
            whitelist = json.loads(get_config('ip_whitelist', '[]'))
        except Exception:
            whitelist = []
        return jsonify(ok=True, active=get_config('ip_whitelist_active', '0') == '1',
                        whitelist=whitelist)

    if not _peut(uid, 'config_generale', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    data = request.get_json(silent=True) or {}
    set_config('ip_whitelist_active', '1' if data.get('active') else '0')
    if 'whitelist' in data:
        set_config('ip_whitelist', json.dumps(data.get('whitelist') or []))
    audit(session['username'], 'PARAMETRES', 'IP_WHITELIST', 'Mise a jour liste blanche')
    return jsonify(ok=True)


@bp.route('/api/config/ip-whitelist/ajouter', methods=['POST'])
@login_required
def api_ip_whitelist_ajouter():
    uid = session['user_id']
    if not _peut(uid, 'config_generale', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    ip = ((request.get_json(silent=True) or {}).get('ip') or '').strip()
    if not ip:
        return jsonify(ok=False, msg='Adresse IP requise')
    try:
        whitelist = json.loads(get_config('ip_whitelist', '[]'))
    except Exception:
        whitelist = []
    if ip not in whitelist:
        whitelist.append(ip)
        set_config('ip_whitelist', json.dumps(whitelist))
    audit(session['username'], 'PARAMETRES', 'IP_AJOUT', ip)
    return jsonify(ok=True, whitelist=whitelist)


@bp.route('/api/config/ip-whitelist/supprimer', methods=['POST'])
@login_required
def api_ip_whitelist_supprimer():
    uid = session['user_id']
    if not _peut(uid, 'config_generale', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    ip = ((request.get_json(silent=True) or {}).get('ip') or '').strip()
    try:
        whitelist = json.loads(get_config('ip_whitelist', '[]'))
    except Exception:
        whitelist = []
    whitelist = [w for w in whitelist if w != ip]
    set_config('ip_whitelist', json.dumps(whitelist))
    audit(session['username'], 'PARAMETRES', 'IP_SUPPRESSION', ip)
    return jsonify(ok=True, whitelist=whitelist)


@bp.route('/api/network-info')
@login_required
def api_network_info():
    ip_locale = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_locale = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    return jsonify(ok=True, ip_locale=ip_locale, hostname=socket.gethostname())


# ── Journal d'audit ───────────────────────────────────────────────────────
@bp.route('/api/audit/blocages')
@login_required
def api_audit_blocages():
    uid = session['user_id']
    if not _peut(uid, 'config_generale', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    limite = int(request.args.get('limite', 100))
    rows = db_all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limite,))
    return jsonify(ok=True, audit=rows)


# ── Licence ───────────────────────────────────────────────────────────────
@bp.route('/api/licence/desactiver', methods=['POST'])
@login_required
def api_licence_desactiver():
    uid = session['user_id']
    if not _peut(uid, 'licence', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    mgr = get_licence_manager()
    if not mgr:
        return jsonify(ok=False, msg='Module licence indisponible')
    mgr.desactiver()
    audit(session['username'], 'PARAMETRES', 'LICENCE_DESACTIVATION', '')
    return jsonify(ok=True)


# ── Base de donnees ───────────────────────────────────────────────────────
@bp.route('/api/database/sqlite-info')
@login_required
def api_database_sqlite_info():
    uid = session['user_id']
    if not _peut(uid, 'base_donnees', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    chemin = get_db_path()
    taille = os.path.getsize(chemin) if chemin and os.path.exists(chemin) else 0
    tables = db_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return jsonify(ok=True, chemin=chemin, taille_octets=taille,
                    nb_tables=len(tables), tables=[t['name'] for t in tables])


@bp.route('/api/database/backup-sqlite', methods=['POST'])
@login_required
def api_database_backup_sqlite():
    uid = session['user_id']
    if not _peut(uid, 'base_donnees', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    chemin = get_db_path()
    if not chemin or not os.path.exists(chemin):
        return jsonify(ok=False, msg='Base de donnees introuvable')
    horodatage = datetime.now().strftime('%Y%m%d_%H%M%S')
    dossier = os.path.join(os.path.dirname(chemin), 'backups')
    os.makedirs(dossier, exist_ok=True)
    dest = os.path.join(dossier, 'nexora_backup_%s.db' % horodatage)
    shutil.copy2(chemin, dest)
    audit(session['username'], 'PARAMETRES', 'BACKUP_SQLITE', dest)
    return jsonify(ok=True, fichier=dest)


@bp.route('/api/database/vacuum-sqlite', methods=['POST'])
@login_required
def api_database_vacuum_sqlite():
    uid = session['user_id']
    if not _peut(uid, 'base_donnees', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    db_exec('VACUUM')
    audit(session['username'], 'PARAMETRES', 'VACUUM_SQLITE', '')
    return jsonify(ok=True)


# ── Mon compte ────────────────────────────────────────────────────────────
@bp.route('/api/mon-password', methods=['POST'])
@login_required
def api_mon_password():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    ancien = data.get('ancien_password', '')
    nouveau = data.get('nouveau_password', '')
    if not nouveau:
        return jsonify(ok=False, msg='Nouveau mot de passe requis')
    user = db_one("SELECT * FROM utilisateurs WHERE id=?", (uid,))
    if not user:
        return jsonify(ok=False, msg='Utilisateur introuvable'), 404
    if user['password_hash'] and not verify_pwd(ancien, user['password_hash']):
        return jsonify(ok=False, msg='Ancien mot de passe incorrect')
    db_exec("UPDATE utilisateurs SET password_hash=? WHERE id=?", (hash_pwd(nouveau), uid))
    audit(session['username'], 'PARAMETRES', 'CHANGEMENT_PASSWORD', '')
    return jsonify(ok=True)
