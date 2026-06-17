"""NEXORA v2.0 — Module Stock & Inventaire (complet)"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import (get_config, PERMISSIONS_TREE,
                            db_all, db_one, db_exec, audit)
from datetime import date, timedelta
import logging

log = logging.getLogger('NEXORA.Stock')


@bp.route('/module/stock')
@login_required
def module_stock():
    user    = get_user()
    modules = session.get('modules', [])
    cfg     = {'nom_societe': get_config('nom_societe', ''),
               'devise':      get_config('devise', 'XAF')}
    return render_template('modules/stock.html',
        module='stock', module_label='Stock & Inventaire',
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)


# ── Dashboard ────────────────────────────────────────────────────

@bp.route('/api/stock/dashboard')
@login_required
def api_stock_dashboard():
    from core.sage_connector import get_stock_disponible
    articles = get_stock_disponible(7)
    if not articles:
        return jsonify({
            'ok': True, 'message': 'Sage non disponible (aucun article recupere)',
            'ruptures': 0, 'dormants': 0, 'mouvements_jour': 0,
            'valeur_stock': 0, 'alertes': [], 'nb_articles': 0,
        })
    ruptures = sum(1 for a in articles if float(a.get('stock_physique', 0)) <= 0)
    dormants_count = db_one(
        "SELECT COUNT(*) n FROM mouvements_stock WHERE statut='en_attente'"
    ) or {'n': 0}
    mvt_jour = db_one(
        "SELECT COUNT(*) n FROM mouvements_stock WHERE date(cree_le)=date('now')"
    ) or {'n': 0}
    valeur = sum(
        float(a.get('stock_physique', 0)) * float(a.get('prix_achat', 0))
        for a in articles
    )
    alertes = []
    if ruptures > 0:
        alertes.append({
            'ico': 'ERR', 'niveau': 'danger',
            'message': str(ruptures) + ' article(s) en rupture de stock'
        })
    non_reg = db_one(
        "SELECT COUNT(*) n FROM mouvements_stock "
        "WHERE type_mouvement='MANUEL' AND regularise=0"
    ) or {'n': 0}
    if non_reg['n'] > 0:
        alertes.append({
            'ico': 'WARN', 'niveau': 'warning',
            'message': str(non_reg['n']) + ' bordereau(x) manuel(s) non régularisé(s)'
        })
    return jsonify({
        'ok':             True,
        'ruptures':       ruptures,
        'dormants':       dormants_count['n'],
        'mouvements_jour': mvt_jour['n'],
        'valeur_stock':   round(valeur, 0),
        'alertes':        alertes,
        'nb_articles':    len(articles),
    })


# ── BL Sage ──────────────────────────────────────────────────────

@bp.route('/api/stock/reconstituer-bl', methods=['POST'])
@login_required
def api_reconstituer_bl():
    d     = request.get_json() or {}
    no_bl = d.get('no_bl', '').strip()
    if not no_bl:
        return jsonify({'ok': False, 'msg': 'Numéro BL obligatoire'})
    cached = db_all(
        "SELECT * FROM mouvements_stock WHERE no_doc_sage=? AND type_mouvement='BL_SAGE'",
        (no_bl,))
    if cached:
        return jsonify({'ok': True, 'lignes': cached, 'source': 'cache'})
    from core.sage_connector import reconstituer_bl
    lignes = reconstituer_bl(no_bl)
    return jsonify({'ok': True, 'lignes': lignes, 'source': 'sage',
                    'nb': len(lignes)})


@bp.route('/api/stock/valider-bl', methods=['POST'])
@login_required
def api_valider_bl():
    d      = request.get_json() or {}
    lignes = d.get('lignes', [])
    if not lignes:
        return jsonify({'ok': False, 'msg': 'Aucune ligne'})
    nb_valide = nb_ecart = 0
    for l in lignes:
        qte_saisie = float(l.get('qte_saisie', 0))
        qte_sage   = float(l.get('qte_doc_sage', 0))
        ecart      = round(qte_sage - qte_saisie, 4)
        statut     = 'valide' if abs(ecart) < 0.01 else 'ecart'
        if statut == 'valide':
            nb_valide += 1
        else:
            nb_ecart += 1
        db_exec(
            "INSERT INTO mouvements_stock(type_mouvement,no_doc_sage,date_mvt,"
            "code_article,designation,qte_saisie,qte_doc_sage,ecart,"
            "code_client,client_nom,statut,saisi_par,agence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ('BL_SAGE', l.get('no_bl', ''), l.get('date_mvt', str(date.today())),
             l.get('ar_ref', ''), l.get('designation', ''),
             qte_saisie, qte_sage, ecart,
             l.get('code_client', ''), l.get('client_nom', ''),
             statut, session.get('username', ''), 'BERTOUA'))
    audit(session.get('username', '?'), 'STOCK', 'BL_VALIDE',
          'nb=' + str(len(lignes)) + ' ecarts=' + str(nb_ecart))
    return jsonify({'ok': True, 'nb': len(lignes),
                    'nb_valide': nb_valide, 'nb_ecart': nb_ecart})


# ── Bordereau Manuel ─────────────────────────────────────────────

@bp.route('/api/stock/saisir-manuel', methods=['POST'])
@login_required
def api_saisir_manuel():
    d    = request.get_json() or {}
    code = d.get('code_article', '').strip()
    if not code:
        return jsonify({'ok': False, 'msg': 'Code article obligatoire'})
    qte = float(d.get('qte_saisie', 0))
    if qte <= 0:
        return jsonify({'ok': False, 'msg': 'Quantité doit être > 0'})
    count = db_one("SELECT COUNT(*) n FROM mouvements_stock") or {'n': 0}
    no_manuel = 'MAN' + date.today().strftime('%Y%m%d') + str(count['n'] + 1).zfill(4)
    uid = db_exec(
        "INSERT INTO mouvements_stock(type_mouvement,no_doc_manuel,date_mvt,"
        "code_article,designation,qte_saisie,code_client,client_nom,statut,saisi_par,agence)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ('MANUEL', no_manuel, d.get('date_mvt', str(date.today())),
         code, d.get('designation', ''), qte,
         d.get('code_client', ''), d.get('client_nom', ''),
         'en_attente', session.get('username', ''), 'BERTOUA'))
    audit(session.get('username', '?'), 'STOCK', 'MANUEL_CREE', no_manuel)
    return jsonify({'ok': True, 'id': uid, 'no_manuel': no_manuel})


@bp.route('/api/stock/regulariser-manuel', methods=['POST'])
@login_required
def api_regulariser_manuel():
    d         = request.get_json() or {}
    mvt_id    = d.get('id')
    no_sage   = d.get('no_sage', '').strip()
    if not mvt_id or not no_sage:
        return jsonify({'ok': False, 'msg': 'ID et numéro Sage obligatoires'})
    mvt = db_one("SELECT * FROM mouvements_stock WHERE id=?", (mvt_id,))
    if not mvt:
        return jsonify({'ok': False, 'msg': 'Mouvement introuvable'})
    from core.sage_connector import reconstituer_bl
    lignes_sage = reconstituer_bl(no_sage)
    qte_sage    = 0
    for l in lignes_sage:
        ref = l.get('AR_Ref', '') or l.get('ar_ref', '')
        if ref == mvt['code_article']:
            qte_sage = float(l.get('DL_Qte', 0) or l.get('qte_saisie', 0))
            break
    ecart  = round(qte_sage - float(mvt['qte_saisie']), 4)
    statut = 'valide' if abs(ecart) < 0.01 else 'ecart'
    db_exec(
        "UPDATE mouvements_stock SET regularise=1, regularise_le=?, "
        "no_sage_lie=?, qte_doc_sage=?, ecart=?, statut=? WHERE id=?",
        (str(date.today()), no_sage, qte_sage, ecart, statut, mvt_id))
    return jsonify({'ok': True, 'statut': statut, 'ecart': ecart,
                    'qte_sage': qte_sage})


# ── Historique ───────────────────────────────────────────────────

@bp.route('/api/stock/historique')
@login_required
def api_stock_historique():
    limite  = min(int(request.args.get('limite', 100)), 500)
    type_mv = request.args.get('type', '')
    statut  = request.args.get('statut', '')
    sql     = "SELECT * FROM mouvements_stock WHERE 1=1"
    params  = []
    if type_mv:
        sql += " AND type_mouvement=?"; params.append(type_mv)
    if statut:
        sql += " AND statut=?"; params.append(statut)
    sql += " ORDER BY cree_le DESC LIMIT ?"
    params.append(limite)
    rows = db_all(sql, params)
    return jsonify({'ok': True, 'mouvements': rows, 'nb': len(rows)})


@bp.route('/api/stock/docs-non-regularises')
@login_required
def api_docs_non_reg():
    rows = db_all(
        "SELECT * FROM mouvements_stock WHERE type_mouvement='MANUEL' "
        "AND regularise=0 ORDER BY cree_le DESC")
    return jsonify({'ok': True, 'documents': rows, 'nb': len(rows)})


# ── Analyses avec périodes ───────────────────────────────────────

@bp.route('/api/stock/analyses/top-sorties')
@login_required
def api_top_sorties():
    """Top sorties — supporte comparaison multi-périodes."""
    from core.sage_connector import get_mouvements
    debut  = request.args.get('debut', '')
    fin    = request.args.get('fin', '')
    limite = int(request.args.get('limite', 20))
    if not debut:
        debut = str(date.today().replace(day=1))
    if not fin:
        fin = str(date.today())
    mvts   = get_mouvements(date_debut=debut, date_fin=fin)
    if not mvts:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun mouvement recupere)',
                        'articles': [], 'somme_top': 0, 'nb_total': 0, 'debut': debut, 'fin': fin})
    totaux = {}
    for m in mvts:
        ref  = m.get('AR_Ref', '?')
        desc = m.get('DL_Design', '')
        qte  = float(m.get('DL_Qte', 0) or 0)
        if ref not in totaux:
            totaux[ref] = {'ar_ref': ref, 'designation': desc, 'total_qte': 0, 'nb_mvts': 0}
        totaux[ref]['total_qte'] += qte
        totaux[ref]['nb_mvts']   += 1
    top       = sorted(totaux.values(), key=lambda x: x['total_qte'], reverse=True)[:limite]
    somme_top = sum(a['total_qte'] for a in top)
    return jsonify({
        'ok':        True,
        'articles':  top,
        'somme_top': somme_top,
        'nb_total':  len(totaux),
        'debut':     debut,
        'fin':       fin,
    })


@bp.route('/api/stock/analyses/dormants')
@login_required
def api_dormants():
    """Stock dormant — supporte comparaison multi-périodes."""
    from core.sage_connector import get_stock_disponible, get_mouvements
    seuil_jours = int(request.args.get('jours', 15))
    debut       = request.args.get('debut', '')
    fin         = request.args.get('fin', str(date.today()))
    if debut:
        seuil_date = debut
    else:
        seuil_date = str(date.today() - timedelta(days=seuil_jours))
    articles      = get_stock_disponible(7)
    if not articles:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun article recupere)',
                        'articles': [], 'somme_totale': 0, 'valeur_immobilisee': 0,
                        'seuil_jours': seuil_jours, 'debut': seuil_date, 'fin': fin})
    mvts_recents  = get_mouvements(date_debut=seuil_date, date_fin=fin)
    refs_actives  = set(m.get('AR_Ref', '') for m in mvts_recents)
    dormants = [
        a for a in articles
        if float(a.get('stock_physique', 0)) > 0
        and a.get('AR_Ref', '') not in refs_actives
    ]
    valeur_immob = sum(
        float(a.get('stock_physique', 0)) * float(a.get('prix_achat', a.get('AR_PrixAch', 0)))
        for a in dormants
    )
    return jsonify({
        'ok':               True,
        'articles':         dormants[:100],
        'somme_totale':     len(dormants),
        'valeur_immobilisee': round(valeur_immob, 0),
        'seuil_jours':      seuil_jours,
        'debut':            seuil_date,
        'fin':              fin,
    })


@bp.route('/api/stock/analyses/valorisation')
@login_required
def api_valorisation():
    """Valorisation du stock — supporte comparaison multi-périodes."""
    from core.sage_connector import get_stock_disponible
    depot_no = int(request.args.get('depot', 7))
    articles = get_stock_disponible(depot_no)
    if not articles:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun article recupere)',
                        'valeur_totale': 0, 'nb_articles': 0, 'nb_ruptures': 0, 'depot': depot_no})
    valeur_totale = sum(
        float(a.get('stock_physique', 0)) * float(a.get('prix_achat', a.get('AR_PrixAch', 0)))
        for a in articles
    )
    nb_articles   = len(articles)
    nb_ruptures   = sum(1 for a in articles if float(a.get('stock_physique', 0)) <= 0)
    return jsonify({
        'ok':           True,
        'valeur_totale': round(valeur_totale, 0),
        'nb_articles':   nb_articles,
        'nb_ruptures':   nb_ruptures,
        'depot':         depot_no,
    })


# ── Stock Consolidé ──────────────────────────────────────────────

@bp.route('/api/stock/consolide')
@login_required
def api_stock_consolide():
    """
    Stock consolidé : Article × Agence
    Tableau : Bertoua | Douala | Yaoundé | Garoua-Boulaï | TOTAL | VALEUR
    """
    from core.sage_connector import get_stock_disponible
    agences = db_all("SELECT * FROM nx_agences WHERE actif=1 ORDER BY id")
    dicts_par_agence = {}
    for ag in agences:
        depot_no = ag.get('depot_sage_no') or 7
        arts     = get_stock_disponible(depot_no)
        dicts_par_agence[ag['id']] = {
            a.get('AR_Ref', ''): a for a in arts
        }
    # Regrouper tous les articles
    tous_refs = set()
    for arts_dict in dicts_par_agence.values():
        tous_refs.update(arts_dict.keys())
    result = []
    for ref in sorted(tous_refs):
        ligne = {'ar_ref': ref, 'designation': '', 'agences': {}, 'total': 0, 'valeur': 0}
        prix  = 0
        for ag in agences:
            art = dicts_par_agence[ag['id']].get(ref, {})
            qte = float(art.get('stock_physique', 0))
            if not ligne['designation'] and art.get('AR_Design'):
                ligne['designation'] = art['AR_Design']
            if not prix and art.get('prix_achat'):
                prix = float(art.get('prix_achat', 0))
            ligne['agences'][ag['id']] = qte
            ligne['total']            += qte
        ligne['valeur'] = round(ligne['total'] * prix, 0)
        ligne['prix']   = prix
        if ligne['total'] > 0:
            result.append(ligne)
    valeur_totale = sum(l['valeur'] for l in result)
    if not result:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun article recupere)',
                        'articles': [], 'agences': agences, 'valeur_totale': 0, 'nb_articles': 0})
    return jsonify({
        'ok':          True,
        'articles':    result,
        'agences':     agences,
        'valeur_totale': valeur_totale,
        'nb_articles': len(result),
    })


# ── Multi-Sites (DT/DA) ──────────────────────────────────────────

@bp.route('/api/stock/multisite/stock-disponible')
@login_required
def api_ms_stock_dispo():
    from core.sage_connector import get_stock_disponible
    agence_id = int(request.args.get('agence_source', 2))
    q         = request.args.get('q', '')
    ag        = db_one("SELECT * FROM nx_agences WHERE id=?", (agence_id,))
    depot_no  = ag.get('depot_sage_no', 7) if ag else 7
    articles  = get_stock_disponible(depot_no, q)
    if not articles:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun article recupere)',
                        'articles': [], 'agence': ag, 'nb': 0})
    dts_en_cours = db_all(
        "SELECT tl.ar_ref, SUM(tl.qte_demandee) qte_dt "
        "FROM nx_transferts_lignes tl "
        "JOIN nx_transferts t ON t.id=tl.transfert_id "
        "WHERE t.statut IN ('VALIDEE','EN_COURS') "
        "AND t.agence_source_id=? "
        "GROUP BY tl.ar_ref", (agence_id,))
    dt_map = {r['ar_ref']: r['qte_dt'] for r in dts_en_cours}
    for a in articles:
        ref            = a.get('AR_Ref', '')
        phys           = float(a.get('stock_physique', 0))
        res            = float(a.get('qte_reservee', 0))
        dt             = float(dt_map.get(ref, 0))
        a['qte_en_dt'] = dt
        a['stock_dispo'] = max(0, phys - res - dt)
    return jsonify({'ok': True, 'articles': articles,
                    'agence': ag, 'nb': len(articles)})


@bp.route('/api/stock/multisite/transferts', methods=['GET', 'POST'])
@login_required
def api_ms_transferts():
    if request.method == 'POST':
        import random, string
        d   = request.get_json() or {}
        no  = 'DT' + date.today().strftime('%Y%m%d') + \
              ''.join(random.choices(string.digits, k=4))
        uid = db_exec(
            "INSERT INTO nx_transferts(numero,agence_source_id,agence_dest_id,"
            "statut,urgence,demande_par,nb_lignes) VALUES(?,?,?,?,?,?,?)",
            (no, d.get('agence_source_id', 2), d.get('agence_dest_id', 3),
             'SOUMISE', 1 if d.get('urgence') else 0,
             session.get('username', ''), len(d.get('lignes', []))))
        for l in d.get('lignes', []):
            db_exec(
                "INSERT INTO nx_transferts_lignes(transfert_id,ar_ref,"
                "designation,qte_demandee,stock_dispo_src) VALUES(?,?,?,?,?)",
                (uid, l.get('ar_ref', ''), l.get('designation', ''),
                 float(l.get('qte', 0)), float(l.get('stock_dispo', 0))))
        audit(session.get('username', '?'), 'MULTISITE', 'DT_CREE', no)
        return jsonify({'ok': True, 'id': uid, 'numero': no})
    statut = request.args.get('statut', '')
    sql = (
        "SELECT t.*, sa.nom source_nom, da.nom dest_nom "
        "FROM nx_transferts t "
        "LEFT JOIN nx_agences sa ON sa.id=t.agence_source_id "
        "LEFT JOIN nx_agences da ON da.id=t.agence_dest_id"
    )
    params = []
    if statut:
        sql += " WHERE t.statut=?"; params.append(statut)
    sql += " ORDER BY t.date_demande DESC LIMIT 200"
    return jsonify({'ok': True, 'transferts': db_all(sql, params)})


@bp.route('/api/stock/multisite/transferts/<int:tid>/valider', methods=['POST'])
@login_required
def api_ms_valider_dt(tid):
    d      = request.get_json() or {}
    action = d.get('action', 'valider')
    motif  = d.get('motif_refus', '').strip()
    if action == 'refuser' and not motif:
        return jsonify({'ok': False, 'msg': 'Motif de refus obligatoire'})
    statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
    db_exec(
        "UPDATE nx_transferts SET statut=?,date_validation=?,valide_par=?,motif_refus=? WHERE id=?",
        (statut, str(date.today()), session.get('username', ''), motif, tid))
    audit(session.get('username', '?'), 'MULTISITE', 'DT_' + statut,
          'id=' + str(tid))
    return jsonify({'ok': True, 'statut': statut})


@bp.route('/api/stock/multisite/demandes-achat', methods=['GET', 'POST'])
@login_required
def api_ms_da():
    if request.method == 'POST':
        import random, string
        d   = request.get_json() or {}
        no  = 'DA' + date.today().strftime('%Y%m%d') + \
              ''.join(random.choices(string.digits, k=4))
        uid = db_exec(
            "INSERT INTO nx_demandes_achat(numero,agence_id,fournisseur_nom,"
            "statut,urgence,livraison_agence,demande_par,observations) VALUES(?,?,?,?,?,?,?,?)",
            (no, d.get('agence_id', 2), d.get('fournisseur_nom', ''),
             'SOUMISE', 1 if d.get('urgence') else 0,
             d.get('agence_id', 2), session.get('username', ''),
             d.get('observations', '')))
        audit(session.get('username', '?'), 'MULTISITE', 'DA_CREE', no)
        return jsonify({'ok': True, 'id': uid, 'numero': no})
    return jsonify({'ok': True, 'demandes': db_all(
        "SELECT * FROM nx_demandes_achat ORDER BY date_demande DESC LIMIT 100")})


@bp.route('/api/stock/multisite/demandes-achat/<int:did>/valider', methods=['POST'])
@login_required
def api_ms_valider_da(did):
    d      = request.get_json() or {}
    action = d.get('action', 'valider')
    motif  = d.get('motif_refus', '').strip()
    if action == 'refuser' and not motif:
        return jsonify({'ok': False, 'msg': 'Motif obligatoire'})
    statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
    db_exec(
        "UPDATE nx_demandes_achat SET statut=?,date_validation=?,valide_par=?,motif_refus=? WHERE id=?",
        (statut, str(date.today()), session.get('username', ''), motif, did))
    return jsonify({'ok': True, 'statut': statut})
