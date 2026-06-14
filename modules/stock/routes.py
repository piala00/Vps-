#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/stock/routes.py
NEXORA v2.0 — Module Stock : fiches BL Sage / bordereau manuel / reception /
transfert, rapprochements, documents non regularises, equilibre inter-magasins
et analyses BI.
"""
from datetime import date

from flask import render_template, session, redirect, url_for, request, jsonify

from . import bp
from . import analyses_engine as eng
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit
from core.nexora_security import login_required
from core.sage_connector import (
    reconstituer_bl, get_mouvements, get_stock_disponible, get_articles,
    get_alertes_stock,
)


def _peut(uid, sous_module, action="lire"):
    return session.get("is_master") or has_permission(uid, "stock", sous_module, action)


@bp.route('/module/stock')
@login_required
def module_stock():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/stock.html', module='stock',
                            module_label='📦 Gestion Stock')


# ── Tableau de bord ──────────────────────────────────────────────────────────
@bp.route('/api/stock/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    alertes = get_alertes_stock()
    ruptures = sum(1 for a in alertes if a.get('alerte') == 'RUPTURE')
    critiques = sum(1 for a in alertes if a.get('alerte') == 'CRITIQUE')

    valeur_stock = sum(float(s.get('valeur_stock') or 0) for s in get_stock_disponible())

    mvts_jour = db_scalar(
        "SELECT COUNT(*) FROM mouvements_stock WHERE date(cree_le)=date('now')") or 0

    dormants_count = 0
    if _peut(uid, 'analyses_dormants', 'lire'):
        mvts = get_mouvements('3mois')
        dormants_count = len(eng.stocks_dormants(mvts, 60))

    docs_non_reg = db_scalar(
        "SELECT COUNT(DISTINCT no_doc_manuel) FROM mouvements_stock "
        "WHERE regularise=0 AND no_doc_manuel <> ''") or 0

    return jsonify(ok=True, summary={
        'ruptures': ruptures,
        'critiques': critiques,
        'valeur_stock': round(valeur_stock, 2),
        'mouvements_jour': mvts_jour,
        'dormants_count': dormants_count,
        'docs_non_regularises': docs_non_reg,
    })


# ── Recherche articles (Sage) ────────────────────────────────────────────────
@bp.route('/api/stock/articles')
@login_required
def api_articles():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    q = request.args.get('q', '')
    return jsonify(ok=True, data=get_articles(q, 30))


# ── BL Sage ───────────────────────────────────────────────────────────────────
@bp.route('/api/stock/reconstituer-bl', methods=['POST'])
@login_required
def api_reconstituer_bl():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    no_bl = (request.json or {}).get('no_bl', '').strip().upper()
    if not no_bl:
        return jsonify(ok=False, msg='Numero BL requis')
    cached = db_all("SELECT * FROM cache_bl WHERE no_bl=? ORDER BY code_article", (no_bl,))
    if cached:
        return jsonify(ok=True, source='cache', no_bl=no_bl, lignes=cached)
    ok, msg, lignes = reconstituer_bl(no_bl)
    if not ok:
        return jsonify(ok=False, msg=msg)
    return jsonify(ok=True, source='sage', no_bl=no_bl, lignes=lignes)


@bp.route('/api/stock/valider-bl', methods=['POST'])
@login_required
def api_valider_bl():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    no_bl = d.get('no_bl', '').strip().upper()
    lignes = d.get('lignes', [])
    if not no_bl or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')

    agence = session.get('agence', 'BERTOUA')
    ok_count = 0
    ecarts = 0
    for l in lignes:
        code = l.get('code_article', '')
        qte_sage = float(l.get('qte_sage', 0) or 0)
        qte_saisie = float(l.get('qte_saisie', 0) or 0)
        ecart = qte_sage - qte_saisie
        statut = 'valide' if abs(ecart) < 0.01 else 'ecart'
        if abs(ecart) > 0.01:
            ecarts += 1
        db_exec("DELETE FROM mouvements_stock WHERE no_doc_sage=? AND code_article=? "
                "AND type_mouvement='SORTIE_BL'", (no_bl, code))
        db_exec("""INSERT INTO mouvements_stock
            (type_mouvement,no_doc_sage,date_mvt,depot,code_article,designation,
             qte_saisie,qte_doc_sage,ecart,statut,regularise,regularise_le,
             saisi_par,agence,cree_le)
            VALUES('SORTIE_BL',?,?,?,?,?,?,?,?,?,1,datetime('now'),?,?,datetime('now'))""",
            (no_bl, l.get('date_bl', date.today().isoformat()), agence, code,
             l.get('designation', ''), qte_saisie, qte_sage, ecart, statut,
             session['username'], agence))
        ok_count += 1

    audit(session['username'], 'stock', 'VALIDER_BL',
          'BL=%s %d art %d ecart(s)' % (no_bl, ok_count, ecarts))
    return jsonify(ok=True,
                    msg='BL %s valide - %d article(s), %d ecart(s)' % (no_bl, ok_count, ecarts),
                    ecarts=ecarts)


# ── Bordereau manuel ──────────────────────────────────────────────────────────
@bp.route('/api/stock/saisir-manuel', methods=['POST'])
@login_required
def api_saisir_manuel():
    uid = session['user_id']
    if not _peut(uid, 'fiche_manuel', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    no_manuel = d.get('no_manuel', '').strip()
    type_mvt = d.get('type_mouvement', 'SORTIE_MANUEL')
    lignes = d.get('lignes', [])
    if not no_manuel or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')

    agence = session.get('agence', 'BERTOUA')
    date_mvt = d.get('date_mvt', date.today().isoformat())
    for l in lignes:
        db_exec("""INSERT INTO mouvements_stock
            (type_mouvement,no_doc_manuel,date_mvt,depot,
             code_article,designation,qte_saisie,qte_doc_sage,ecart,
             code_client,client_nom,statut,regularise,saisi_par,agence,cree_le)
            VALUES(?,?,?,?,?,?,?,0,0,?,?,'en_attente',0,?,?,datetime('now'))""",
            (type_mvt, no_manuel, date_mvt, agence,
             l.get('code_article', ''), l.get('designation', ''),
             float(l.get('quantite', 0) or 0),
             d.get('code_client', ''), d.get('client_nom', ''),
             session['username'], agence))

    audit(session['username'], 'stock', 'SAISIE_MANUEL',
          'N=%s type=%s' % (no_manuel, type_mvt))
    return jsonify(ok=True,
                    msg='Bordereau %s enregistre - %d article(s)' % (no_manuel, len(lignes)))


@bp.route('/api/stock/regulariser-manuel', methods=['POST'])
@login_required
def api_regulariser_manuel():
    """Lie un bordereau manuel a son N de BL Sage correspondant."""
    uid = session['user_id']
    if not _peut(uid, 'fiche_manuel', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    no_manuel = d.get('no_manuel', '').strip()
    no_sage = d.get('no_sage', '').strip().upper()
    if not no_manuel or not no_sage:
        return jsonify(ok=False, msg='N manuel et N Sage requis')

    ok, msg, lignes_sage = reconstituer_bl(no_sage)
    if not ok:
        return jsonify(ok=False, msg="BL Sage '%s': %s" % (no_sage, msg))

    lignes_manuel = db_all(
        "SELECT * FROM mouvements_stock WHERE no_doc_manuel=? AND regularise=0", (no_manuel,))
    if not lignes_manuel:
        return jsonify(ok=False, msg='Bordereau manuel introuvable ou deja regularise')

    qtes_sage = {}
    for l in lignes_sage:
        qtes_sage[l.get('code_article')] = float(l.get('quantite') or 0)

    ecarts = []
    ok_count = 0
    for lm in lignes_manuel:
        code = lm['code_article']
        qte_saisie = float(lm.get('qte_saisie') or 0)
        qte_sage = qtes_sage.get(code, 0)
        ecart = qte_sage - qte_saisie
        statut = 'valide' if abs(ecart) < 0.01 else 'ecart'
        if abs(ecart) > 0.01:
            ecarts.append({'code': code, 'ecart': ecart})
        db_exec("""UPDATE mouvements_stock SET
            no_doc_sage=?, qte_doc_sage=?, ecart=?, statut=?,
            regularise=1, regularise_le=datetime('now'), no_sage_lie=?
            WHERE id=?""",
            (no_sage, qte_sage, ecart, statut, no_sage, lm['id']))
        ok_count += 1

    audit(session['username'], 'stock', 'REGULARISER_MANUEL',
          'Manuel=%s Sage=%s' % (no_manuel, no_sage))
    return jsonify(ok=True,
                    msg='Regularisation effectuee - %d article(s)' % ok_count,
                    ecarts=ecarts, nb_ecarts=len(ecarts))


# ── Reception fournisseur ─────────────────────────────────────────────────────
@bp.route('/api/stock/reception', methods=['POST'])
@login_required
def api_reception():
    uid = session['user_id']
    if not _peut(uid, 'fiche_reception', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    no_reception = d.get('no_reception', '').strip()
    lignes = d.get('lignes', [])
    if not no_reception or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')

    agence = session.get('agence', 'BERTOUA')
    date_mvt = d.get('date_mvt', date.today().isoformat())
    for l in lignes:
        db_exec("""INSERT INTO mouvements_stock
            (type_mouvement,no_doc_manuel,date_mvt,depot,
             code_article,designation,qte_saisie,qte_doc_sage,ecart,
             code_fournisseur,fournisseur_nom,statut,regularise,saisi_par,agence,cree_le)
            VALUES('ENTREE_RECEPTION',?,?,?,?,?,?,0,0,?,?,'valide',1,?,?,datetime('now'))""",
            (no_reception, date_mvt, agence,
             l.get('code_article', ''), l.get('designation', ''),
             float(l.get('quantite', 0) or 0),
             d.get('code_fournisseur', ''), d.get('fournisseur_nom', ''),
             session['username'], agence))

    audit(session['username'], 'stock', 'RECEPTION',
          'N=%s %d article(s)' % (no_reception, len(lignes)))
    return jsonify(ok=True,
                    msg='Reception %s enregistree - %d article(s)' % (no_reception, len(lignes)))


# ── Transfert inter-depot ──────────────────────────────────────────────────────
@bp.route('/api/stock/transfert', methods=['POST'])
@login_required
def api_transfert():
    uid = session['user_id']
    if not _peut(uid, 'fiche_transfert', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    no_transfert = d.get('no_transfert', '').strip()
    depot = d.get('depot', '').strip()
    depot_dest = d.get('depot_dest', '').strip()
    lignes = d.get('lignes', [])
    if not no_transfert or not depot or not depot_dest or not lignes:
        return jsonify(ok=False, msg='Donnees incompletes')
    if depot == depot_dest:
        return jsonify(ok=False, msg='Le depot de destination doit etre different du depot source')

    date_mvt = d.get('date_mvt', date.today().isoformat())
    for l in lignes:
        db_exec("""INSERT INTO mouvements_stock
            (type_mouvement,no_doc_manuel,date_mvt,depot,depot_dest,
             code_article,designation,qte_saisie,qte_doc_sage,ecart,
             statut,regularise,saisi_par,agence,cree_le)
            VALUES('TRANSFERT',?,?,?,?,?,?,?,0,0,'valide',1,?,?,datetime('now'))""",
            (no_transfert, date_mvt, depot, depot_dest,
             l.get('code_article', ''), l.get('designation', ''),
             float(l.get('quantite', 0) or 0),
             session['username'], depot))

    audit(session['username'], 'stock', 'TRANSFERT',
          'N=%s %s -> %s %d article(s)' % (no_transfert, depot, depot_dest, len(lignes)))
    return jsonify(ok=True,
                    msg='Transfert %s enregistre - %d article(s)' % (no_transfert, len(lignes)))


# ── Historique ────────────────────────────────────────────────────────────────
@bp.route('/api/stock/historique')
@login_required
def api_stock_historique():
    uid = session['user_id']
    if not _peut(uid, 'fiche_bl_sage', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    type_mvt = request.args.get('type', '')
    code = request.args.get('code', '')
    no_doc = request.args.get('no_doc', '')
    statut = request.args.get('statut', '')
    limit = int(request.args.get('limit', 100))

    sql = "SELECT * FROM mouvements_stock WHERE 1=1"
    params = []
    if type_mvt:
        sql += " AND type_mouvement=?"
        params.append(type_mvt)
    if code:
        sql += " AND code_article LIKE ?"
        params.append('%' + code + '%')
    if no_doc:
        sql += " AND (no_doc_sage LIKE ? OR no_doc_manuel LIKE ?)"
        params += ['%' + no_doc + '%'] * 2
    if statut:
        sql += " AND statut=?"
        params.append(statut)
    sql += " ORDER BY cree_le DESC LIMIT ?"
    params.append(limit)
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


# ── Rapprochement ────────────────────────────────────────────────────────────
@bp.route('/api/stock/rapprochement')
@login_required
def api_rapprochement():
    uid = session['user_id']
    if not _peut(uid, 'rapprochement_bl', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    type_mvt = request.args.get('type', 'SORTIE_BL')
    date_deb = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    statut = request.args.get('statut', '')

    sql = """SELECT no_doc_sage,no_doc_manuel,date_mvt,
                    MAX(client_nom) AS client_nom,
                    COUNT(code_article) AS nb_articles,
                    SUM(qte_doc_sage) AS total_sage,
                    SUM(qte_saisie) AS total_saisi,
                    SUM(ABS(ecart)) AS total_ecart,
                    SUM(CASE WHEN ABS(ecart)>0.01 THEN 1 ELSE 0 END) AS nb_ecarts,
                    MAX(statut) AS statut_global,
                    MAX(saisi_par) AS saisi_par,
                    MAX(cree_le) AS valide_le
             FROM mouvements_stock WHERE type_mouvement=?"""
    params = [type_mvt]
    if date_deb:
        sql += " AND date_mvt>=?"
        params.append(date_deb)
    if date_fin:
        sql += " AND date_mvt<=?"
        params.append(date_fin)
    if statut:
        sql += " AND statut=?"
        params.append(statut)
    sql += " GROUP BY no_doc_sage,no_doc_manuel,date_mvt ORDER BY valide_le DESC"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/stock/rapprochement/detail/<no_doc>')
@login_required
def api_rapprochement_detail(no_doc):
    uid = session['user_id']
    if not _peut(uid, 'rapprochement_bl', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    rows = db_all(
        "SELECT * FROM mouvements_stock WHERE no_doc_sage=? OR no_doc_manuel=? "
        "ORDER BY code_article", (no_doc, no_doc))
    return jsonify(ok=True, data=rows)


# ── Documents non regularises ─────────────────────────────────────────────────
@bp.route('/api/stock/docs-non-regularises')
@login_required
def api_docs_non_reg():
    uid = session['user_id']
    if not _peut(uid, 'documents_non_reg', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    rows = db_all("""SELECT no_doc_manuel,type_mouvement,
                            MIN(date_mvt) AS date_mvt,
                            COUNT(code_article) AS nb_articles,
                            MAX(saisi_par) AS saisi_par,
                            MAX(cree_le) AS cree_le,
                            CAST(julianday('now')-julianday(MIN(date_mvt)) AS INTEGER) AS jours_attente
                     FROM mouvements_stock
                     WHERE regularise=0 AND no_doc_manuel <> ''
                     GROUP BY no_doc_manuel,type_mouvement
                     ORDER BY date_mvt ASC""")
    return jsonify(ok=True, data=rows)


# ── Equilibre inter-magasins ──────────────────────────────────────────────────
@bp.route('/api/analyses/equilibre')
@login_required
def api_equilibre():
    uid = session['user_id']
    if not _peut(uid, 'equilibre', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '3mois')
    mvts = get_mouvements(periode)
    return jsonify(ok=True, data=eng.equilibre_inter_magasins(mvts))


# ── Analyses BI ───────────────────────────────────────────────────────────────
@bp.route('/api/analyses/dashboard')
@login_required
def api_analyses_dashboard():
    uid = session['user_id']
    if not _peut(uid, 'analyses_top', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '3mois')
    granularite = request.args.get('granularite', 'mois')
    jours_dormants = int(request.args.get('jours_dormants', 60))
    mvts = get_mouvements(periode)
    return jsonify(ok=True, periode=periode, granularite=granularite,
                    kpis=eng.kpis(mvts),
                    top_articles=eng.top_articles(mvts, 10),
                    evolution=eng.evolution_temporelle(mvts, granularite),
                    evolution_dormants=eng.evolution_dormants(mvts, jours_dormants, granularite),
                    familles=eng.repartition_familles(mvts),
                    dormants_count=len(eng.stocks_dormants(mvts, jours_dormants)),
                    nb_mouvements=len(mvts))


@bp.route('/api/analyses/top-articles')
@login_required
def api_top_articles():
    uid = session['user_id']
    if not _peut(uid, 'analyses_top', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '3mois')
    limit = int(request.args.get('limit', 20))
    mvts = get_mouvements(periode)
    return jsonify(ok=True, data=eng.top_articles(mvts, limit), periode=periode)


@bp.route('/api/analyses/dormants')
@login_required
def api_dormants():
    uid = session['user_id']
    if not _peut(uid, 'analyses_dormants', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '12mois')
    jours = int(request.args.get('jours', 60))
    mvts = get_mouvements(periode)
    return jsonify(ok=True, data=eng.stocks_dormants(mvts, jours))


@bp.route('/api/analyses/reappro')
@login_required
def api_reappro():
    uid = session['user_id']
    if not _peut(uid, 'analyses_reappro', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '3mois')
    sem = int(request.args.get('semaines', 4))
    mvts = get_mouvements(periode)
    return jsonify(ok=True, data=eng.besoins_reappro(mvts, sem))


@bp.route('/api/analyses/clients')
@login_required
def api_analyse_clients():
    uid = session['user_id']
    if not _peut(uid, 'analyses_graphiques', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '12mois')
    code = request.args.get('code', '')
    mvts = get_mouvements(periode)
    return jsonify(ok=True, data=eng.consommation_clients(mvts, code or None))


@bp.route('/api/analyses/previsions')
@login_required
def api_previsions():
    uid = session['user_id']
    if not _peut(uid, 'analyses_graphiques', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    periode = request.args.get('periode', '12mois')
    mvts = get_mouvements(periode)
    all_c = eng.consommation_clients(mvts)
    prev = [c for c in all_c if c.get('nb_commandes', 0) >= 2 and c.get('frequence_jours')]
    prev.sort(key=lambda x: x.get('jours_restants') if x.get('jours_restants') is not None else 9999)
    return jsonify(ok=True, data=prev)


@bp.route('/api/analyses/comparative')
@login_required
def api_comparative():
    uid = session['user_id']
    if not _peut(uid, 'analyses_graphiques', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    p1 = request.args.get('periode1', '3mois')
    p2 = request.args.get('periode2', '6mois')
    m1 = get_mouvements(p1)
    m2 = get_mouvements(p2)
    return jsonify(ok=True, data=eng.analyse_comparative(m1, m2, p1, p2), periode1=p1, periode2=p2)
