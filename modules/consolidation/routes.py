#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/consolidation/routes.py
NEXORA v2.0 — Module Consolidation : vue globale du reseau (CA consolide multi-agences).
"""
from datetime import date, timedelta

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import db_all, has_permission
from core.nexora_security import login_required
from core.sage_connector import get_ca_par_depot


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'consolidation', sous_module, action)


def _bornes_periode(granularite):
    today = date.today()
    if granularite == 'jour':
        return today.isoformat(), today.isoformat()
    if granularite == 'semaine':
        debut = today - timedelta(days=today.weekday())
        return debut.isoformat(), today.isoformat()
    if granularite == 'mois_precedent':
        premier_jour_mois = today.replace(day=1)
        dernier_jour_precedent = premier_jour_mois - timedelta(days=1)
        premier_jour_precedent = dernier_jour_precedent.replace(day=1)
        return premier_jour_precedent.isoformat(), dernier_jour_precedent.isoformat()
    # 'mois' par defaut
    debut = today.replace(day=1)
    return debut.isoformat(), today.isoformat()


def _decaler_n1(date_debut, date_fin):
    d1 = date.fromisoformat(date_debut) - timedelta(days=365)
    d2 = date.fromisoformat(date_fin) - timedelta(days=365)
    return d1.isoformat(), d2.isoformat()


@bp.route('/module/consolidation')
@login_required
def module_consolidation():
    uid = session['user_id']
    if not _peut(uid, 'synthese_groupe', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/consolidation.html', module='consolidation',
                            module_label='🧮 Consolidation')


# ── Vue globale reseau ────────────────────────────────────────────────────────
@bp.route('/api/consolidation/dashboard')
@login_required
def api_dashboard():
    uid = session['user_id']
    if not _peut(uid, 'synthese_groupe', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    granularite = request.args.get('granularite', 'mois')
    date_debut, date_fin = _bornes_periode(granularite)
    date_debut_n1, date_fin_n1 = _decaler_n1(date_debut, date_fin)

    ca_depots = get_ca_par_depot(date_debut, date_fin)
    ca_depots_n1 = get_ca_par_depot(date_debut_n1, date_fin_n1)

    agences = db_all(
        "SELECT id, code, nom, ville, type_site, depot_sage_no FROM nx_agences "
        "WHERE actif=1 ORDER BY id")

    data = []
    total_ca = 0.0
    total_ca_n1 = 0.0
    for ag in agences:
        depot_no = ag['depot_sage_no']
        ca = sum(float(d.get('ca_ht') or 0) for d in ca_depots if d.get('depot_no') == depot_no) \
            if depot_no else 0.0
        ca_n1 = sum(float(d.get('ca_ht') or 0) for d in ca_depots_n1 if d.get('depot_no') == depot_no) \
            if depot_no else 0.0
        total_ca += ca
        total_ca_n1 += ca_n1
        data.append({
            'agence_id': ag['id'],
            'code': ag['code'],
            'nom': ag['nom'],
            'ville': ag['ville'],
            'type_site': ag['type_site'],
            'ca': round(ca, 2),
            'ca_n1': round(ca_n1, 2),
        })

    for d in data:
        d['pct_contribution'] = round(d['ca'] / total_ca * 100, 2) if total_ca > 0 else 0.0
        d['variation_pct'] = round((d['ca'] - d['ca_n1']) / d['ca_n1'] * 100, 2) if d['ca_n1'] > 0 else 0.0

    variation_globale = round((total_ca - total_ca_n1) / total_ca_n1 * 100, 2) if total_ca_n1 > 0 else 0.0

    return jsonify(ok=True, data=data,
                    ca_total=round(total_ca, 2),
                    ca_total_n1=round(total_ca_n1, 2),
                    variation_pct=variation_globale,
                    periode={'debut': date_debut, 'fin': date_fin,
                             'debut_n1': date_debut_n1, 'fin_n1': date_fin_n1})
