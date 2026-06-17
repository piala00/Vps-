"""
NEXORA v2.0 — Module Commercial & Ventes
Toutes les regles metier de GTC ERP PILOT V3.
Source SQL/Excel respectee, cache 24h, filtre periode, roles.
"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_exec, db_one
import logging
from datetime import date as _date, datetime

log = logging.getLogger('NEXORA.Commercial')


def _get_user_filter():
    """Retourne le filtre commercial si l'utilisateur est un commercial."""
    u = get_user()
    if u.get('role') == 'commercial' and u.get('commercial_name'):
        return u['commercial_name']
    return None


def _get_agence_commerciaux(agence):
    """Retourne les noms normalises des commerciaux rattaches a une agence (role agence)."""
    from core.commercial_engine import _norm
    rows = db_all(
        "SELECT commercial_name FROM utilisateurs WHERE agence=? AND role='commercial' AND actif=1",
        (agence,))
    return {_norm(r['commercial_name']) for r in rows if r['commercial_name']}


def _filter_by_agence_if_needed(rows, key_commercial='commercial'):
    """Si l'utilisateur a le role 'agence', filtre les lignes sur les commerciaux de son agence."""
    u = get_user()
    if u.get('role') != 'agence' or not u.get('agence'):
        return rows
    from core.commercial_engine import _norm
    ag_coms = _get_agence_commerciaux(u['agence'])
    if not ag_coms:
        return rows
    return [r for r in rows if _norm(r.get(key_commercial, '')) in ag_coms]


def _periode_from_request():
    """
    Lit la periode d'analyse depuis les parametres URL, fidele a la barre
    globale Annee/Mois/Du-Au de GTC ERP PILOT V3. Supporte annee+mois
    (dropdowns), du+au (plage exacte) ou debut/fin (alias retrocompatible).
    Sans defaut explicite, retombe sur le mois en cours.
    Sans cette resolution centralisee, chaque route choisissait sa propre
    periode par defaut, rendant CA/Creances/Tendances incomparables entre
    ecrans et avec l'ancien logiciel.
    """
    from core.commercial_engine import resolve_period
    debut, fin, label = resolve_period(request.args)
    return debut, fin


def _load_data(force=False, period_args=None):
    """
    Charge et calcule toutes les donnees commerciales pour la periode
    resolue depuis period_args (typiquement request.args), fidele a la
    barre globale Annee/Mois/Du-Au de GTC ERP PILOT V3.
    Sans cette resolution explicite, le CA/Creances/Tendances seraient
    calcules sur un cumul depuis le debut de l'annee, faussant toute
    comparaison avec les chiffres mensuels attendus.
    Respecte la source (SQL ou Excel) configuree.
    Retourne le dict data ou None si pas de donnees.
    """
    from core.data_source import load_grand_livre_data, get_commerciaux_list
    from core.commercial_engine import init_commerciaux, compute_all, resolve_period, _latest_date
    all_rows, ref, coms = load_grand_livre_data(force=force)
    if not all_rows: return None
    init_commerciaux(coms)
    latest = _latest_date(all_rows)
    debut, fin, label = resolve_period(period_args or {}, latest_date=latest)
    data  = compute_all(all_rows, ref, start_date=debut, end_date=fin)
    data['source']        = get_config('source','sql').upper()
    data['all_rows']      = all_rows  # donnees completes pour tendances
    data['period_label']  = label
    data['period_debut']  = str(debut)
    data['period_fin']    = str(fin)
    return data


@bp.route('/module/commercial')
@login_required
def module_commercial():
    user    = get_user()
    modules = session.get('modules',[])
    cfg     = {'nom_societe': get_config('nom_societe',''),
               'devise':      get_config('devise','XAF')}
    from core.auth import get_allowed_subtabs
    allowed = get_allowed_subtabs(user.get('role','admin'), 'commercial')
    return render_template('modules/commercial.html',
        module='commercial', module_label='Commercial & Ventes',
        user=user, modules=modules, config=cfg, tree=PERMISSIONS_TREE,
        allowed_subtabs=allowed)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route('/api/commercial/dashboard')
@login_required
def api_commercial_dashboard():
    force       = request.args.get('force','0')=='1'
    debut, fin  = _periode_from_request()
    data        = _load_data(force=force, period_args=request.args)
    if not data:
        return jsonify({'ok':True,'message':'Sage/Excel non disponible',
                        'ca_total':0,'rec_total':0,'creances_totales':0,
                        'nb_clients':0,'nb_commerciaux':0,'nb_retard':0,
                        'source': get_config('source','sql').upper(),
                        'periode': {'debut': str(debut), 'fin': str(fin)}})
    com_f = _get_user_filter()
    k     = data['kpis']
    # Alertes
    alertes = [{'niveau':a['niveau'],'code':a['code'],'nom':a['nom'],
                 'fns':round(a['fns'],2),'retard':a['retard'],'msg':a['msg']}
                for a in data['alertes'][:12]]
    if com_f:
        alertes = [a for a in alertes if a.get('com')==com_f]
    return jsonify({
        'ok':            True,
        'ca_total':      round(k['ca'],2),
        'rec_total':     round(k['recouvrement'],2),
        'taux_rec':      round(k['taux_rec'],1),
        'creances_totales': round(k['fns'],2),
        'nb_clients':    k['nb_clients'],
        'nb_retard':     k['nb_retard'],
        'nb_commerciaux':len(data['commerciaux']),
        'alertes':       alertes,
        'source':        data['source'],
        'analysis_date': str(data['analysis_date']) if data.get('analysis_date') else '',
        'period_label':  data.get('period_label',''),
        'loaded_at':     data.get('loaded_at',''),
        'periode':       {'debut': str(debut), 'fin': str(fin)},
    })


# ── Classement ────────────────────────────────────────────────────────────────

@bp.route('/api/commercial/classement')
@login_required
def api_classement():
    force = request.args.get('force','0')=='1'
    debut, fin = _periode_from_request()
    data  = _load_data(force=force, period_args=request.args)
    if not data:
        return jsonify({'ok':True,'classement':[],'message':'Sage/Excel non disponible'})
    com_f = _get_user_filter()
    cl    = data['classement']
    if com_f:
        cl = [r for r in cl if r['commercial']==com_f]
    cl = _filter_by_agence_if_needed(cl, 'commercial')
    # Serialiser
    out = []
    for r in cl:
        out.append({
            'rang':        r['rang'],
            'commercial':  r['commercial'],
            'ca':          round(r['ca'],2),
            'objectif':    round(r['objectif'],2),
            'pct_obj':     round(r['pct_obj']*100,1),
            'recouvrement':round(r['recouvrement'],2),
            'taux_rec':    round(r['taux_rec']*100,1),
            'fns':         round(r['fns'],2),
            'nb_retard':   r['nb_retard'],
            'score':       round(r['score']*100,1),
            'risque':      round(r.get('risque',0)*100,1),
        })
    return jsonify({'ok':True,'classement':out,'nb':len(out),
                    'source':data.get('source',''),
                    'period_label': data.get('period_label',''),
                    'periode': {'debut': str(debut), 'fin': str(fin)}})


# ── Cockpit d'un commercial ───────────────────────────────────────────────────

@bp.route('/api/commercial/cockpit')
@login_required
def api_cockpit():
    com   = request.args.get('commercial','').strip()
    force = request.args.get('force','0')=='1'
    debut, fin = _periode_from_request()
    if not com:
        return jsonify({'ok':False,'msg':'commercial manquant'})
    # RBAC: un commercial ne peut voir que son propre cockpit
    u = get_user()
    if u.get('role') == 'commercial' and u.get('commercial_name') and com != u['commercial_name']:
        return jsonify({'ok':False,'msg':'Acces non autorise a ce cockpit'})
    if u.get('role') == 'agence' and u.get('agence'):
        from core.commercial_engine import _norm
        ag_coms = _get_agence_commerciaux(u['agence'])
        if ag_coms and _norm(com) not in ag_coms:
            return jsonify({'ok':False,'msg':'Acces non autorise a ce cockpit'})
    data = _load_data(force=force, period_args=request.args)
    if not data:
        return jsonify({'ok':True,'kpis':{},'message':'Sage/Excel non disponible'})
    from core.commercial_engine import (build_cockpit_com, client_statut,
                                        _com_cockpit, _is_vt,
                                        build_copilote_quotidien,
                                        build_grand_livre_commercial)
    kd = build_cockpit_com(com, data)

    # ── Copilote quotidien : objectif du MOIS DE LA PERIODE SELECTIONNEE ──
    # Regle metier : sans la periode explicite, le copilote (objectif mensuel,
    # progression du jour) et le cockpit principal (CA realise sur la periode)
    # affichent des chiffres incoherents car calcules sur des fenetres de
    # temps differentes. Les deux doivent utiliser la meme reference de mois.
    today_dt    = fin if isinstance(fin, _date) else _date.today()
    periode_str = today_dt.strftime('%Y-%m')
    obj_row     = db_one(
        "SELECT objectif_ca FROM objectifs_commerciaux WHERE commercial=? AND periode=?",
        (com, periode_str))
    if obj_row and obj_row.get('objectif_ca'):
        objectif_mensuel = obj_row['objectif_ca']
    else:
        objectif_mensuel = (kd.get('obj', 0) or 0) / 12.0
    copilote = build_copilote_quotidien(com, data['all_rows'], objectif_mensuel, today=today_dt)

    # Top clients avec statut
    ref      = data['ref']
    top_codes= [x['code'] for x in kd['top_clients']]
    cre_map  = {c['code']:c for c in data['creances'] if _com_cockpit(c.get('commercial',''))==com}
    top_enrich = []
    for code in top_codes:
        c   = cre_map.get(code,{})
        lbl,col,ico,action = client_statut(c)
        top_enrich.append({
            'code':    code,
            'nom':     ref.get(code,{}).get('nom',code),
            'zone':    ref.get(code,{}).get('zone',''),
            'ca':      round(next((x['ca'] for x in kd['top_clients'] if x['code']==code),0),2),
            'statut':  lbl,
            'couleur': col,
            'icone':   ico,
            'action':  action,
            'fns':     round(c.get('fns',0),2),
            'retard':  c.get('retard',0),
            'solde':   round(c.get('solde',0),2),
            'telephone': ref.get(code,{}).get('telephone',''),
        })
    # Creances de ce commercial
    creances_com = [c for c in data['creances'] if _com_cockpit(c.get('commercial',''))==com]

    # ── Grand Livre filtre sur le portefeuille du commercial (distinct du ──
    # Grand Livre general de Comptabilite — meme structure 16 colonnes) ──
    gl_com = build_grand_livre_commercial(data.get('grand', []), com)
    gl_out = [{
        'code': r['code'], 'nom': r['nom'], 'zone': r.get('zone',''),
        'date': str(r['date']) if r['date'] else '', 'journal': r['journal'],
        'piece': r['piece'], 'libelle': r['libelle'],
        'debit': round(r['debit'],2), 'credit': round(r['credit'],2),
        'solde_d': round(r['solde_d'],2), 'solde_c': round(r['solde_c'],2),
        'statut': r['statut'], 'ouvert': round(r['ouvert'],2),
        'echeance': str(r['echeance']) if r['echeance'] else '',
        'retard': r['retard'], 'type': r['type'], 'is_total': r['is_total'],
    } for r in gl_com[:500]]
    return jsonify({
        'ok':          True,
        'commercial':  com,
        'kpis': {
            'ca':           round(kd['ca'],2),
            'obj':          round(kd['obj'],2),
            'pct_obj':      round(kd['pct_obj'],1),
            'recouvrement': round(kd['recouvrement'],2),
            'fns':          round(kd['fns'],2),
            'solde':        round(kd['solde'],2),
            'nb_retard':    kd['nb_retard'],
            'nb_clients':   kd['nb_clients'],
            'mdp':          round(kd['mdp'],2),
            'taux_rec':     round(kd['taux_rec'],1),
            'taux_risque':  round(kd['taux_risque'],1),
            'nb_fac':       kd['nb_fac'],
            'ca_comptant':  round(kd['ca_comptant'],2),
            'ca_terme':     round(kd['ca_terme'],2),
        },
        'copilote':    copilote,
        'daily':       copilote['historique_7j'],
        'top_clients': top_enrich,
        'creances':    creances_com,
        'grand_livre': gl_out,
        'mouvements':  gl_out,
        'source':      data.get('source',''),
        'periode':     {'debut': str(debut), 'fin': str(fin)},
    })


# ── Tendances ─────────────────────────────────────────────────────────────────

@bp.route('/api/commercial/tendances')
@login_required
def api_tendances():
    gran  = request.args.get('granularite','mensuel')
    vue   = request.args.get('vue','CA')
    com   = request.args.get('commercial','')
    force = request.args.get('force','0')=='1'
    data  = _load_data(force=force)
    if not data:
        return jsonify({'ok':True,'periodes':[],'message':'Sage/Excel non disponible'})
    from core.commercial_engine import build_tendances, _com_cockpit
    all_rows = data.get('all_rows', data.get('raw',[]))
    if com:
        all_rows = [r for r in all_rows
                    if r.get('com_vente')==com or _com_cockpit(r.get('commercial',''))==com]
    result = build_tendances(all_rows, granularite=gran)
    # Vue demandee
    if vue == 'CA':
        periodes = result['ca']
    elif vue == 'Recouvrement':
        periodes = result['recouvrement']
    else:
        periodes = result['creances']
    return jsonify({'ok':True,'periodes':periodes,'granularite':gran,'vue':vue,
                    'source':data.get('source',''),
                    'all_periodes': result['periodes']})


# ── Analyse CA avec periodes (sélecteur universel) ────────────────────────────

@bp.route('/api/commercial/analyse-ca')
@login_required
def api_analyse_ca():
    debut_s = request.args.get('debut','')
    fin_s   = request.args.get('fin','')
    force   = request.args.get('force','0')=='1'
    # Charger les donnees completes (pas de periode appliquee a la source)
    # puis filtrer une seule fois sur la vraie periode demandee, pour eviter
    # le double-filtrage incoherent (periode par defaut de _load_data PUIS
    # filtre date ici).
    data  = _load_data(force=force)
    if not data:
        return jsonify({'ok':True,'total_ca':0,'nb_factures':0,
                        'message':'Sage/Excel non disponible'})
    rows = data.get('all_rows', data['raw'])
    if debut_s:
        try:
            from datetime import datetime as dt
            d1 = dt.strptime(debut_s,'%Y-%m-%d').date()
            rows = [r for r in rows if r.get('date') and r['date']>=d1]
        except Exception: pass
    if fin_s:
        try:
            from datetime import datetime as dt
            d2 = dt.strptime(fin_s,'%Y-%m-%d').date()
            rows = [r for r in rows if r.get('date') and r['date']<=d2]
        except Exception: pass
    from core.commercial_engine import _annotate
    _annotate(rows)
    com_f = _get_user_filter()
    if com_f:
        rows = [r for r in rows if r.get('com_vente')==com_f]
    total_ca = sum(r.get('ca_amount',0) for r in rows)
    nb_fac   = sum(1 for r in rows if r.get('ca_amount',0)>0)
    return jsonify({'ok':True,'total_ca':round(total_ca,2),
                    'nb_factures':nb_fac,'debut':debut_s,'fin':fin_s,
                    'source':data.get('source','')})


# ── Annees disponibles ────────────────────────────────────────────────────────

@bp.route('/api/commercial/years')
@login_required
def api_years():
    data = _load_data()
    if not data: return jsonify({'ok':True,'years':[]})
    return jsonify({'ok':True,'years':data.get('years',[])})


# ── Clients ───────────────────────────────────────────────────────────────────

@bp.route('/api/commercial/clients', methods=['GET','POST'])
@login_required
def api_clients():
    if request.method == 'POST':
        d    = request.get_json() or {}
        code = d.get('code_client','').strip()
        nom  = d.get('nom','').strip()
        if not code or not nom:
            return jsonify({'ok':False,'msg':'Code et nom obligatoires'})
        db_exec(
            "INSERT OR REPLACE INTO fiches_clients(code_client,nom,prenom,telephone,"
            "telephone2,email,adresse,ville,secteur,commercial_attitree,"
            "plafond_credit,delai_paiement) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (code,nom,d.get('prenom',''),d.get('telephone',''),
             d.get('telephone2',''),d.get('email',''),d.get('adresse',''),
             d.get('ville',''),d.get('secteur',''),d.get('commercial_attitree',''),
             float(d.get('plafond_credit',0)),int(d.get('delai_paiement',30))))
        return jsonify({'ok':True})
    q   = request.args.get('q','')
    sql = "SELECT * FROM fiches_clients WHERE actif=1"
    p   = []
    if q:
        sql += " AND (nom LIKE ? OR code_client LIKE ? OR telephone LIKE ?)"
        p   += ['%'+q+'%','%'+q+'%','%'+q+'%']
    sql += " ORDER BY nom LIMIT 100"
    return jsonify({'ok':True,'clients':db_all(sql,p)})


# ── Objectifs ─────────────────────────────────────────────────────────────────

@bp.route('/api/commercial/objectifs', methods=['GET','POST'])
@login_required
def api_objectifs():
    if request.method == 'POST':
        d = request.get_json() or {}
        db_exec(
            "INSERT OR REPLACE INTO objectifs_commerciaux(commercial,periode,"
            "objectif_ca,objectif_recouvrement,objectif_nb_clients) VALUES(?,?,?,?,?)",
            (d.get('commercial',''),d.get('periode',''),
             float(d.get('objectif_ca',0)),float(d.get('objectif_recouvrement',0)),
             int(d.get('objectif_nb_clients',0))))
        return jsonify({'ok':True})
    return jsonify({'ok':True,'objectifs':db_all(
        "SELECT * FROM objectifs_commerciaux ORDER BY periode DESC")})

# compatibilite ancienne route
from datetime import date
