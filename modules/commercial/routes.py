#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/commercial/routes.py
NEXORA v2.0 — Module Commercial : fiches clients, objectifs commerciaux,
suivi des ventes, previsions de commandes et analyse du chiffre d'affaires.
"""
from datetime import date, timedelta

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit
from core.nexora_security import login_required
from core.sage_connector import get_ventes, get_creances_clients


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'commercial', sous_module, action)


def _creances_depassement():
    creances = get_creances_clients()
    if not creances:
        return 0.0
    plafonds = {f['code_client']: float(f['plafond_credit'] or 0)
                for f in db_all("SELECT code_client, plafond_credit FROM fiches_clients")}
    total = 0.0
    for c in creances:
        solde = float(c.get('solde') or 0)
        plafond = plafonds.get(c.get('code_client'), 0)
        if plafond > 0 and solde > plafond:
            total += (solde - plafond)
    return round(total, 2)


def _ca_par_periode(ventes, granularite):
    buckets = {}
    for v in ventes:
        d_str = str(v.get('date_facture') or '')[:10]
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if granularite == 'semaine':
            iso = d.isocalendar()
            cle = '%s-S%02d' % (iso[0], iso[1])
        elif granularite == 'mois':
            cle = d.strftime('%Y-%m')
        else:
            cle = d_str
        buckets[cle] = buckets.get(cle, 0.0) + float(v.get('montant_ttc') or 0)
    return [{'periode': k, 'ca': round(v, 2)} for k, v in sorted(buckets.items())]


def _top_clients(ventes, n=10):
    par_client = {}
    for v in ventes:
        cc = v.get('code_client')
        if not cc:
            continue
        if cc not in par_client:
            par_client[cc] = {'code_client': cc, 'client_nom': v.get('client_nom', ''), 'total': 0.0}
        par_client[cc]['total'] += float(v.get('montant_ttc') or 0)
    clients = sorted(par_client.values(), key=lambda c: c['total'], reverse=True)
    for c in clients:
        c['total'] = round(c['total'], 2)
    return clients[:n]


@bp.route('/module/commercial')
@login_required
def module_commercial():
    uid = session['user_id']
    if not _peut(uid, 'fiches_clients', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/commercial.html', module='commercial',
                            module_label='📊 Commercial')


# ── Tableau de bord ──────────────────────────────────────────────────────────
@bp.route('/api/commercial/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'fiches_clients', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    today = date.today().isoformat()
    debut_mois = date.today().replace(day=1).isoformat()

    ventes_jour = get_ventes(date_debut=today, date_fin=today)
    ventes_mois = get_ventes(date_debut=debut_mois, date_fin=today)
    ca_jour = sum(float(v.get('montant_ttc') or 0) for v in ventes_jour)
    ca_mois = sum(float(v.get('montant_ttc') or 0) for v in ventes_mois)

    clients_actifs = db_scalar("SELECT COUNT(*) FROM fiches_clients WHERE actif=1") or 0

    return jsonify(ok=True, summary={
        'ca_jour': round(ca_jour, 2),
        'ca_mois': round(ca_mois, 2),
        'clients_actifs': clients_actifs,
        'creances_depassement': _creances_depassement(),
    })


# ── Fiches clients ────────────────────────────────────────────────────────────
@bp.route('/api/commercial/clients', methods=['GET', 'POST'])
@login_required
def api_clients():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'fiches_clients', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        if not d.get('code_client') or not d.get('nom'):
            return jsonify(ok=False, msg='Code client et nom requis')
        if db_one("SELECT id FROM fiches_clients WHERE code_client=?", (d['code_client'],)):
            return jsonify(ok=False, msg='Ce code client existe deja')
        cid = db_exec("""INSERT INTO fiches_clients
            (code_client,nom,prenom,telephone,telephone2,email,adresse,ville,quartier,
             activite,secteur,commercial_attitre,plafond_credit,delai_paiement,observations)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.get('code_client', ''), d.get('nom', ''), d.get('prenom', ''), d.get('telephone', ''),
             d.get('telephone2', ''), d.get('email', ''), d.get('adresse', ''), d.get('ville', ''),
             d.get('quartier', ''), d.get('activite', ''), d.get('secteur', ''),
             d.get('commercial_attitre', ''), float(d.get('plafond_credit', 0) or 0),
             int(d.get('delai_paiement', 30) or 30), d.get('observations', '')))
        audit(session['username'], 'commercial', 'CREER_CLIENT', 'Client=%s' % d.get('code_client', ''))
        return jsonify(ok=True, msg='Client cree', id=cid)

    if not _peut(uid, 'fiches_clients', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    q = request.args.get('q', '').strip()
    sql = "SELECT * FROM fiches_clients WHERE 1=1"
    params = []
    if q:
        like = '%' + q + '%'
        sql += " AND (code_client LIKE ? OR nom LIKE ? OR telephone LIKE ?)"
        params += [like, like, like]
    sql += " ORDER BY nom"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/commercial/clients/<int:cid>', methods=['PUT'])
@login_required
def api_client_detail(cid):
    uid = session['user_id']
    if not _peut(uid, 'fiches_clients', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    r = db_one("SELECT id FROM fiches_clients WHERE id=?", (cid,))
    if not r:
        return jsonify(ok=False, msg='Client introuvable')
    d = request.json or {}
    db_exec("""UPDATE fiches_clients SET nom=?,prenom=?,telephone=?,telephone2=?,email=?,
        adresse=?,ville=?,quartier=?,activite=?,secteur=?,commercial_attitre=?,
        plafond_credit=?,delai_paiement=?,observations=?,actif=?,modifie_le=datetime('now')
        WHERE id=?""",
        (d.get('nom', ''), d.get('prenom', ''), d.get('telephone', ''), d.get('telephone2', ''),
         d.get('email', ''), d.get('adresse', ''), d.get('ville', ''), d.get('quartier', ''),
         d.get('activite', ''), d.get('secteur', ''), d.get('commercial_attitre', ''),
         float(d.get('plafond_credit', 0) or 0), int(d.get('delai_paiement', 30) or 30),
         d.get('observations', ''), 1 if d.get('actif', 1) else 0, cid))
    audit(session['username'], 'commercial', 'MAJ_CLIENT', 'Client id=%s' % cid)
    return jsonify(ok=True, msg='Client mis a jour')


# ── Objectifs commerciaux ─────────────────────────────────────────────────────
@bp.route('/api/commercial/objectifs', methods=['GET', 'POST'])
@login_required
def api_objectifs():
    uid = session['user_id']

    if request.method == 'POST':
        if not _peut(uid, 'objectifs', 'ecrire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
        d = request.json or {}
        if not d.get('commercial') or not d.get('periode'):
            return jsonify(ok=False, msg='Commercial et periode requis')
        db_exec("""INSERT INTO objectifs_commerciaux
            (commercial,periode,objectif_ca,objectif_recouvrement,objectif_nb_clients)
            VALUES(?,?,?,?,?)
            ON CONFLICT(commercial,periode) DO UPDATE SET
                objectif_ca=excluded.objectif_ca,
                objectif_recouvrement=excluded.objectif_recouvrement,
                objectif_nb_clients=excluded.objectif_nb_clients""",
            (d.get('commercial', ''), d.get('periode', ''),
             float(d.get('objectif_ca', 0) or 0), float(d.get('objectif_recouvrement', 0) or 0),
             int(d.get('objectif_nb_clients', 0) or 0)))
        audit(session['username'], 'commercial', 'MAJ_OBJECTIF',
              'Commercial=%s Periode=%s' % (d.get('commercial', ''), d.get('periode', '')))
        return jsonify(ok=True, msg='Objectif enregistre')

    if not _peut(uid, 'objectifs', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=db_all(
        "SELECT * FROM objectifs_commerciaux ORDER BY periode DESC, commercial"))


# ── Suivi des ventes ──────────────────────────────────────────────────────────
@bp.route('/api/commercial/ventes')
@login_required
def api_ventes():
    uid = session['user_id']
    if not _peut(uid, 'suivi_ventes', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=get_ventes(
        date_debut=request.args.get('date_debut', ''),
        date_fin=request.args.get('date_fin', ''),
        code_client=request.args.get('code_client', '')))


# ── Previsions de commandes ────────────────────────────────────────────────────
@bp.route('/api/commercial/previsions')
@login_required
def api_previsions():
    uid = session['user_id']
    if not _peut(uid, 'previsions', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    depuis = (date.today() - timedelta(days=365)).isoformat()
    ventes = get_ventes(date_debut=depuis)

    par_client = {}
    for v in ventes:
        cc = v.get('code_client')
        if not cc:
            continue
        d_str = str(v.get('date_facture') or '')[:10]
        if not d_str:
            continue
        par_client.setdefault(cc, {'nom': v.get('client_nom', ''), 'dates': []})
        par_client[cc]['dates'].append(d_str)

    today = date.today()
    previsions = []
    for cc, info in par_client.items():
        dates = sorted(set(info['dates']))
        nb_commandes = len(dates)
        if nb_commandes < 2:
            continue
        intervals = []
        for i in range(1, len(dates)):
            d1 = date.fromisoformat(dates[i - 1])
            d2 = date.fromisoformat(dates[i])
            intervals.append((d2 - d1).days)
        frequence_jours = round(sum(intervals) / len(intervals))
        if frequence_jours <= 0:
            continue
        derniere = date.fromisoformat(dates[-1])
        jours_restants = frequence_jours - (today - derniere).days
        previsions.append({
            'code_client': cc,
            'client_nom': info['nom'],
            'nb_commandes': nb_commandes,
            'frequence_jours': frequence_jours,
            'derniere_commande': dates[-1],
            'jours_restants': jours_restants,
        })

    previsions.sort(key=lambda p: p['jours_restants'])
    return jsonify(ok=True, data=previsions)


# ── Analyse du chiffre d'affaires ───────────────────────────────────────────────
@bp.route('/api/commercial/analyse-ca')
@login_required
def api_analyse_ca():
    uid = session['user_id']
    if not _peut(uid, 'analyse_commerc', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    granularite = request.args.get('granularite', 'jour')
    if granularite == 'semaine':
        nb_jours = 84
    elif granularite == 'mois':
        nb_jours = 365
    else:
        granularite = 'jour'
        nb_jours = 30

    fin = date.today()
    debut = fin - timedelta(days=nb_jours - 1)
    debut_n1 = debut - timedelta(days=365)
    fin_n1 = fin - timedelta(days=365)

    ventes = get_ventes(date_debut=debut.isoformat(), date_fin=fin.isoformat())
    ventes_n1 = get_ventes(date_debut=debut_n1.isoformat(), date_fin=fin_n1.isoformat())

    data = _ca_par_periode(ventes, granularite)
    data_n1 = _ca_par_periode(ventes_n1, granularite)

    ca_total = sum(p['ca'] for p in data)
    ca_total_n1 = sum(p['ca'] for p in data_n1)

    top_clients = _top_clients(ventes, 10)
    top_clients_n1 = _top_clients(ventes_n1, 10)
    top10_total = sum(c['total'] for c in top_clients)
    top10_total_n1 = sum(c['total'] for c in top_clients_n1)

    return jsonify(ok=True, granularite=granularite, data=data, data_n1=data_n1,
                    ca_total=round(ca_total, 2), ca_total_n1=round(ca_total_n1, 2),
                    top_clients=top_clients,
                    top10_progression=round(top10_total - top10_total_n1, 2))
