#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/rh/routes.py
NEXORA v2.0 — Module RH : fiches employes et suivi quotidien des presences.
"""
from datetime import date

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit
from core.nexora_security import login_required

STATUTS_PRESENCE = ('PRESENT', 'ABSENT', 'CONGE', 'MALADIE')


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'rh', sous_module, action)


@bp.route('/module/rh')
@login_required
def module_rh():
    uid = session['user_id']
    if not _peut(uid, 'fiches_employes', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/rh.html', module='rh',
                            module_label='👥 Ressources Humaines')


# ── Tableau de bord ──────────────────────────────────────────────────────────
@bp.route('/api/rh/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'fiches_employes', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    today = date.today().isoformat()
    mois = today[:7]

    effectif_actif = db_scalar("SELECT COUNT(*) FROM employes WHERE actif=1") or 0
    presents_jour = db_scalar(
        "SELECT COUNT(*) FROM presences WHERE date_presence=? AND statut='PRESENT'", (today,)) or 0
    absents_jour = db_scalar(
        "SELECT COUNT(*) FROM presences WHERE date_presence=? AND statut!='PRESENT'", (today,)) or 0
    masse_salariale = db_scalar("SELECT COALESCE(SUM(salaire_base),0) FROM employes WHERE actif=1") or 0
    recrutements_mois = db_scalar(
        "SELECT COUNT(*) FROM employes WHERE date_embauche LIKE ?", (mois + '%',)) or 0
    departs_mois = db_scalar(
        "SELECT COUNT(*) FROM employes WHERE date_depart LIKE ?", (mois + '%',)) or 0

    return jsonify(ok=True, summary={
        'effectif_actif': effectif_actif,
        'presents_jour': presents_jour,
        'absents_jour': absents_jour,
        'masse_salariale': round(float(masse_salariale), 2),
        'recrutements_mois': recrutements_mois,
        'departs_mois': departs_mois,
    })


# ── Fiches employés ────────────────────────────────────────────────────────────
@bp.route('/api/rh/employes', methods=['GET', 'POST'])
@login_required
def api_employes():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'fiches_employes', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        if not d.get('matricule') or not d.get('nom'):
            return jsonify(ok=False, msg='Matricule et nom requis')
        if db_one("SELECT id FROM employes WHERE matricule=?", (d['matricule'],)):
            return jsonify(ok=False, msg='Ce matricule existe deja')
        eid = db_exec("""INSERT INTO employes
            (matricule,nom,prenom,poste,departement,date_embauche,date_depart,
             salaire_base,telephone,email)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (d.get('matricule', ''), d.get('nom', ''), d.get('prenom', ''), d.get('poste', ''),
             d.get('departement', ''), d.get('date_embauche', ''), d.get('date_depart', ''),
             float(d.get('salaire_base', 0) or 0), d.get('telephone', ''), d.get('email', '')))
        audit(session['username'], 'rh', 'CREER_EMPLOYE', 'Matricule=%s' % d.get('matricule', ''))
        return jsonify(ok=True, msg='Employe cree', id=eid)

    if not _peut(uid, 'fiches_employes', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    q = request.args.get('q', '').strip()
    departement = request.args.get('departement', '').strip()
    sql = "SELECT * FROM employes WHERE 1=1"
    params = []
    if q:
        like = '%' + q + '%'
        sql += " AND (matricule LIKE ? OR nom LIKE ? OR prenom LIKE ?)"
        params += [like, like, like]
    if departement:
        sql += " AND departement=?"
        params.append(departement)
    sql += " ORDER BY nom, prenom"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/rh/employes/<int:eid>', methods=['PUT'])
@login_required
def api_employe_detail(eid):
    uid = session['user_id']
    if not _peut(uid, 'fiches_employes', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    if not db_one("SELECT id FROM employes WHERE id=?", (eid,)):
        return jsonify(ok=False, msg='Employe introuvable')
    d = request.json or {}
    db_exec("""UPDATE employes SET nom=?,prenom=?,poste=?,departement=?,date_embauche=?,
        date_depart=?,salaire_base=?,telephone=?,email=?,actif=? WHERE id=?""",
        (d.get('nom', ''), d.get('prenom', ''), d.get('poste', ''), d.get('departement', ''),
         d.get('date_embauche', ''), d.get('date_depart', ''),
         float(d.get('salaire_base', 0) or 0), d.get('telephone', ''), d.get('email', ''),
         1 if d.get('actif', 1) else 0, eid))
    audit(session['username'], 'rh', 'MAJ_EMPLOYE', 'Employe id=%s' % eid)
    return jsonify(ok=True, msg='Employe mis a jour')


@bp.route('/api/rh/departements')
@login_required
def api_departements():
    uid = session['user_id']
    if not _peut(uid, 'fiches_employes', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    rows = db_all(
        "SELECT DISTINCT departement FROM employes WHERE departement!='' "
        "AND departement IS NOT NULL ORDER BY departement")
    return jsonify(ok=True, data=[r['departement'] for r in rows])


# ── Présences ──────────────────────────────────────────────────────────────────
@bp.route('/api/rh/presences', methods=['GET', 'POST'])
@login_required
def api_presences():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'presences', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        date_presence = d.get('date_presence', '')
        lignes = d.get('lignes', [])
        if not date_presence:
            return jsonify(ok=False, msg='Date requise')
        for l in lignes:
            statut = l.get('statut', 'PRESENT')
            if statut not in STATUTS_PRESENCE:
                continue
            db_exec("""INSERT INTO presences (employe_id,date_presence,statut,observations)
                VALUES(?,?,?,?)
                ON CONFLICT(employe_id,date_presence) DO UPDATE SET
                    statut=excluded.statut, observations=excluded.observations""",
                (l.get('employe_id'), date_presence, statut, l.get('observations', '')))
        audit(session['username'], 'rh', 'SAISIE_PRESENCES', 'Date=%s' % date_presence)
        return jsonify(ok=True, msg='Presences enregistrees')

    if not _peut(uid, 'presences', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    date_presence = request.args.get('date', date.today().isoformat())
    departement = request.args.get('departement', '').strip()
    sql = """
        SELECT e.id AS employe_id, e.matricule, e.nom, e.prenom, e.poste, e.departement,
               p.statut, p.observations
        FROM employes e
        LEFT JOIN presences p ON p.employe_id=e.id AND p.date_presence=?
        WHERE e.actif=1
    """
    params = [date_presence]
    if departement:
        sql += " AND e.departement=?"
        params.append(departement)
    sql += " ORDER BY e.departement, e.nom, e.prenom"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/rh/presences/historique')
@login_required
def api_presences_historique():
    uid = session['user_id']
    if not _peut(uid, 'presences', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    departement = request.args.get('departement', '').strip()

    sql = """
        SELECT p.date_presence, p.statut, p.observations,
               e.matricule, e.nom, e.prenom, e.departement
        FROM presences p
        INNER JOIN employes e ON e.id=p.employe_id
        WHERE 1=1
    """
    params = []
    if date_debut:
        sql += " AND p.date_presence>=?"
        params.append(date_debut)
    if date_fin:
        sql += " AND p.date_presence<=?"
        params.append(date_fin)
    if departement:
        sql += " AND e.departement=?"
        params.append(departement)
    sql += " ORDER BY p.date_presence DESC, e.nom"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))
