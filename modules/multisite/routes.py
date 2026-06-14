from flask import render_template, request, jsonify, session, redirect, url_for
from . import bp
from core.database import (
    db_all, db_one, db_exec, db_scalar, has_permission, audit, next_numero,
    get_agence_locale,
)
from core.nexora_security import login_required
from core.sage_connector import get_stock_disponible, get_creances_clients, get_articles


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'multisite', sous_module, action)


def _est_siege():
    ag = get_agence_locale()
    return bool(ag and ag.get('type_site') == 'SIEGE')


@bp.route('/module/multisite')
@login_required
def module_multisite():
    uid = session['user_id']
    if not _peut(uid, 'gestion_agences', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/multisite.html', module='multisite',
                            module_label='🌐 Multi-Agences', est_siege=_est_siege())


# ── Tableau de bord ────────────────────────────────────────────────────────────
@bp.route('/api/multisite/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'gestion_agences', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    nb_agences = db_scalar("SELECT COUNT(*) FROM nx_agences WHERE actif=1") or 0
    dt_attente = db_scalar("SELECT COUNT(*) FROM nx_transferts WHERE statut='SOUMISE'") or 0
    dt_cours = db_scalar(
        "SELECT COUNT(*) FROM nx_transferts WHERE statut IN ('VALIDEE','EN_COURS')") or 0
    da_attente = db_scalar("SELECT COUNT(*) FROM nx_demandes_achat WHERE statut='SOUMISE'") or 0

    return jsonify(ok=True, summary={
        'nb_agences': nb_agences,
        'dt_attente': dt_attente,
        'dt_cours': dt_cours,
        'da_attente': da_attente,
        'est_siege': _est_siege(),
    })


# ── Gestion des agences ───────────────────────────────────────────────────────
@bp.route('/api/multisite/agences')
@login_required
def api_agences():
    uid = session['user_id']
    if not _peut(uid, 'gestion_agences', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=db_all("SELECT * FROM nx_agences ORDER BY id"))


@bp.route('/api/multisite/agences', methods=['POST'])
@login_required
def api_agence_creer():
    uid = session['user_id']
    if not _peut(uid, 'gestion_agences', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    code = d.get('code', '').strip().upper()
    nom = d.get('nom', '').strip()
    if not code or not nom:
        return jsonify(ok=False, msg='Code et nom requis')
    if db_one("SELECT id FROM nx_agences WHERE code=?", (code,)):
        return jsonify(ok=False, msg='Ce code agence existe deja')

    db_exec("""INSERT INTO nx_agences
        (code,nom,ville,adresse,telephone,type_site,depot_sage_no,actif)
        VALUES(?,?,?,?,?,?,?,1)""",
        (code, nom, d.get('ville', ''), d.get('adresse', ''), d.get('telephone', ''),
         d.get('type_site', 'AGENCE'), d.get('depot_sage_no') or None))
    audit(session['username'], 'multisite', 'CREER_AGENCE', 'Code=%s Nom=%s' % (code, nom))
    return jsonify(ok=True, msg='Agence %s creee' % nom)


@bp.route('/api/multisite/agences/<int:agence_id>', methods=['PUT'])
@login_required
def api_agence_modifier(agence_id):
    uid = session['user_id']
    if not _peut(uid, 'gestion_agences', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    ag = db_one("SELECT * FROM nx_agences WHERE id=?", (agence_id,))
    if not ag:
        return jsonify(ok=False, msg='Agence introuvable')

    d = request.json or {}
    db_exec("""UPDATE nx_agences SET nom=?, ville=?, adresse=?, telephone=?, type_site=?,
                depot_sage_no=?, actif=? WHERE id=?""",
            (d.get('nom', ag['nom']), d.get('ville', ag['ville']), d.get('adresse', ag['adresse']),
             d.get('telephone', ag['telephone']), d.get('type_site', ag['type_site']),
             d.get('depot_sage_no') if d.get('depot_sage_no') not in (None, '') else ag['depot_sage_no'],
             1 if d.get('actif', ag['actif']) else 0, agence_id))
    audit(session['username'], 'multisite', 'MODIFIER_AGENCE', 'ID=%s' % agence_id)
    return jsonify(ok=True, msg='Agence mise a jour')


# ── Permissions de visibilite ─────────────────────────────────────────────────
@bp.route('/api/multisite/permissions-visibilite')
@login_required
def api_permissions_visibilite():
    uid = session['user_id']
    if not _peut(uid, 'permissions_visibilite', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=db_all("SELECT * FROM nx_permissions_visibilite"))


@bp.route('/api/multisite/permissions-visibilite', methods=['POST'])
@login_required
def api_permissions_visibilite_set():
    uid = session['user_id']
    if not _peut(uid, 'permissions_visibilite', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    src = d.get('agence_source')
    cible = d.get('agence_cible')
    if not src or not cible:
        return jsonify(ok=False, msg='Agences source et cible requises')
    if int(src) == int(cible):
        return jsonify(ok=False, msg="L'agence cible doit etre differente de l'agence source")

    existe = db_one(
        "SELECT 1 FROM nx_permissions_visibilite WHERE agence_source=? AND agence_cible=?",
        (src, cible))
    vals = (1 if d.get('peut_voir_stock') else 0,
            1 if d.get('peut_voir_dt') else 0,
            1 if d.get('peut_voir_ventes') else 0,
            1 if d.get('peut_voir_creances') else 0)
    if existe:
        db_exec("""UPDATE nx_permissions_visibilite SET peut_voir_stock=?, peut_voir_dt=?,
                    peut_voir_ventes=?, peut_voir_creances=?
                    WHERE agence_source=? AND agence_cible=?""", vals + (src, cible))
    else:
        db_exec("""INSERT INTO nx_permissions_visibilite
                    (agence_source,agence_cible,peut_voir_stock,peut_voir_dt,peut_voir_ventes,peut_voir_creances)
                    VALUES(?,?,?,?,?,?)""", (src, cible) + vals)
    audit(session['username'], 'multisite', 'MAJ_VISIBILITE', 'src=%s cible=%s' % (src, cible))
    return jsonify(ok=True, msg='Permissions de visibilite mises a jour')


# ── Stock & creances consolides ───────────────────────────────────────────────
@bp.route('/api/multisite/stock-disponible')
@login_required
def api_stock_disponible():
    uid = session['user_id']
    if not _peut(uid, 'stock_consolide', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    q = request.args.get('q', '').strip().lower()

    agences = db_all(
        "SELECT id,code,nom,depot_sage_no FROM nx_agences "
        "WHERE actif=1 AND depot_sage_no IS NOT NULL")

    data = []
    for ag in agences:
        for r in get_stock_disponible(ag['depot_sage_no']):
            if q and q not in (str(r.get('code_article', '')) + str(r.get('designation', ''))).lower():
                continue
            r['agence_code'] = ag['code']
            r['agence_nom'] = ag['nom']
            data.append(r)

    return jsonify(ok=True, data=data)


@bp.route('/api/multisite/creances-consolidees')
@login_required
def api_creances_consolidees():
    uid = session['user_id']
    if not _peut(uid, 'stock_consolide', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=get_creances_clients())


# ── Recherche article (DT / DA) ───────────────────────────────────────────────
@bp.route('/api/multisite/articles')
@login_required
def api_multisite_articles():
    uid = session['user_id']
    if not (_peut(uid, 'transferts_dt', 'lire') or _peut(uid, 'demandes_achat', 'lire')):
        return jsonify(ok=False, msg='Acces refuse'), 403
    q = request.args.get('q', '')
    return jsonify(ok=True, data=get_articles(q, 30))


# ── Transferts inter-agences (DT) ─────────────────────────────────────────────
@bp.route('/api/multisite/transferts')
@login_required
def api_transferts():
    uid = session['user_id']
    if not _peut(uid, 'transferts_dt', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    statut = request.args.get('statut', '')

    sql = """SELECT t.*, s.nom AS agence_source_nom, c.nom AS agence_dest_nom
             FROM nx_transferts t
             LEFT JOIN nx_agences s ON s.id=t.agence_source_id
             LEFT JOIN nx_agences c ON c.id=t.agence_dest_id
             WHERE 1=1"""
    params = []
    if statut:
        sql += " AND t.statut=?"
        params.append(statut)
    sql += " ORDER BY t.id DESC"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/multisite/transferts/<int:tid>')
@login_required
def api_transfert_detail(tid):
    uid = session['user_id']
    if not _peut(uid, 'transferts_dt', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    t = db_one("""SELECT t.*, s.nom AS agence_source_nom, c.nom AS agence_dest_nom
                   FROM nx_transferts t
                   LEFT JOIN nx_agences s ON s.id=t.agence_source_id
                   LEFT JOIN nx_agences c ON c.id=t.agence_dest_id
                   WHERE t.id=?""", (tid,))
    if not t:
        return jsonify(ok=False, msg='Transfert introuvable')
    lignes = db_all("SELECT * FROM nx_transferts_lignes WHERE transfert_id=?", (tid,))
    return jsonify(ok=True, data=t, lignes=lignes)


@bp.route('/api/multisite/transferts', methods=['POST'])
@login_required
def api_transfert_creer():
    uid = session['user_id']
    if not _peut(uid, 'transferts_dt', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    src = d.get('agence_source_id')
    dest = d.get('agence_dest_id')
    lignes = d.get('lignes', [])
    if not src or not dest or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')
    if int(src) == int(dest):
        return jsonify(ok=False, msg="L'agence de destination doit etre differente de l'agence source")

    numero = next_numero('DT')
    valeur_totale = sum(
        float(l.get('quantite', 0) or 0) * float(l.get('prix_unitaire', 0) or 0)
        for l in lignes)

    tid = db_exec("""INSERT INTO nx_transferts
        (numero,agence_source_id,agence_dest_id,statut,urgence,demande_par,observations,nb_lignes,valeur_totale)
        VALUES(?,?,?,'SOUMISE',?,?,?,?,?)""",
        (numero, src, dest, 1 if d.get('urgence') else 0, session['username'],
         d.get('observations', ''), len(lignes), valeur_totale))

    for l in lignes:
        db_exec("""INSERT INTO nx_transferts_lignes
            (transfert_id,ar_ref,designation,unite,qte_demandee,prix_unitaire,stock_dispo_src)
            VALUES(?,?,?,?,?,?,?)""",
            (tid, l.get('code_article', ''), l.get('designation', ''), l.get('unite', 'Unite'),
             float(l.get('quantite', 0) or 0), float(l.get('prix_unitaire', 0) or 0),
             float(l.get('stock_dispo_src', 0) or 0)))

    audit(session['username'], 'multisite', 'CREER_DT',
          'N=%s %d article(s)' % (numero, len(lignes)))
    return jsonify(ok=True, msg='Transfert %s soumis - %d article(s)' % (numero, len(lignes)),
                    numero=numero)


@bp.route('/api/multisite/transferts/<int:tid>/valider', methods=['POST'])
@login_required
def api_transfert_valider(tid):
    uid = session['user_id']
    if not _peut(uid, 'transferts_dt', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    if not (session.get('is_master') or _est_siege()):
        return jsonify(ok=False, msg='Seul le siege peut valider les transferts')

    t = db_one("SELECT * FROM nx_transferts WHERE id=?", (tid,))
    if not t:
        return jsonify(ok=False, msg='Transfert introuvable')

    d = request.json or {}
    decision = d.get('decision', '')
    if decision == 'valider':
        db_exec("""UPDATE nx_transferts SET statut='VALIDEE', date_validation=datetime('now'),
                    valide_par=? WHERE id=?""", (session['username'], tid))
        msg = 'Transfert %s valide' % t['numero']
    elif decision == 'refuser':
        motif = d.get('motif_refus', '').strip()
        if not motif:
            return jsonify(ok=False, msg='Motif de refus obligatoire')
        db_exec("""UPDATE nx_transferts SET statut='REFUSEE', date_validation=datetime('now'),
                    valide_par=?, motif_refus=? WHERE id=?""", (session['username'], motif, tid))
        msg = 'Transfert %s refuse' % t['numero']
    elif decision == 'en_cours':
        db_exec("UPDATE nx_transferts SET statut='EN_COURS' WHERE id=?", (tid,))
        msg = 'Transfert %s marque en cours de livraison' % t['numero']
    elif decision == 'livrer':
        db_exec("UPDATE nx_transferts SET statut='LIVREE' WHERE id=?", (tid,))
        msg = 'Transfert %s marque comme livre' % t['numero']
    else:
        return jsonify(ok=False, msg='Decision invalide')

    audit(session['username'], 'multisite', 'VALIDER_DT', '%s -> %s' % (t['numero'], decision))
    return jsonify(ok=True, msg=msg)


# ── Demandes d'achat (DA) ──────────────────────────────────────────────────────
@bp.route('/api/multisite/demandes-achat')
@login_required
def api_demandes_achat():
    uid = session['user_id']
    if not _peut(uid, 'demandes_achat', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    statut = request.args.get('statut', '')

    sql = """SELECT d.*, a.nom AS agence_nom, l.nom AS livraison_nom
             FROM nx_demandes_achat d
             LEFT JOIN nx_agences a ON a.id=d.agence_id
             LEFT JOIN nx_agences l ON l.id=d.livraison_agence
             WHERE 1=1"""
    params = []
    if statut:
        sql += " AND d.statut=?"
        params.append(statut)
    sql += " ORDER BY d.id DESC"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/multisite/demandes-achat/<int:did>')
@login_required
def api_demande_achat_detail(did):
    uid = session['user_id']
    if not _peut(uid, 'demandes_achat', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d_ = db_one("""SELECT d.*, a.nom AS agence_nom, l.nom AS livraison_nom
                    FROM nx_demandes_achat d
                    LEFT JOIN nx_agences a ON a.id=d.agence_id
                    LEFT JOIN nx_agences l ON l.id=d.livraison_agence
                    WHERE d.id=?""", (did,))
    if not d_:
        return jsonify(ok=False, msg='Demande introuvable')
    lignes = db_all("SELECT * FROM nx_demandes_achat_lignes WHERE da_id=?", (did,))
    return jsonify(ok=True, data=d_, lignes=lignes)


@bp.route('/api/multisite/demandes-achat', methods=['POST'])
@login_required
def api_demande_achat_creer():
    uid = session['user_id']
    if not _peut(uid, 'demandes_achat', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    agence_id = d.get('agence_id')
    lignes = d.get('lignes', [])
    if not agence_id or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')

    numero = next_numero('DA')
    valeur_totale = sum(
        float(l.get('quantite', 0) or 0) * float(l.get('prix_unitaire', 0) or 0)
        for l in lignes)
    did = db_exec("""INSERT INTO nx_demandes_achat
        (numero,agence_id,fournisseur_code,fournisseur_nom,statut,urgence,
         livraison_agence,demande_par,observations,valeur_totale)
        VALUES(?,?,?,?,'SOUMISE',?,?,?,?,?)""",
        (numero, agence_id, d.get('fournisseur_code', ''), d.get('fournisseur_nom', ''),
         1 if d.get('urgence') else 0, d.get('livraison_agence') or agence_id,
         session['username'], d.get('observations', ''), valeur_totale))

    for l in lignes:
        db_exec("""INSERT INTO nx_demandes_achat_lignes
            (da_id,ar_ref,designation,unite,qte_demandee,prix_unitaire)
            VALUES(?,?,?,?,?,?)""",
            (did, l.get('code_article', ''), l.get('designation', ''), l.get('unite', 'Unite'),
             float(l.get('quantite', 0) or 0), float(l.get('prix_unitaire', 0) or 0)))

    audit(session['username'], 'multisite', 'CREER_DA',
          'N=%s %d article(s)' % (numero, len(lignes)))
    return jsonify(ok=True, msg='Demande %s soumise - %d article(s)' % (numero, len(lignes)),
                    numero=numero)


@bp.route('/api/multisite/demandes-achat/<int:did>/valider', methods=['POST'])
@login_required
def api_demande_achat_valider(did):
    uid = session['user_id']
    if not _peut(uid, 'demandes_achat', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    if not (session.get('is_master') or _est_siege()):
        return jsonify(ok=False, msg='Seul le siege peut valider les demandes d\'achat')

    da = db_one("SELECT * FROM nx_demandes_achat WHERE id=?", (did,))
    if not da:
        return jsonify(ok=False, msg='Demande introuvable')

    d = request.json or {}
    decision = d.get('decision', '')
    if decision == 'valider':
        db_exec("""UPDATE nx_demandes_achat SET statut='VALIDEE', date_validation=datetime('now'),
                    valide_par=? WHERE id=?""", (session['username'], did))
        msg = 'Demande %s validee' % da['numero']
    elif decision == 'refuser':
        motif = d.get('motif_refus', '').strip()
        if not motif:
            return jsonify(ok=False, msg='Motif de refus obligatoire')
        db_exec("""UPDATE nx_demandes_achat SET statut='REFUSEE', date_validation=datetime('now'),
                    valide_par=?, motif_refus=? WHERE id=?""", (session['username'], motif, did))
        msg = 'Demande %s refusee' % da['numero']
    elif decision == 'commander':
        bc = d.get('bc_numero', '').strip()
        db_exec("UPDATE nx_demandes_achat SET statut='COMMANDEE', bc_numero=? WHERE id=?",
                (bc, did))
        msg = 'Demande %s passee en commande (BC %s)' % (da['numero'], bc or '-')
    else:
        return jsonify(ok=False, msg='Decision invalide')

    audit(session['username'], 'multisite', 'VALIDER_DA', '%s -> %s' % (da['numero'], decision))
    return jsonify(ok=True, msg=msg)
