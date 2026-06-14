#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/caisse/routes.py
NEXORA v2.0 — Module Caisse : saisie des rapports de caisse journaliers,
historique avec workflow de validation (brouillon -> soumis -> valide / rejete),
recap journalier et analyse du solde.
"""
from datetime import date, timedelta

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit
from core.nexora_security import login_required

STATUTS_VALIDES = ('brouillon', 'soumis', 'valide', 'rejete')


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'caisse', sous_module, action)


def _solde_periode(debut, fin):
    row = db_one(
        "SELECT COALESCE(SUM(total_encaisse),0) AS enc, COALESCE(SUM(depenses_caisse),0) AS dep "
        "FROM rapports_caisse WHERE date_rapport>=? AND date_rapport<=?", (debut, fin))
    return float(row['enc'] or 0) - float(row['dep'] or 0)


@bp.route('/module/caisse')
@login_required
def module_caisse():
    uid = session['user_id']
    if not _peut(uid, 'saisie_caisse', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/caisse.html', module='caisse',
                            module_label='🏪 Caisse')


# ── Tableau de bord ──────────────────────────────────────────────────────────
@bp.route('/api/caisse/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'recap_journalier', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    today = date.today().isoformat()
    rapports_jour = db_all(
        "SELECT total_encaisse, depenses_caisse FROM rapports_caisse WHERE date_rapport=?",
        (today,))
    encaisse_jour = sum(float(r['total_encaisse'] or 0) for r in rapports_jour)
    depenses_jour = sum(float(r['depenses_caisse'] or 0) for r in rapports_jour)
    solde_jour = encaisse_jour - depenses_jour

    debut_semaine = (date.today() - timedelta(days=6)).isoformat()
    debut_semaine_prec = (date.today() - timedelta(days=13)).isoformat()
    fin_semaine_prec = (date.today() - timedelta(days=7)).isoformat()
    solde_semaine = _solde_periode(debut_semaine, today)
    solde_semaine_prec = _solde_periode(debut_semaine_prec, fin_semaine_prec)

    debut_mois = date.today().replace(day=1)
    fin_mois_prec = debut_mois - timedelta(days=1)
    debut_mois_prec = fin_mois_prec.replace(day=1)
    solde_mois = _solde_periode(debut_mois.isoformat(), today)
    solde_mois_prec = _solde_periode(debut_mois_prec.isoformat(), fin_mois_prec.isoformat())

    rapports_en_attente = db_scalar(
        "SELECT COUNT(*) FROM rapports_caisse WHERE statut='soumis'") or 0

    return jsonify(ok=True, summary={
        'solde_jour': round(solde_jour, 2),
        'encaisse_jour': round(encaisse_jour, 2),
        'depenses_jour': round(depenses_jour, 2),
        'nb_rapports_jour': len(rapports_jour),
        'rapports_en_attente': rapports_en_attente,
        'solde_semaine': round(solde_semaine, 2),
        'solde_semaine_precedente': round(solde_semaine_prec, 2),
        'solde_mois': round(solde_mois, 2),
        'solde_mois_precedent': round(solde_mois_prec, 2),
    })


# ── Rapports : saisie + historique ───────────────────────────────────────────
@bp.route('/api/caisse/rapports', methods=['GET', 'POST'])
@login_required
def api_rapports():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'saisie_caisse', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        if not d.get('date_rapport') or not d.get('commercial'):
            return jsonify(ok=False, msg='Date et commercial requis')

        lignes = d.get('lignes', [])
        rid = db_exec("""INSERT INTO rapports_caisse
            (date_rapport,commercial,agence,total_ventes,total_encaisse,total_credit,
             depenses_caisse,observations,statut,saisi_par)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (d.get('date_rapport', ''), d.get('commercial', ''), d.get('agence', 'BERTOUA'),
             float(d.get('total_ventes', 0) or 0), float(d.get('total_encaisse', 0) or 0),
             float(d.get('total_credit', 0) or 0), float(d.get('depenses_caisse', 0) or 0),
             d.get('observations', ''), 'brouillon', session['username']))
        for l in lignes:
            db_exec("""INSERT INTO lignes_rapport_caisse
                (rapport_id,no_facture,code_client,client_nom,montant_facture,
                 montant_encaisse,mode_paiement,observations)
                VALUES(?,?,?,?,?,?,?,?)""",
                (rid, l.get('no_facture', ''), l.get('code_client', ''), l.get('client_nom', ''),
                 float(l.get('montant_facture', 0) or 0), float(l.get('montant_encaisse', 0) or 0),
                 l.get('mode_paiement', 'ESPECES'), l.get('observations', '')))
        audit(session['username'], 'caisse', 'CREER_RAPPORT_CAISSE',
              'Rapport=%s Date=%s' % (rid, d.get('date_rapport', '')))
        return jsonify(ok=True, msg='Rapport de caisse enregistre', id=rid)

    if not _peut(uid, 'historique_caisse', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    sql = "SELECT * FROM rapports_caisse WHERE 1=1"
    params = []
    statut = request.args.get('statut', '')
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    if statut:
        sql += " AND statut=?"
        params.append(statut)
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
        r['solde'] = round(float(r['total_encaisse'] or 0) - float(r['depenses_caisse'] or 0), 2)
    return jsonify(ok=True, data=rapports)


@bp.route('/api/caisse/rapports/<int:rid>/lignes')
@login_required
def api_rapport_lignes(rid):
    uid = session['user_id']
    if not _peut(uid, 'historique_caisse', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=db_all(
        "SELECT * FROM lignes_rapport_caisse WHERE rapport_id=?", (rid,)))


@bp.route('/api/caisse/rapports/<int:rid>', methods=['PUT'])
@login_required
def api_rapport_statut(rid):
    uid = session['user_id']
    if not _peut(uid, 'saisie_caisse', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    r = db_one("SELECT id, statut FROM rapports_caisse WHERE id=?", (rid,))
    if not r:
        return jsonify(ok=False, msg='Rapport introuvable')
    d = request.json or {}
    statut = d.get('statut', '')
    if statut not in STATUTS_VALIDES:
        return jsonify(ok=False, msg='Statut invalide')
    db_exec("UPDATE rapports_caisse SET statut=? WHERE id=?", (statut, rid))
    audit(session['username'], 'caisse', 'MAJ_STATUT_RAPPORT_CAISSE',
          'Rapport=%s %s->%s' % (rid, r['statut'], statut))
    return jsonify(ok=True, msg='Statut mis a jour')


# ── Recap journalier / analyse du solde ──────────────────────────────────────
@bp.route('/api/caisse/evolution-solde')
@login_required
def api_evolution_solde():
    uid = session['user_id']
    if not _peut(uid, 'recap_journalier', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    jours = int(request.args.get('jours', 30) or 30)
    depuis = (date.today() - timedelta(days=jours)).isoformat()
    rows = db_all(
        "SELECT date_rapport, COALESCE(SUM(total_encaisse),0) AS encaisse, "
        "COALESCE(SUM(depenses_caisse),0) AS depenses "
        "FROM rapports_caisse WHERE date_rapport>=? "
        "GROUP BY date_rapport ORDER BY date_rapport", (depuis,))

    cumul = 0.0
    jour_fort = None
    jour_faible = None
    for r in rows:
        solde = float(r['encaisse'] or 0) - float(r['depenses'] or 0)
        cumul += solde
        r['solde'] = round(solde, 2)
        r['cumul'] = round(cumul, 2)
        if jour_fort is None or solde > jour_fort['solde']:
            jour_fort = r
        if jour_faible is None or solde < jour_faible['solde']:
            jour_faible = r

    return jsonify(ok=True, data=rows, jour_fort=jour_fort, jour_faible=jour_faible)
