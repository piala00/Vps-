"""NEXORA v2.0 — Authentification et decorateurs"""
import logging
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from core.database import (db_one, db_all, get_config, set_config,
                            audit, get_accessible_modules, verify_pwd)

log = logging.getLogger('NEXORA.Auth')

_NEXORA_MASTER     = 'nexora_master'
_NEXORA_MASTER_NOM = 'Youssouf HAMADOU'

# ── Matrice RBAC par sous-onglet (fidele a GTC ERP PILOT V3 _ROLE_TABS) ──────
# Definit quels sous-onglets Commercial/Comptabilite sont visibles selon le role.
ROLE_SUBTABS = {
    'admin':      {'commercial': ['com-dashboard','com-classement','com-cockpit','com-tendances',
                                   'com-clients','com-objectifs','com-analyse-ca','com-previsions'],
                   'comptabilite': ['compta-dashboard','gl-vue','cr-global','cr-aging','cr-zones',
                                     'cr-commerciaux','cr-clients','cr-priorite','compta-caisse']},
    'direction':  {'commercial': ['com-dashboard','com-classement','com-cockpit','com-tendances',
                                   'com-clients','com-objectifs','com-analyse-ca','com-previsions'],
                   'comptabilite': ['compta-dashboard','gl-vue','cr-global','cr-aging','cr-zones',
                                     'cr-commerciaux','cr-clients','cr-priorite','compta-caisse']},
    'financier':  {'commercial': ['com-dashboard','com-tendances','com-clients'],
                   'comptabilite': ['compta-dashboard','gl-vue','cr-global','cr-aging','cr-zones',
                                     'cr-commerciaux','cr-clients','cr-priorite','compta-caisse']},
    'agence':     {'commercial': ['com-dashboard','com-classement','com-cockpit','com-tendances',
                                   'com-clients','com-objectifs'],
                   'comptabilite': ['compta-dashboard','gl-vue','cr-global','cr-aging','cr-zones',
                                     'cr-commerciaux','cr-clients','cr-priorite']},
    'commercial': {'commercial': ['com-dashboard','com-cockpit'],
                   'comptabilite': ['compta-dashboard','gl-vue','cr-global']},
}
# Roles NEXORA additionnels (comptable/logistique/viewer) heritent d'admin par defaut
_DEFAULT_SUBTABS = ROLE_SUBTABS['admin']


def get_allowed_subtabs(role, module):
    """Retourne la liste des sous-onglets autorises pour un role et un module."""
    cfg = ROLE_SUBTABS.get(role, _DEFAULT_SUBTABS)
    return cfg.get(module, _DEFAULT_SUBTABS.get(module, []))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_id') is None:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'ok': False, 'msg': 'Non connecte'}), 401
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


def get_user():
    return {
        'id':              session.get('user_id', 0),
        'username':        session.get('username', ''),
        'nom':             session.get('nom', ''),
        'prenom':          session.get('prenom', ''),
        'agence':          session.get('agence', 'BERTOUA'),
        'role':            session.get('role', 'commercial'),
        'poste':           session.get('poste', ''),
        'categorie':       session.get('categorie', ''),
        'commercial_name': session.get('commercial_name', ''),
        'telegram_id':     session.get('telegram_id', ''),
        'is_master':       session.get('is_master', False),
        'modules':         session.get('modules', []),
    }


def get_ip():
    return (request.headers.get('X-Forwarded-For') or
            request.remote_addr or '')


def set_master_session():
    from core.database import PERMISSIONS_TREE
    session['user_id']        = 0
    session['username']       = _NEXORA_MASTER
    session['nom']            = _NEXORA_MASTER_NOM
    session['prenom']         = ''
    session['agence']         = 'Direction Generale'
    session['role']           = 'admin'
    session['poste']          = 'Developpeur Principal'
    session['categorie']      = 'MASTER'
    session['commercial_name']= ''
    session['telegram_id']    = ''
    session['is_master']      = True
    session['modules']        = list(PERMISSIONS_TREE.keys())
    session['perms']          = {}


def process_login(username, password=''):
    """
    Authentification NEXORA.
    - nexora_master   → accès total (mode conception, pas de mdp)
    - Autres users    → vérification PBKDF2 (ou sans mdp en mode conception)
    """
    username = username.strip().lower()

    if username == _NEXORA_MASTER:
        set_master_session()
        audit(_NEXORA_MASTER, 'AUTH', 'LOGIN_MASTER', '', get_ip())
        log.info("[MASTER] Connexion Super Admin")
        return True, 'accueil'

    user = db_one(
        "SELECT * FROM utilisateurs WHERE username=? AND actif=1",
        (username,))
    if not user:
        return False, None

    # Vérification mot de passe (PBKDF2 + rétrocompatibilité)
    stored_hash = user.get('password_hash', '')
    if stored_hash:
        if not verify_pwd(password or '', stored_hash):
            return False, None
        # Migration automatique vers PBKDF2 si ancien hash
        if stored_hash and not stored_hash.startswith('pbkdf2:') and password:
            from core.database import hash_pwd, db_exec
            db_exec("UPDATE utilisateurs SET password_hash=? WHERE id=?",
                    (hash_pwd(password), user['id']))

    session['user_id']         = user['id']
    session['username']        = user['username']
    session['nom']             = user['nom']
    session['prenom']          = user.get('prenom', '')
    session['agence']          = user.get('agence', 'BERTOUA')
    session['role']            = user.get('role', 'commercial')
    session['poste']           = user.get('poste', '')
    session['categorie']       = user.get('categorie', '')
    session['commercial_name'] = user.get('commercial_name', '')
    session['telegram_id']     = user.get('telegram_id', '')
    session['is_master']       = False
    session['modules']         = get_accessible_modules(user['id'])
    session['perms']           = {}
    audit(username, 'AUTH', 'LOGIN', '', get_ip())
    log.info("Login: %s", username)
    return True, 'accueil'
