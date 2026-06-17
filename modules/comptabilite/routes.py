"""
NEXORA v2.0 — Module Comptabilite & Finance
Toutes les regles metier de GTC ERP PILOT V3.
Grand Livre + Creances 6 onglets avec regles exactes.
"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_exec
import logging
from datetime import date
from collections import defaultdict

log = logging.getLogger('NEXORA.Comptabilite')


def _get_user_filter():
    u = get_user()
    if u.get('role') == 'commercial' and u.get('commercial_name'):
        return u['commercial_name']
    return None


def _filter_by_agence_if_needed(rows, key_commercial='commercial'):
    """Si l'utilisateur a le role 'agence', filtre sur les commerciaux de son agence."""
    u = get_user()
    if u.get('role') != 'agence' or not u.get('agence'):
        return rows
    from core.commercial_engine import _norm
    ag_rows = db_all(
        "SELECT commercial_name FROM utilisateurs WHERE agence=? AND role='commercial' AND actif=1",
        (u['agence'],))
    ag_coms = {_norm(r['commercial_name']) for r in ag_rows if r['commercial_name']}
    if not ag_coms:
        return rows
    return [r for r in rows if _norm(r.get(key_commercial,'')) in ag_coms]


def _periode_from_request():
    """
    Lit la periode d'analyse depuis les parametres URL, fidele a la barre
    globale Annee/Mois/Du-Au de GTC ERP PILOT V3. Supporte annee+mois
    (dropdowns), du+au (plage exacte) ou debut/fin (alias retrocompatible).
    Identique a la logique du module Commercial : sans cette resolution
    centralisee, Grand Livre et Creances affichent des montants differents
    de ceux du Cockpit/Classement pour la "meme" periode.
    """
    from core.commercial_engine import resolve_period
    debut, fin, label = resolve_period(request.args)
    return debut, fin


def _load_data(force=False, debut=None, fin=None):
    from core.data_source import load_grand_livre_data
    from core.commercial_engine import init_commerciaux, compute_all
    all_rows, ref, coms = load_grand_livre_data(force=force)
    if not all_rows: return None
    init_commerciaux(coms)
    data = compute_all(all_rows, ref, start_date=debut, end_date=fin)
    data['source'] = get_config('source','sql').upper()
    return data


@bp.route('/module/comptabilite')
@login_required
def module_comptabilite():
    user    = get_user()
    modules = session.get('modules',[])
    cfg     = {'nom_societe': get_config('nom_societe',''),
               'devise':      get_config('devise','XAF')}
    from core.auth import get_allowed_subtabs
    allowed = get_allowed_subtabs(user.get('role','admin'), 'comptabilite')
    return render_template('modules/comptabilite.html',
        module='comptabilite', module_label='Comptabilite & Finance',
        user=user, modules=modules, config=cfg, tree=PERMISSIONS_TREE,
        allowed_subtabs=allowed)


# ── Grand Livre ───────────────────────────────────────────────────────────────

@bp.route('/api/comptabilite/grand-livre')
@login_required
def api_grand_livre():
    """
    Grand Livre complet avec toutes les colonnes de GTC ERP PILOT V3.
    16 colonnes : Code, Nom, Date, Jnl, Piece, Libelle,
                  Debit, Credit, Solde D, Solde C,
                  Statut, Non Solde, Echeance, J.Ret., Commercial, Type
    Coloration : rouge si retard > 30j, orange si retard > 0j.
    Filtre : recherche + commercial + type.
    """
    force  = request.args.get('force','0')=='1'
    q      = request.args.get('q','').lower()
    com_f_url = request.args.get('commercial','')
    type_f = request.args.get('type','')
    from core.commercial_engine import resolve_period
    debut, fin, period_label = resolve_period(request.args)
    data   = _load_data(force=force, debut=debut, fin=fin)
    if not data:
        return jsonify({'ok':True,'lignes':[],'nb':0,'message':'Sage/Excel non disponible'})
    grand = data['grand']
    com_f_user = _get_user_filter()
    com_f = com_f_user or com_f_url
    if com_f:
        grand = [r for r in grand if r['commercial']==com_f]
    grand = _filter_by_agence_if_needed(grand, 'commercial')
    if type_f:
        grand = [r for r in grand if r['type']==type_f]
    if q:
        grand = [r for r in grand if
                 q in (r['code']+r['nom']+r.get('facture','')+r['libelle']+r['commercial']).lower()]
    def _ser(r):
        # Coloration selon retard (rules metier)
        retard  = r['retard'] or 0
        couleur = 'red'    if retard>30 else \
                  'orange' if retard>0  else \
                  'total'  if r['is_total'] else ''
        return {
            'code':       r['code'],
            'nom':        r['nom'],
            'zone':       r.get('zone',''),
            'date':       str(r['date']) if r['date'] else '',
            'journal':    r['journal'],
            'piece':      r['piece'],
            'libelle':    r['libelle'],
            'debit':      round(r['debit'],2),
            'credit':     round(r['credit'],2),
            'solde_d':    round(r['solde_d'],2),
            'solde_c':    round(r['solde_c'],2),
            'statut':     r['statut'],
            'ouvert':     round(r['ouvert'],2),
            'echeance':   str(r['echeance']) if r['echeance'] else '',
            'retard':     retard,
            'commercial': r['commercial'],
            'type':       r['type'],
            'is_total':   r['is_total'],
            'couleur':    couleur,
        }
    lignes = [_ser(r) for r in grand]
    coms   = sorted(set(r['commercial'] for r in grand if r['commercial']))
    tot_d  = sum(r['debit']   for r in grand if not r['is_total'])
    tot_c  = sum(r['credit']  for r in grand if not r['is_total'])
    tot_s  = sum(r['solde_d'] for r in grand if r['is_total'])
    return jsonify({
        'ok':           True,
        'lignes':       lignes,
        'nb':           len(lignes),
        'commerciaux':  coms,
        'total_debit':  round(tot_d,2),
        'total_credit': round(tot_c,2),
        'total_solde':  round(tot_s,2),
        'periode':      {'debut': str(debut), 'fin': str(fin)},
        'period_label': period_label,
    })


# ── Créances (6 onglets) ──────────────────────────────────────────────────────

@bp.route('/api/comptabilite/creances')
@login_required
def api_creances():
    """
    Rapport Creances — 6 onglets avec regles exactes de GTC ERP PILOT V3.
    Global | Aging | Zones | Commerciaux | Clients (tri FNS) | Priorite
    Coloration : rouge si retard > 30j, orange si retard > 0j.
    Score priorite = retard x 2 + fns / 1000.
    """
    force    = request.args.get('force','0')=='1'
    q        = request.args.get('q','').lower()
    zone_f   = request.args.get('zone','')
    ret_only = request.args.get('retard_only','0')=='1'
    from core.commercial_engine import resolve_period
    debut, fin, period_label = resolve_period(request.args)
    data     = _load_data(force=force, debut=debut, fin=fin)
    if not data:
        return jsonify({'ok':True,'clients':[],'nb':0,'message':'Sage/Excel non disponible'})
    creances = data['creances']
    com_f    = _get_user_filter()
    if com_f:
        creances = [c for c in creances if c['commercial']==com_f]
    creances = _filter_by_agence_if_needed(creances, 'commercial')
    # Filtres
    def _filtered(rows):
        out = []
        for r in rows:
            if ret_only and r['retard']<=0: continue
            if zone_f and r['zone']!=zone_f: continue
            if q and q not in (r['code']+r['nom']+r['zone']+r['commercial']).lower(): continue
            out.append(r)
        return out
    filtered = _filtered(creances)
    zones    = sorted(set(r['zone'] for r in creances if r['zone']))
    coms_lst = sorted(set(r['commercial'] for r in creances if r['commercial']))

    # ── Onglet Aging (tranches retard exactes) ──
    tranches = [
        ('Courant (0 j)',     lambda r: r['retard']==0 and r['fns']==0),
        ('1-30 jours',        lambda r: 0<r['retard']<=30),
        ('31-60 jours',       lambda r: 30<r['retard']<=60),
        ('61-90 jours',       lambda r: 60<r['retard']<=90),
        ('Plus de 90 jours',  lambda r: r['retard']>90),
    ]
    tot_fns = sum(r['fns'] for r in filtered) or 1
    aging   = []
    for lbl, fn in tranches:
        sub     = [r for r in filtered if fn(r)]
        montant = sum(r['fns'] for r in sub)
        aging.append({
            'tranche': lbl, 'nb': len(sub),
            'montant': round(montant,2),
            'pct':     round(montant/tot_fns*100,1),
            'couleur': 'red' if '90' in lbl else 'orange' if ('31' in lbl or '61' in lbl) else '',
        })

    # ── Onglet Zones ──
    z_agg = defaultdict(lambda:{'nb':0,'solde':0.,'fns':0.,'retard':0})
    for r in filtered:
        z = r['zone'] or 'N/A'
        z_agg[z]['nb']    += 1
        z_agg[z]['solde'] += r['solde']
        z_agg[z]['fns']   += r['fns']
        z_agg[z]['retard'] = max(z_agg[z]['retard'], r['retard'])
    par_zone = [{'zone':z,'nb':d['nb'],'solde':round(d['solde'],2),
                 'fns':round(d['fns'],2),'retard':d['retard'],
                 'couleur':'red' if d['retard']>30 else 'orange' if d['retard']>0 else ''}
                for z,d in sorted(z_agg.items(), key=lambda x:-x[1]['fns'])]

    # ── Onglet Commerciaux ──
    c_agg = defaultdict(lambda:{'nb':0,'solde':0.,'fns':0.,'retard':0,'mdp':0.})
    for r in filtered:
        c = r['commercial'] or 'N/A'
        c_agg[c]['nb']    += 1
        c_agg[c]['solde'] += r['solde']
        c_agg[c]['fns']   += r['fns']
        c_agg[c]['retard'] = max(c_agg[c]['retard'], r['retard'])
        c_agg[c]['mdp']   += r['mdp']
    par_com = [{'commercial':c,'nb':d['nb'],'solde':round(d['solde'],2),
                'fns':round(d['fns'],2),'retard':d['retard'],'mdp':round(d['mdp'],2),
                'couleur':'red' if d['retard']>30 else 'orange' if d['retard']>0 else ''}
               for c,d in sorted(c_agg.items(), key=lambda x:-x[1]['fns'])]

    # ── Onglet Clients (tri FNS décroissant) ──
    sorted_cl = sorted(filtered, key=lambda r:-r['fns'])
    par_clients= [{'rang':i+1,'code':r['code'],'nom':r['nom'],
                   'commercial':r['commercial'],'fns':round(r['fns'],2),
                   'retard':r['retard'],'solde':round(r['solde'],2),
                   'couleur':'red' if r['retard']>30 else 'orange' if r['retard']>0 else ''}
                  for i,r in enumerate(sorted_cl)]

    # ── Onglet Priorité (score = retard*2 + fns/1000) ──
    def _score(r):  return r['retard']*2 + r['fns']/1000
    def _prio(r):
        if r['retard']>60: return 'CRITIQUE'
        if r['retard']>30: return 'HAUTE'
        if r['retard']>0:  return 'MOYENNE'
        return 'BASSE'
    def _action(r):
        if r['retard']>60: return 'MISE EN DEMEURE'
        if r['retard']>30: return 'RELANCE URGENTE'
        if r['retard']>0:  return 'RELANCE'
        if r['mdp']>0:     return 'DEPASSEMENT PLAFOND'
        return 'SUIVI'
    sorted_p = sorted(filtered, key=_score, reverse=True)
    priorite = [{'priorite':_prio(r),'code':r['code'],'nom':r['nom'],
                 'commercial':r['commercial'],'fns':round(r['fns'],2),
                 'retard':r['retard'],'telephone':r['telephone'],
                 'action':_action(r),
                 'couleur':'red' if _prio(r)=='CRITIQUE' else 'orange' if _prio(r)=='HAUTE' else ''}
                for r in sorted_p if r['fns']>0 or r['retard']>0]

    # ── Totaux (avec les regles exactes de GTC ERP PILOT V3) ──
    ts    = round(sum(r['solde']  for r in filtered),2)
    tfnst = round(sum(r['fnstot'] for r in filtered),2)
    tf2   = round(sum(r['fns']    for r in filtered),2)
    tm    = round(sum(r['mdp']    for r in filtered if r['mdp']>0),2)

    # Clients serialises
    clients_out = []
    for r in filtered:
        clients_out.append({
            'code':       r['code'], 'nom': r['nom'],
            'zone':       r['zone'], 'commercial': r['commercial'],
            'solde':      round(r['solde'],2),
            'fnstot':     round(r['fnstot'],2),
            'fns':        round(r['fns'],2),
            'nf':         r['nf'], 'retard': r['retard'],
            'mdp':        round(r['mdp'],2),
            'plafond':    round(r['plafond'],2),
            'telephone':  r['telephone'],
            'couleur':    'red' if r['retard']>30 else 'orange' if r['retard']>0 else '',
        })

    return jsonify({
        'ok':             True,
        'clients':        clients_out,
        'nb':             len(filtered),
        'zones':          zones,
        'commerciaux':    coms_lst,
        'aging':          aging,
        'par_zone':       par_zone,
        'par_commercial': par_com,
        'par_clients':    par_clients,
        'priorite':       priorite,
        'totaux': {
            'solde':      ts,
            'fnstot':     tfnst,
            'fns_echu':   tf2,
            'depasses':   tm,
            'nb_clients': len(filtered),
        },
        'periode':      {'debut': str(debut), 'fin': str(fin)},
        'period_label': period_label,
        'periode': {'debut': str(debut), 'fin': str(fin)},
    })


# ── Evolution créances ────────────────────────────────────────────────────────

@bp.route('/api/comptabilite/evolution-creances')
@login_required
def api_evol_creances():
    from core.commercial_engine import resolve_period
    debut, fin, period_label = resolve_period(request.args)
    data = _load_data(debut=debut, fin=fin)
    if not data:
        return jsonify({'ok':True,'clients':[]})
    creances = data['creances']
    def _niveau(s):
        if s>500000: return 'CRITIQUE'
        if s>200000: return 'ELEVE'
        if s>50000:  return 'MOYEN'
        return 'FAIBLE'
    result = [{'code':c['code'],'nom':c['nom'],'commercial':c['commercial'],
               'solde':round(c['solde'],2),'fns':round(c['fns'],2),
               'fnstot':round(c['fnstot'],2),'retard':c['retard'],
               'niveau_risque':_niveau(c['solde'])}
              for c in creances[:50]]
    return jsonify({'ok':True,'clients':result,'period_label':period_label,
                    'periode':{'debut':str(debut),'fin':str(fin)}})


# ── Rapport de caisse ─────────────────────────────────────────────────────────

@bp.route('/api/comptabilite/rapport-caisse', methods=['GET','POST'])
@login_required
def api_rapport_caisse():
    if request.method == 'POST':
        d   = request.get_json() or {}
        uid = db_exec(
            "INSERT INTO rapports_caisse(date_rapport,commercial,agence,total_ventes,"
            "total_encaisse,total_credit,observations,statut,saisi_par) VALUES(?,?,?,?,?,?,?,?,?)",
            (d.get('date_rapport',''),d.get('commercial',''),
             d.get('agence','BERTOUA'),float(d.get('total_ventes',0)),
             float(d.get('total_encaisse',0)),float(d.get('total_credit',0)),
             d.get('observations',''),'brouillon',session.get('username','')))
        for l in d.get('lignes',[]):
            db_exec(
                "INSERT INTO lignes_rapport_caisse(rapport_id,no_facture,code_client,"
                "client_nom,montant_facture,montant_encaisse,mode_paiement) VALUES(?,?,?,?,?,?,?)",
                (uid,l.get('no_facture',''),l.get('code_client',''),
                 l.get('client_nom',''),float(l.get('montant_facture',0)),
                 float(l.get('montant_encaisse',0)),l.get('mode_paiement','ESPECES')))
        return jsonify({'ok':True,'id':uid})
    rows = db_all("SELECT * FROM rapports_caisse ORDER BY date_rapport DESC LIMIT 100")
    return jsonify({'ok':True,'rapports':rows})
