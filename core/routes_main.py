"""NEXORA v2.0 — Routes principales"""
from flask import (render_template, redirect, url_for, request,
                   session, jsonify, Blueprint)
from core.database import (db_one, db_all, db_exec, get_config, set_config,
                           audit, get_accessible_modules, set_all_permissions,
                           hash_pwd, PERMISSIONS_TREE, init_db)
from core.auth import login_required, get_user, get_ip, process_login, set_master_session
from core.nexora_licence import get_licence_manager, NexoraLicenceVerifier
import logging, os

log = logging.getLogger('NEXORA.Main')
bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    if session.get('user_id') is None:
        if not get_config('setup_done'):
            return redirect(url_for('main.setup'))
        return redirect(url_for('main.login'))
    return redirect(url_for('main.accueil'))


@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if get_config('setup_done') and request.method == 'GET':
        return redirect(url_for('main.login'))

    if request.method == 'GET':
        return render_template('setup.html')

    d = request.get_json() or {}
    try:
        nom_societe = d.get('nom_societe', '').strip()
        if not nom_societe:
            return jsonify({'ok': False, 'message': 'Nom de societe obligatoire'})

        for key, val in {
            'nom_societe':   nom_societe,
            'sigle_societe': d.get('sigle_societe', nom_societe[:3].upper()),
            'secteur':       d.get('secteur', ''),
            'devise':        d.get('devise', 'XAF'),
            'pays':          d.get('pays', 'CM'),
            'ville_siege':   d.get('ville_siege', ''),
            'telephone':     d.get('telephone', ''),
            'nom_site':      d.get('nom_siege', nom_societe),
            'type_site':     d.get('type_site', 'SIEGE'),
        }.items():
            set_config(key, val)

        if d.get('sage_server'):
            set_config('sage_server',   d.get('sage_server', ''))
            set_config('sage_database', d.get('sage_database', ''))
            set_config('sage_user',     d.get('sage_user', 'sa'))
            set_config('sage_password', d.get('sage_password', ''))

        admin_login  = d.get('admin_login', 'admin').strip() or 'admin'
        admin_nom    = d.get('admin_nom',   'Administrateur').strip()
        admin_prenom = d.get('admin_prenom', '').strip()
        admin_pwd    = d.get('admin_password', '')

        db_exec("DELETE FROM utilisateurs WHERE username=?", (admin_login,))
        uid = db_exec(
            "INSERT INTO utilisateurs(username,password_hash,nom,prenom,agence,actif)"
            " VALUES(?,?,?,?,?,1)",
            (admin_login, hash_pwd(admin_pwd) if admin_pwd else '',
             admin_nom, admin_prenom, 'SIEGE'))
        if uid:
            set_all_permissions(uid, True)

        set_config('setup_done',    '1')
        set_config('setup_version', '2.0')
        log.info("Setup termine: %s", nom_societe)
        return jsonify({'ok': True, 'message': 'NEXORA configure pour ' + nom_societe})

    except Exception as e:
        log.error("Erreur setup: %s", e)
        return jsonify({'ok': False, 'message': str(e)})


@bp.route('/login', methods=['GET', 'POST'])
def login():
    cfg = {'nom_societe': get_config('nom_societe', '')}
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            return render_template('login.html', error='Saisissez un identifiant', config=cfg)
        ok, dest = process_login(username)
        if ok:
            return redirect(url_for('main.' + dest))
        return render_template('login.html', error='Utilisateur introuvable', config=cfg)
    return render_template('login.html', error='', config=cfg)


@bp.route('/logout')
def logout():
    u = session.get('username', '')
    session.clear()
    if u:
        audit(u, 'AUTH', 'LOGOUT', '', get_ip())
    return redirect(url_for('main.login'))


@bp.route('/accueil')
@login_required
def accueil():
    user    = get_user()
    modules = session.get('modules', [])
    cfg     = {
        'nom_societe':   get_config('nom_societe', ''),
        'sigle_societe': get_config('sigle_societe', ''),
        'devise':        get_config('devise', 'XAF'),
    }
    return render_template('accueil.html', user=user, modules=modules, config=cfg)


@bp.route('/acces-refuse')
def ip_bloquee():
    return '<h1>Acces refuse</h1><p>Votre IP n\'est pas autorisee.</p>', 403


# ── API Licence ──────────────────────────────────────────────────

@bp.route('/api/licence/statut')
@login_required
def api_licence_statut():
    mgr = get_licence_manager()
    if not mgr:
        return jsonify({'ok': False, 'erreur': 'Non initialise'})
    info = mgr.get_licence()
    if not info.valide and mgr.mode_demonstration():
        return jsonify({
            'ok': True, 'mode': 'DEMO',
            'jours_demo': mgr.jours_demo_restants(),
            'message':    'Mode demonstration - ' + str(mgr.jours_demo_restants()) + ' jours restants',
            'modules':    list(PERMISSIONS_TREE.keys()),
            'nb_postes':  1,
        })
    if not info.valide:
        return jsonify({'ok': False, 'mode': 'INVALIDE', 'erreur': info.erreur})
    return jsonify({
        'ok':             True,
        'mode':           'PERPETUELLE' if info.perpetuelle else 'ACTIVE',
        'nom_societe':    info.nom_societe,
        'modules':        info.modules,
        'modules_noms':   info.modules_noms,
        'nb_postes':      info.nb_postes,
        'date_expiration': str(info.date_expiration) if info.date_expiration else None,
        'perpetuelle':    info.perpetuelle,
        'jours_restants': info.jours_restants,
        'expire_bientot': info.expire_bientot,
        'reference':      info.reference,
    })


@bp.route('/api/licence/activer', methods=['POST'])
@login_required
def api_licence_activer():
    mgr = get_licence_manager()
    if not mgr:
        return jsonify({'ok': False, 'message': 'Non initialise'})
    d      = request.get_json() or {}
    numero = d.get('numero_serie', '').strip()
    if not numero:
        return jsonify({'ok': False, 'message': 'Numero de serie manquant'})
    info = mgr.activer(numero)
    if info.valide:
        audit(session.get('username', '?'), 'LICENCE', 'ACTIVATION',
              'societe=' + info.nom_societe)
        return jsonify({'ok': True, 'message': 'Licence activee pour ' + info.nom_societe,
                        'nom_societe': info.nom_societe, 'modules': info.modules})
    return jsonify({'ok': False, 'message': info.erreur})


@bp.route('/api/licence/verifier', methods=['POST'])
def api_licence_verifier():
    d      = request.get_json() or {}
    numero = d.get('numero_serie', '').strip()
    v      = NexoraLicenceVerifier()
    info   = v.verifier(numero)
    if info.valide:
        return jsonify({'ok': True, 'nom_societe': info.nom_societe,
                        'modules_noms': info.modules_noms, 'nb_postes': info.nb_postes,
                        'perpetuelle': info.perpetuelle,
                        'date_expiration': str(info.date_expiration) if info.date_expiration else None,
                        'jours_restants': info.jours_restants})
    return jsonify({'ok': False, 'message': info.erreur})


@bp.route('/api/licence/desactiver', methods=['POST'])
@login_required
def api_licence_desactiver():
    mgr = get_licence_manager()
    if mgr:
        mgr.desactiver()
    audit(session.get('username', '?'), 'LICENCE', 'DESACTIVATION', '')
    return jsonify({'ok': True})


@bp.route('/api/me')
@login_required
def api_me():
    return jsonify({'ok': True, 'user': get_user()})


@bp.route('/api/network-info')
@login_required
def api_network_info():
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'
    return jsonify({'ok': True, 'local_ip': local_ip, 'ip_publique': ''})
