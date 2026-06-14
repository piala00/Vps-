#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/comptabilite/routes.py
NEXORA v2.0 — Module Comptabilite : balance agee creances, grand livre clients,
suivi des paiements, evolution des creances, rapport de caisse.
"""
from datetime import date, timedelta

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit
from core.nexora_security import login_required
from core.sage_connector import (
    get_creances_clients, get_grand_livre_client, get_paiements_clients,
)


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'comptabilite', sous_module, action)


def _niveau_risque(solde):
    solde = float(solde or 0)
    if solde > 500000:
        return 'CRITIQUE'
    if solde > 200000:
        return 'ELEVE'
    if solde > 50000:
        return 'MOYEN'
    return 'FAIBLE'


def _creances_avec_risque():
    creances = get_creances_clients()
    for c in creances:
        c['niveau_risque'] = _niveau_risque(c.get('solde'))
    return creances


def _snapshot_creances(creances, total, periode):
    existing = db_scalar(
        "SELECT id FROM nx_bi_snapshots WHERE module='comptabilite' "
        "AND indicateur='creances_total' AND periode=?", (periode,))
    if not existing:
        db_exec("INSERT INTO nx_bi_snapshots (module,indicateur,periode,valeur) "
                "VALUES('comptabilite','creances_total',?,?)", (periode, total))
    for c in creances:
        code = c.get('code_client')
        if not code:
            continue
        ind = 'creances_client_' + str(code)
        ex = db_scalar(
            "SELECT id FROM nx_bi_snapshots WHERE module='comptabilite' "
            "AND indicateur=? AND periode=?", (ind, periode))
        if not ex:
            db_exec("INSERT INTO nx_bi_snapshots (module,indicateur,periode,valeur) "
                    "VALUES('comptabilite',?,?,?)", (ind, periode, float(c.get('solde') or 0)))


@bp.route('/module/comptabilite')
@login_required
def module_comptabilite():
    uid = session['user_id']
    if not _peut(uid, 'balance_agee', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/comptabilite.html', module='comptabilite',
                            module_label='💰 Comptabilite')


# ── Tableau de bord ──────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'balance_agee', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    creances = _creances_avec_risque()
    creances_totales = sum(float(c.get('solde') or 0) for c in creances)
    creances_critiques = sum(float(c.get('solde') or 0) for c in creances
                              if c['niveau_risque'] == 'CRITIQUE')
    creances_elevees = sum(float(c.get('solde') or 0) for c in creances
                            if c['niveau_risque'] == 'ELEVE')

    today = date.today().isoformat()
    _snapshot_creances(creances, creances_totales, today)

    hier = (date.today() - timedelta(days=1)).isoformat()
    valeur_hier = db_scalar(
        "SELECT valeur FROM nx_bi_snapshots WHERE module='comptabilite' "
        "AND indicateur='creances_total' AND periode=?", (hier,))
    tendance = 'stable'
    if valeur_hier is not None:
        if creances_totales > float(valeur_hier) + 0.01:
            tendance = 'hausse'
        elif creances_totales < float(valeur_hier) - 0.01:
            tendance = 'baisse'

    rapports_brouillon = db_scalar(
        "SELECT COUNT(*) FROM rapports_caisse WHERE statut='brouillon'") or 0

    encaisse_mois = db_scalar(
        "SELECT COALESCE(SUM(total_encaisse),0) FROM rapports_caisse "
        "WHERE strftime('%Y-%m', date_rapport)=strftime('%Y-%m','now')") or 0

    return jsonify(ok=True, summary={
        'creances_totales': round(creances_totales, 2),
        'nb_clients_debiteurs': len(creances),
        'creances_critiques': round(creances_critiques, 2),
        'creances_elevees': round(creances_elevees, 2),
        'tendance': tendance,
        'rapports_brouillon': rapports_brouillon,
        'encaisse_mois': round(float(encaisse_mois), 2),
    })


# ── Balance agee ──────────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/balance-agee')
@login_required
def api_balance_agee():
    uid = session['user_id']
    if not _peut(uid, 'balance_agee', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=_creances_avec_risque())


# ── Grand livre client ────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/grand-livre-client')
@login_required
def api_grand_livre_client():
    uid = session['user_id']
    if not _peut(uid, 'grand_livre', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    code_client = request.args.get('code_client', '')
    if not code_client:
        return jsonify(ok=False, msg='code_client requis')
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    return jsonify(ok=True, data=get_grand_livre_client(code_client, date_debut, date_fin))


# ── Suivi paiements ───────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/paiements')
@login_required
def api_paiements():
    uid = session['user_id']
    if not _peut(uid, 'suivi_paiements', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    code_client = request.args.get('code_client', '')
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    return jsonify(ok=True, data=get_paiements_clients(code_client, date_debut, date_fin))


# ── Evolution creances ────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/evolution-creances')
@login_required
def api_evolution_creances():
    uid = session['user_id']
    if not _peut(uid, 'recouvrement', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    creances = _creances_avec_risque()
    creances_totales = sum(float(c.get('solde') or 0) for c in creances)
    today = date.today().isoformat()
    _snapshot_creances(creances, creances_totales, today)

    code_client = request.args.get('code_client', '')
    jours = int(request.args.get('jours', 30) or 30)
    indicateur = ('creances_client_' + code_client) if code_client else 'creances_total'
    depuis = (date.today() - timedelta(days=jours)).isoformat()

    rows = db_all(
        "SELECT periode, valeur FROM nx_bi_snapshots "
        "WHERE module='comptabilite' AND indicateur=? AND periode>=? "
        "ORDER BY periode", (indicateur, depuis))

    return jsonify(ok=True, data=rows, clients=[
        {'code_client': c.get('code_client'), 'nom': c.get('nom')} for c in creances])


# ── Rapport de caisse ─────────────────────────────────────────────────────────
@bp.route('/api/comptabilite/rapport-caisse', methods=['GET', 'POST'])
@login_required
def api_rapport_caisse():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'rapport_caisse', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        lignes = d.get('lignes', [])
        rid = db_exec("""INSERT INTO rapports_caisse
            (date_rapport,commercial,agence,total_ventes,total_encaisse,total_credit,
             observations,statut,saisi_par)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (d.get('date_rapport', ''), d.get('commercial', ''), d.get('agence', 'BERTOUA'),
             float(d.get('total_ventes', 0) or 0), float(d.get('total_encaisse', 0) or 0),
             float(d.get('total_credit', 0) or 0), d.get('observations', ''),
             'brouillon', session['username']))
        for l in lignes:
            db_exec("""INSERT INTO lignes_rapport_caisse
                (rapport_id,no_facture,code_client,client_nom,montant_facture,
                 montant_encaisse,mode_paiement,observations)
                VALUES(?,?,?,?,?,?,?,?)""",
                (rid, l.get('no_facture', ''), l.get('code_client', ''), l.get('client_nom', ''),
                 float(l.get('montant_facture', 0) or 0), float(l.get('montant_encaisse', 0) or 0),
                 l.get('mode_paiement', 'ESPECES'), l.get('observations', '')))
        audit(session['username'], 'comptabilite', 'CREER_RAPPORT_CAISSE',
              'Rapport=%s Date=%s' % (rid, d.get('date_rapport', '')))
        return jsonify(ok=True, msg='Rapport de caisse enregistre', id=rid)

    if not _peut(uid, 'rapport_caisse', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    sql = "SELECT * FROM rapports_caisse WHERE 1=1"
    params = []
    if date_debut:
        sql += " AND date_rapport>=?"
        params.append(date_debut)
    if date_fin:
        sql += " AND date_rapport<=?"
        params.append(date_fin)
    sql += " ORDER BY date_rapport DESC, id DESC"
    rapports = db_all(sql, tuple(params))
    for r in rapports:
        r['nb_lignes'] = db_scalar(
            "SELECT COUNT(*) FROM lignes_rapport_caisse WHERE rapport_id=?", (r['id'],)) or 0
    return jsonify(ok=True, data=rapports)


@bp.route('/api/comptabilite/rapport-caisse/<int:rid>/lignes')
@login_required
def api_rapport_caisse_lignes(rid):
    uid = session['user_id']
    if not _peut(uid, 'rapport_caisse', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    lignes = db_all("SELECT * FROM lignes_rapport_caisse WHERE rapport_id=?", (rid,))
    return jsonify(ok=True, data=lignes)


@bp.route('/api/comptabilite/rapport-caisse/<int:rid>', methods=['PUT'])
@login_required
def api_rapport_caisse_valider(rid):
    uid = session['user_id']
    if not _peut(uid, 'rapport_caisse', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    r = db_one("SELECT id FROM rapports_caisse WHERE id=?", (rid,))
    if not r:
        return jsonify(ok=False, msg='Rapport introuvable')
    d = request.json or {}
    statut = d.get('statut', 'valide')
    db_exec("UPDATE rapports_caisse SET statut=? WHERE id=?", (statut, rid))
    audit(session['username'], 'comptabilite', 'MAJ_STATUT_RAPPORT_CAISSE',
          'Rapport=%s Statut=%s' % (rid, statut))
    return jsonify(ok=True, msg='Rapport mis a jour')
