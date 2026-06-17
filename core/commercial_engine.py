"""
NEXORA v2.0 — Moteur Commercial & Comptabilite
Toutes les regles metier de GTC ERP PILOT V3 portees fidelement.
Fonctionne en Python pur, sans dependance tkinter.
"""
import re, unicodedata, logging
from datetime import date, datetime, timedelta
from collections import defaultdict

log = logging.getLogger('NEXORA.Engine')

# ── Utilitaires ───────────────────────────────────────────────────────────────

def _txt(v):   return '' if v is None else str(v).strip()
def _up(v):    return _txt(v).upper()

def _num(v):
    try:
        if v is None or v == '': return 0.0
        if isinstance(v, str):
            v = v.replace(' ','').replace('\xa0','').replace(',','.')
        return float(v)
    except: return 0.0

def _to_date(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date):     return v
    if isinstance(v, (int, float)) and v > 20000:
        try: return (datetime(1899,12,30) + timedelta(days=float(v))).date()
        except: pass
    s = _txt(v).replace('\xa0',' ').strip()
    if not s: return None
    first = s.split(' ')[0].strip()
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d','%d/%m/%y'):
        try: return datetime.strptime(first, fmt).date()
        except: pass
    return None

def _norm(v):
    s = _txt(v).upper()
    s = ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn')
    return ' '.join(s.replace('_',' ').split())

def _parse_date_str(s):
    s = _txt(s).strip()
    for fmt in ('%d/%m/%Y','%Y-%m-%d','%d-%m-%Y'):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    return None

# ── Référentiel commerciaux ───────────────────────────────────────────────────

_OFF_BY_NORM = {}
_OFF_ORDER   = []
_OFF_OBJ     = {}
AUTRE        = 'AUTRE CLIENT'

def init_commerciaux(liste):
    global _OFF_BY_NORM, _OFF_ORDER, _OFF_OBJ
    _OFF_BY_NORM = {}; _OFF_ORDER = []; _OFF_OBJ = {}
    for nom, obj in liste:
        n = _txt(nom); k = _norm(n)
        if not n or k in {'COMMERCIAL','TOTAL','OBJECTIF','AUTRE CLIENT'}: continue
        if k in _OFF_BY_NORM: continue
        _OFF_ORDER.append(n)
        _OFF_BY_NORM[k] = n
        _OFF_OBJ[k]     = _num(obj)

def _is_vc(v): return _norm(v) == _norm('VENTE COMPTANT')

def _com_cockpit(raw_name):
    """Retourne le nom officiel du commercial (casse originale) ou AUTRE."""
    k   = _norm(raw_name)
    if not k: return AUTRE
    off = _OFF_BY_NORM.get(k)
    return off if off and not _is_vc(off) else AUTRE

def _com_ca_valide(name):
    """Retourne le nom officiel pour le CA (exclut VENTE COMPTANT, etc.)."""
    raw = _txt(name); k = _norm(raw)
    if not k or k in {'A COMPLETER','COMPTABILITE','COMPTA',
                      'AUTRE CLIENT','VENTE COMPTANT','SANS REPRESENTANT'}: return ''
    off = _OFF_BY_NORM.get(k)
    if off and _norm(off) not in {'VENTE COMPTANT'}: return off
    return raw

def _obj(com):        return _OFF_OBJ.get(_norm(com), 0)
def _obj_by_norm(com): return _OFF_OBJ.get(_norm(_txt(com)), 0)

# ── Détection type de mouvement ───────────────────────────────────────────────

def _detect_type(journal, reference, facture, libelle, debit, credit):
    j   = _up(journal); fac = _up(facture)
    txt = _norm(f"{j} {reference} {fac} {_up(libelle)}")
    if j == 'RAN':                                         return 'REPORT'
    if credit > 0 and debit == 0:                         return 'REGLEMENT'
    if re.search(r'\bBS\b', txt) or fac.startswith('BS'): return 'BS'
    if debit > 0:
        if fac.startswith('FVC') or 'AVOIR' in txt:       return 'AVOIR'
        if fac.startswith('FRC') or 'RETOUR' in txt:      return 'RETOUR'
    if j == 'VTE' and debit > 0:                          return 'FACTURE'
    if debit > 0:                                          return 'FACTURE'
    return 'AUTRE'

def _piece(ref, fac, debit, credit):
    if credit > 0 and debit == 0: return _txt(ref) or _txt(fac)
    return _txt(fac) or _txt(ref)

def _is_vt(reference):
    ref = _up(reference)
    return 'EN COMPTE' in ref or ref.startswith('BP') or '/BP' in ref

def _is_fns_type(t, d):
    return d > 0 and t in {'FACTURE','VENTE','RETOUR','AVOIR','BS',
                            'DEBIT_CLIENT','REPORT','AUTRE'}

# ── Mapping colonnes Excel / SQL ──────────────────────────────────────────────

_IMPORT_ALIASES = {
    'Code_Client':  {'CODE CLIENT','CODE','CT NUM','COMPTE CLIENT'},
    'Nom_Client':   {'NOM CLIENT','NOM','CLIENT','CT INTITULE'},
    'Date':         {'DATE','EC DATE','DATE ECRITURE'},
    'Journal':      {'JOURNAL','C J','CJ','JO NUM'},
    'Reference':    {'REFERENCE','REFERENCES','EC REFERENCE','REF'},
    'N_Facture':    {'N FACTURE','NO FACTURE','FACTURE','EC REFPIECE',
                     'EC REF PIECE','N FACTURES','N FACT','NUMERO FACTURE'},
    'Libelle':      {'LIBELLE','LIBELLE ECRITURE','EC INTITULE','INTITULE'},
    'Debit':        {'DEBIT','MONTANT DEBIT','MONTANT DEB'},
    'Credit':       {'CREDIT','MONTANT CREDIT','MONTANT CRED'},
    'Representant': {'REPRESENTANT','REPRESENTANT COMMERCIAL','VENDEUR','REP'},
}

def _norm_hdr(v):
    s = _txt(v).upper()
    s = ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn')
    s = s.replace('°',' ').replace('N°','N ').replace('Nº','N ')
    return ' '.join(re.sub(r'[^A-Z0-9]+',' ',s).split())

def _find_map(header_row):
    norm = [_norm_hdr(v) for v in header_row]
    m    = {}
    for tgt, aliases in _IMPORT_ALIASES.items():
        for i, h in enumerate(norm):
            if h in aliases:
                m[tgt] = i; break
    return m

# ── Filtrage par période ──────────────────────────────────────────────────────

def filter_rows(all_rows, start_date=None, end_date=None, mode='between'):
    """
    mode='between' : start_date <= date <= end_date
    mode='upto'    : date <= end_date (inclut RAN)
    """
    if not start_date and not end_date: return all_rows
    out = []
    for r in all_rows:
        d = r.get('date')
        if not isinstance(d, date):
            if mode == 'upto': out.append(r)
            continue
        if mode == 'between':
            if start_date and d < start_date: continue
            if end_date   and d > end_date:   continue
        else:
            if end_date and d > end_date: continue
        out.append(r)
    return out

# ── Construction des données brutes ──────────────────────────────────────────

def build_raw_from_sql(sql_rows, ref):
    """
    Construit les lignes brutes depuis les rows SQL (format dict depuis sage_connector).
    sql_rows : liste de dicts (colonnes SQL)
    """
    if not sql_rows: return []
    out = []
    for row in sql_rows:
        code = _txt(row.get('Code_Client') or row.get('code_client',''))
        if not code: continue
        debit   = _num(row.get('Debit')   or row.get('debit',  0))
        credit  = _num(row.get('Credit')  or row.get('credit', 0))
        journal = _txt(row.get('Journal') or row.get('journal',''))
        ref_val = _txt(row.get('Reference') or row.get('reference',''))
        facture = _txt(row.get('N_Facture') or row.get('n_facture',''))
        libelle = _txt(row.get('Libelle')   or row.get('libelle',''))
        repres  = _txt(row.get('Representant') or row.get('representant',''))
        info    = ref.get(code,{})
        d_val   = row.get('Date') or row.get('date')
        out.append({
            'code':        code,
            'nom':         info.get('nom','') or _txt(row.get('Nom_Client') or row.get('nom_client','')),
            'date':        _to_date(d_val),
            'journal':     journal,
            'reference':   ref_val,
            'facture':     facture,
            'libelle':     libelle,
            'debit':       debit,
            'credit':      credit,
            'type':        _detect_type(journal, ref_val, facture, libelle, debit, credit),
            'piece':       _piece(ref_val, facture, debit, credit),
            'representant': repres,
            'commercial':  info.get('commercial','A COMPLETER') or 'A COMPLETER',
            'com_source':  info.get('com_source',''),
            'zone':        info.get('zone',''),
            'ca_amount':   0,
            'com_vente':   '',
        })
    out.sort(key=lambda x: (x['code'], x['date'] or date(1900,1,1),
                             0 if (x['credit']>0 and x['debit']==0) else 1, x['facture']))
    return out

def build_raw_from_excel(import_rows, ref):
    """
    Construit les lignes brutes depuis les rows Excel (listes/tuples).
    import_rows[0] = en-tête, import_rows[1:] = données
    """
    if not import_rows: return []
    header  = list(import_rows[0])
    mapping = _find_map(header)
    out     = []
    for row in import_rows[1:]:
        if not row: continue
        def g(col, dflt=''):
            p = mapping.get(col)
            return row[p] if p is not None and p < len(row) else dflt
        code = _txt(g('Code_Client'))
        if not code: continue
        debit   = _num(g('Debit'));   credit  = _num(g('Credit'))
        journal = _txt(g('Journal')); ref_val = _txt(g('Reference'))
        facture = _txt(g('N_Facture')); libelle = _txt(g('Libelle'))
        repres  = _txt(g('Representant'))
        info    = ref.get(code,{})
        out.append({
            'code':        code,
            'nom':         info.get('nom','') or _txt(g('Nom_Client')),
            'date':        _to_date(g('Date')),
            'journal':     journal,
            'reference':   ref_val,
            'facture':     facture,
            'libelle':     libelle,
            'debit':       debit,
            'credit':      credit,
            'type':        _detect_type(journal, ref_val, facture, libelle, debit, credit),
            'piece':       _piece(ref_val, facture, debit, credit),
            'representant': repres,
            'commercial':  info.get('commercial','A COMPLETER') or 'A COMPLETER',
            'com_source':  info.get('com_source',''),
            'zone':        info.get('zone',''),
            'ca_amount':   0,
            'com_vente':   '',
        })
    out.sort(key=lambda x: (x['code'], x['date'] or date(1900,1,1),
                             0 if (x['credit']>0 and x['debit']==0) else 1, x['facture']))
    return out

def _annotate(rows):
    """
    Calcule ca_amount et com_vente pour chaque ligne.
    Regle : factures commencant par F, excluant FVC et FRC.
    """
    for r in rows:
        r['ca_amount'] = 0; r['com_vente'] = ''
        if _up(r.get('journal','')) == 'RAN': continue
        fac = _up(r.get('facture',''))
        if not fac.startswith('F'): continue
        if fac.startswith('FVC') or fac.startswith('FRC'): continue
        r['ca_amount'] = _num(r.get('debit',0))
        cv = _com_ca_valide(r.get('representant','')) or AUTRE
        r['com_vente'] = cv

# ── Grand Livre avec soldes et échéances ──────────────────────────────────────

def build_grand_livre(rows_balance, ref, analysis_date=None):
    """
    Construit le Grand Livre enrichi.
    Regles :
    - Solde cumule par client
    - Factures Non Soldees vs Soldees (du plus recent au plus ancien)
    - Echeance = date_facture + delai_paiement_client
    - Retard = max(0, aujourd'hui - echeance) en jours
    - Ligne TOTAL par client en fin
    """
    today   = analysis_date if isinstance(analysis_date, date) else date.today()
    grouped = defaultdict(list)
    for r in rows_balance: grouped[r['code']].append(r)
    grand   = []
    for code, rows in grouped.items():
        info  = ref.get(code,{})
        nom   = info.get('nom','') or (rows[0]['nom'] if rows else '')
        com   = info.get('commercial','A COMPLETER') or 'A COMPLETER'
        zone  = info.get('zone','')
        delai = int(_num(info.get('delai',30)) or 30)
        tot_d = tot_c = solde = 0
        idxs  = []
        for r in rows:
            tot_d += r['debit'];  tot_c += r['credit']
            solde += r['debit'] - r['credit']
            grand.append({
                'code':      code, 'nom': nom, 'zone': zone,
                'date':      r['date'], 'journal': r['journal'],
                'reference': r['reference'], 'facture': r['facture'],
                'libelle':   r['libelle'],
                'debit':     r['debit'],  'credit': r['credit'],
                'solde_d':   max(0, solde), 'solde_c': max(0, -solde),
                'statut':    '', 'ouvert': 0, 'echeance': None, 'retard': 0,
                'commercial':com, 'type': r['type'], 'piece': r['piece'],
                'com_vente': r.get('com_vente',''),
                'representant': r.get('representant',''),
                'is_total':  False,
            })
            idxs.append(len(grand)-1)
        # Calculer FNS (du plus recent au plus ancien)
        reste = solde if solde > 0 else 0
        for idx in reversed(idxs):
            d2 = grand[idx]['debit']; t2 = grand[idx]['type']
            if reste > 0 and _is_fns_type(t2, d2):
                ouv = min(d2, reste)
                if ouv > 0:
                    grand[idx]['statut']   = 'Non Soldee'
                    grand[idx]['ouvert']   = ouv
                    dt = grand[idx]['date']
                    if isinstance(dt, date):
                        ech = dt + timedelta(days=delai)
                        grand[idx]['echeance'] = ech
                        grand[idx]['retard']   = max(0, (today - ech).days)
                    reste -= ouv
                else:
                    grand[idx]['statut'] = 'Soldee'
            elif _is_fns_type(t2, d2):
                grand[idx]['statut'] = 'Soldee'
        # Ligne totale
        grand.append({
            'code': code, 'nom': nom, 'zone': zone,
            'date': None, 'journal': 'TOTAL',
            'reference': '', 'facture': '', 'libelle': 'TOTAL CLIENT',
            'debit': tot_d, 'credit': tot_c,
            'solde_d': max(0, solde), 'solde_c': max(0, -solde),
            'statut': 'Non Soldee' if solde > 0 else 'Soldee',
            'ouvert': max(0, solde), 'echeance': None, 'retard': 0,
            'commercial': com, 'type': 'TOTAL', 'piece': '',
            'com_vente': '', 'representant': '', 'is_total': True,
        })
    return grand

# ── Créances ──────────────────────────────────────────────────────────────────

def build_creances(grand, ref):
    """
    Construit la liste des creances par client.
    fns    = creances echues (retard > 0)
    fnstot = toutes les factures non soldees (retard >= 0)
    mdp    = depassement plafond credit
    """
    g2 = defaultdict(lambda: {'solde':0.,'fns':0.,'fnstot':0.,'nf':0,'retard':0,'mdp':0.})
    for r in grand:
        code = r['code']; g = g2[code]
        if r['is_total']:
            g['solde'] = r['solde_d'] - r['solde_c']
            pl         = _num(ref.get(code,{}).get('plafond',0))
            g['mdp']   = max(0, g['solde'] - pl) if pl > 0 else 0
        else:
            if r['ouvert'] > 0:
                g['nf']     += 1
                g['fnstot'] += r['ouvert']
                if r['retard'] > 0:
                    g['fns']   += r['ouvert']
                    g['retard'] = max(g['retard'], r['retard'])
    out = []
    for code, g in g2.items():
        if g['solde'] == 0 and g['fns'] == 0 and g['fnstot'] == 0: continue
        info = ref.get(code,{})
        nom  = info.get('nom','')
        if not nom:
            for r in grand:
                if r['code'] == code and r['nom']:
                    nom = r['nom']; break
        out.append({
            'code':       code, 'nom': nom,
            'zone':       info.get('zone',''),
            'commercial': info.get('commercial',''),
            'solde':      g['solde'], 'fns': g['fns'],
            'fnstot':     g['fnstot'], 'nf': g['nf'],
            'retard':     g['retard'], 'mdp': g['mdp'],
            'plafond':    _num(info.get('plafond',0)),
            'telephone':  info.get('telephone',''),
            'risque':     (g['fns']/g['solde']*100) if g['solde'] else 0,
        })
    return out

# ── KPIs globaux ──────────────────────────────────────────────────────────────

def build_kpis(rows_period, creances):
    """
    KPIs globaux reseau.
    Regles :
    - CA = somme des ca_amount > 0 (factures uniquement, hors FVC/FRC)
    - Recouvrement = somme des credit > 0 quand debit = 0 (hors RAN)
    - FNS = somme des creances echues
    - Nb retard = nb clients avec retard > 0
    """
    ca    = sum(r.get('ca_amount',0) for r in rows_period if r.get('ca_amount',0)>0)
    rec   = sum(r['credit'] for r in rows_period
                if r['credit']>0 and r['debit']==0 and _up(r.get('journal',''))!='RAN')
    fns   = sum(c['fns']   for c in creances)
    nbret = sum(1 for c in creances if c['retard']>0)
    solde = sum(c['solde'] for c in creances if c['solde']>0)
    nb_cl = len(set(r['code'] for r in rows_period))
    return {
        'ca': ca, 'recouvrement': rec, 'fns': fns,
        'nb_retard': nbret, 'solde': solde, 'nb_clients': nb_cl,
        'taux_rec': (rec/ca*100) if ca>0 else 0,
    }

# ── Alertes ───────────────────────────────────────────────────────────────────

def build_alertes(creances):
    """
    Regles alertes :
    - CRITIQUE : retard >= 30j
    - ALERTE   : depassement plafond
    - SUIVI    : FNS > 0
    """
    out = []
    for c in creances:
        if c['retard'] >= 30:
            out.append({'niveau':'CRITIQUE','code':c['code'],'nom':c['nom'],
                        'fns':c['fns'],'retard':c['retard'],'msg':'Retard > 30 jours'})
        elif c['mdp'] > 0:
            out.append({'niveau':'ALERTE','code':c['code'],'nom':c['nom'],
                        'fns':c['fns'],'retard':c['retard'],'msg':'Depassement plafond'})
        elif c['fns'] > 0:
            out.append({'niveau':'SUIVI','code':c['code'],'nom':c['nom'],
                        'fns':c['fns'],'retard':c['retard'],'msg':'Factures non soldees'})
    return out

# ── Classement des commerciaux ────────────────────────────────────────────────

def build_classement(rows_period, creances):
    """
    Score = 40% pct_obj + 25% taux_rec + 20% pct_ca + 15% (1-risque)
    Exclure VENTE COMPTANT.
    Coloration : or si >= 100% obj, rouge si < 50%.
    """
    ca_c   = defaultdict(float); rec_c = defaultdict(float)
    tot_ca = sum(r.get('ca_amount',0) for r in rows_period if r.get('ca_amount',0)>0) or 1
    for r in rows_period:
        if r.get('ca_amount',0) > 0:
            ca_c[r.get('com_vente') or AUTRE] += r['ca_amount']
        elif r['credit']>0 and r['debit']==0 and _up(r.get('journal',''))!='RAN':
            rec_c[_com_cockpit(r.get('commercial',''))] += r['credit']
    fns_c  = defaultdict(float)
    ret_c  = defaultdict(set)
    for c in creances:
        com = _com_cockpit(c.get('commercial',''))
        fns_c[com] += c['fns']
        if c['retard'] > 0: ret_c[com].add(c['code'])
    all_c = set(ca_c) | set(rec_c) | set(_OFF_ORDER)
    rows  = []
    for com in all_c:
        if _is_vc(com): continue
        ca    = ca_c.get(com,0); rec = rec_c.get(com,0)
        fns   = fns_c.get(com,0); obj = _obj(com)
        pct_obj  = (ca/obj)    if obj>0 else 0
        taux_rec = (rec/ca)    if ca>0  else 0
        risque   = (fns/ca)    if ca>0  else 0
        pct_ca   = ca/tot_ca
        score    = (min(1,pct_obj)*0.40 + min(1,taux_rec)*0.25 +
                    min(1,pct_ca)*0.20  + max(0,1-min(1,risque))*0.15)
        rows.append({
            'commercial':   com,
            'ca':           ca, 'recouvrement': rec, 'fns': fns,
            'nb_retard':    len(ret_c.get(com,set())),
            'objectif':     obj, 'pct_obj': pct_obj,
            'taux_rec':     taux_rec, 'risque': risque,
            'score':        score,
        })
    rows.sort(key=lambda x: x['score'], reverse=True)
    for i,r in enumerate(rows,1): r['rang'] = i
    return rows

# ── Cockpit d'un commercial ───────────────────────────────────────────────────

def build_cockpit_com(com, data):
    """
    12 KPIs pour un commercial.
    com : nom officiel (casse originale)
    data : dict complet depuis compute_all()
    """
    raw    = data.get('raw',    [])
    raw_bal= data.get('raw_bal',[])
    cre    = data.get('creances',[])
    ref    = data.get('ref',   {})
    ca     = sum(r.get('ca_amount',0) for r in raw
                 if r.get('com_vente')==com and r.get('ca_amount',0)>0)
    rec    = sum(r['credit'] for r in raw
                 if r['credit']>0 and r['debit']==0
                 and _com_cockpit(r.get('commercial',''))==com
                 and _up(r.get('journal',''))!='RAN')
    fns    = sum(c['fns']   for c in cre if _com_cockpit(c.get('commercial',''))==com)
    solde  = sum(c['solde'] for c in cre if _com_cockpit(c.get('commercial',''))==com and c['solde']>0)
    obj    = _obj(com); pct = (ca/obj*100) if obj>0 else 0
    nb_ret = sum(1 for c in cre if _com_cockpit(c.get('commercial',''))==com and c['retard']>0)
    nb_cl  = len(set(r['code'] for r in raw
                     if r.get('com_vente')==com or _com_cockpit(r.get('commercial',''))==com))
    mdp    = sum(c['mdp'] for c in cre if _com_cockpit(c.get('commercial',''))==com and c['mdp']>0)
    taux_rec   = (rec/ca*100)    if ca>0    else 0
    taux_risque= (fns/solde*100) if solde>0 else 0
    nb_fac = sum(1 for r in raw if r.get('com_vente')==com and r.get('ca_amount',0)>0)
    # Répartition comptant vs terme
    ca_cpt = sum(r.get('ca_amount',0) for r in raw
                 if r.get('com_vente')==com and r.get('ca_amount',0)>0
                 and not _is_vt(r.get('reference','')))
    ca_ter = sum(r.get('ca_amount',0) for r in raw
                 if r.get('com_vente')==com and r.get('ca_amount',0)>0
                 and _is_vt(r.get('reference','')))
    # Top clients CA
    ca_by_code = defaultdict(float)
    for r in raw:
        if r.get('com_vente')==com and r.get('ca_amount',0)>0:
            ca_by_code[r['code']] += r['ca_amount']
    top_clients = sorted(ca_by_code.items(), key=lambda x: -x[1])[:10]
    return {
        'commercial': com,
        'ca': ca, 'obj': obj, 'pct_obj': pct,
        'recouvrement': rec, 'fns': fns, 'solde': solde,
        'nb_retard': nb_ret, 'nb_clients': nb_cl, 'mdp': mdp,
        'taux_rec': taux_rec, 'taux_risque': taux_risque,
        'nb_fac': nb_fac,
        'ca_comptant': ca_cpt, 'ca_terme': ca_ter,
        'top_clients': [{'code':c,'ca':v} for c,v in top_clients],
        'rang': 0,  # rempli par build_classement
    }

# ── Statut client (pour cockpit) ──────────────────────────────────────────────

def client_statut(c):
    """
    Retourne (label, couleur, icone, action) selon la situation du client.
    Regles :
    A RISQUE  : retard >= 60j OU depassement plafond
    ATTENTION : retard >= 30j OU FNS > 0
    BON CLIENT: solde > 0 ET FNS = 0
    SOLDE OK  : solde <= 0
    NORMAL    : autres cas
    """
    retard = c.get('retard',0); fns = c.get('fns',0)
    solde  = c.get('solde',0);  mdp = c.get('mdp',0)
    if retard >= 60 or mdp > 0:
        return ('A RISQUE',   '#E74C3C', '🔴', 'Relancer immediatement. Bloquer livraisons si necessaire.')
    elif retard >= 30 or fns > 0:
        return ('ATTENTION',  '#F39C12', '🟠', 'Contacter le client. Verifier engagement de paiement.')
    elif solde > 0 and fns == 0:
        return ('BON CLIENT', '#27AE60', '🟢', 'Maintenir la relation. Envisager augmentation du plafond.')
    elif solde <= 0:
        return ('SOLDE OK',   '#3498DB', '🔵', 'Suivi standard. Aucune action urgente.')
    else:
        return ('NORMAL',     '#8BA3CC', '⚪', 'Suivi standard. Verifier paiement a la prochaine echeance.')

# ── Copilote quotidien (assistance commercial au jour le jour) ───────────────

def build_copilote_quotidien(com, raw, objectif_mensuel=0, today=None):
    """
    Construit les donnees d'assistance quotidienne pour un commercial.
    Regle metier : le copilote suit la progression jour par jour vers
    l'objectif du mois en cours et indique le rythme necessaire pour
    l'atteindre.

    com              : nom officiel du commercial
    raw              : lignes brutes (data['raw']) deja annotees (ca_amount/com_vente)
    objectif_mensuel : objectif CA du mois en cours (0 si inconnu -> pas de calcul de rythme)
    today            : date du jour (injectable pour les tests), sinon date.today()
    """
    import calendar
    today = today or date.today()
    debut_mois = today.replace(day=1)
    hier       = today - timedelta(days=1)

    ca_par_jour = defaultdict(float)
    for r in raw:
        if r.get('com_vente') != com or r.get('ca_amount', 0) <= 0:
            continue
        d = r.get('date')
        if isinstance(d, date) and d >= debut_mois:
            ca_par_jour[d] += r['ca_amount']

    ca_aujourdhui = ca_par_jour.get(today, 0.0)
    ca_hier       = ca_par_jour.get(hier, 0.0)
    ca_mois       = sum(v for d, v in ca_par_jour.items() if d <= today)

    variation_jour = None
    if ca_hier > 0:
        variation_jour = (ca_aujourdhui - ca_hier) / ca_hier * 100

    nb_jours_mois     = calendar.monthrange(today.year, today.month)[1]
    jours_ecoules     = today.day
    jours_restants    = max(0, nb_jours_mois - jours_ecoules)
    reste_a_vendre    = max(0.0, objectif_mensuel - ca_mois) if objectif_mensuel > 0 else 0.0
    rythme_necessaire = (reste_a_vendre / jours_restants) if jours_restants > 0 else reste_a_vendre
    rythme_actuel_moy = (ca_mois / jours_ecoules) if jours_ecoules > 0 else 0.0
    pct_objectif_mois = (ca_mois / objectif_mensuel * 100) if objectif_mensuel > 0 else 0.0
    pct_temps_ecoule  = (jours_ecoules / nb_jours_mois * 100) if nb_jours_mois > 0 else 0.0

    # Statut d'avancement: en avance si pct CA > pct temps ecoule
    if objectif_mensuel <= 0:
        statut = 'SANS_OBJECTIF'
    elif pct_objectif_mois >= 100:
        statut = 'OBJECTIF_ATTEINT'
    elif pct_objectif_mois >= pct_temps_ecoule:
        statut = 'EN_AVANCE'
    elif pct_objectif_mois >= pct_temps_ecoule * 0.8:
        statut = 'DANS_LES_TEMPS'
    else:
        statut = 'EN_RETARD'

    historique_7j = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        historique_7j.append({'date': str(d), 'ca': round(ca_par_jour.get(d, 0.0), 2)})

    return {
        'date_jour':          str(today),
        'ca_aujourdhui':      round(ca_aujourdhui, 2),
        'ca_hier':            round(ca_hier, 2),
        'variation_jour_pct': round(variation_jour, 1) if variation_jour is not None else None,
        'ca_mois_cumule':     round(ca_mois, 2),
        'objectif_mensuel':   round(objectif_mensuel, 2),
        'reste_a_vendre':     round(reste_a_vendre, 2),
        'jours_ecoules':      jours_ecoules,
        'jours_restants':     jours_restants,
        'nb_jours_mois':      nb_jours_mois,
        'rythme_quotidien_necessaire': round(rythme_necessaire, 2),
        'rythme_actuel_moyen':         round(rythme_actuel_moy, 2),
        'pct_objectif_mois':  round(pct_objectif_mois, 1),
        'pct_temps_ecoule':   round(pct_temps_ecoule, 1),
        'statut':             statut,
        'historique_7j':      historique_7j,
    }


def build_grand_livre_commercial(grand, com):
    """
    Grand Livre filtre sur le portefeuille d'un seul commercial.
    Regle metier : distinct du Grand Livre general (Comptabilite) qui montre
    TOUS les clients/commerciaux. Celui-ci ne montre que les clients et
    mouvements rattaches au commercial donne (via le champ Representant/CO_No
    de Sage, deja resolu dans la colonne 'commercial' du Grand Livre).
    """
    from core.commercial_engine import _com_cockpit
    return [r for r in grand if _com_cockpit(r.get('commercial', '')) == com]

def _group_key(row, granularite):
    """
    Calcule la cle de periode selon la granularite.
    Granularites : journalier / hebdomadaire / mensuel / trimestriel / annuel
    """
    d = row.get('date')
    if not isinstance(d, date):
        try: d = date.fromisoformat(str(d)[:10])
        except: return '?'
    g = granularite.lower()
    if g == 'journalier':   return d.strftime('%Y-%m-%d')
    if g == 'hebdomadaire':
        iso = d.isocalendar()
        return f"{iso[0]}-S{iso[1]:02d}"
    if g == 'mensuel':      return d.strftime('%Y-%m')
    if g == 'trimestriel':  return f"{d.year}-T{(d.month-1)//3+1}"
    if g == 'annuel':       return str(d.year)
    return d.strftime('%Y-%m')

def build_tendances(all_rows, granularite='mensuel'):
    """
    Construit les donnees de tendance.
    Tableaux :
    - CA     : Periode | CA FCFA | Evol (▲▼) | Ecart/prec. | Taux rec.%
    - Rec    : Periode | Recouvrement | Evol | Ecart
    - Creances: Periode | FNS | Evol | Solde total | Taux risque%
    Note : donnees completes — independant du filtre periode actif.
    """
    agg = defaultdict(lambda: {'ca':0., 'rec':0., 'fns':0.})
    for r in all_rows:
        k = _group_key(r, granularite)
        agg[k]['ca']  += r.get('ca_amount',0) or 0
        if r.get('credit',0)>0 and r.get('debit',0)==0 and _up(r.get('journal',''))!='RAN':
            agg[k]['rec'] += r.get('credit',0)
        if (r.get('retard',0) or 0)>0 and (r.get('ouvert',0) or 0)>0:
            agg[k]['fns'] += r.get('ouvert',0)
    # Calcul FNS cumulees si pas de donnees ouvert
    periods = sorted(agg.keys())
    cum_ca = 0.; cum_rec = 0.
    for p in periods:
        cum_ca  += agg[p]['ca']
        cum_rec += agg[p]['rec']
        if agg[p]['fns'] == 0:
            agg[p]['fns'] = max(0., cum_ca - cum_rec)
    # Tableaux avec evolution
    rows_ca  = []; rows_rec = []; rows_fns = []
    prev_ca = prev_rec = prev_fns = None
    for p in periods:
        d = agg[p]
        # CA
        evol_ca  = '' if prev_ca  is None else (' ▲' if d['ca']  >= prev_ca  else ' ▼')
        ecart_ca = '' if prev_ca  is None else d['ca']  - prev_ca
        taux     = f"{d['rec']/d['ca']*100:.1f}%" if d['ca']>0 else '—'
        rows_ca.append({'periode':p,'ca':d['ca'],'evol':evol_ca,
                        'ecart':ecart_ca,'taux_rec':taux})
        # Recouvrement
        evol_rec  = '' if prev_rec is None else (' ▲' if d['rec'] >= prev_rec else ' ▼')
        ecart_rec = '' if prev_rec is None else d['rec'] - prev_rec
        rows_rec.append({'periode':p,'recouvrement':d['rec'],'evol':evol_rec,'ecart':ecart_rec})
        # FNS
        if d['fns'] > 0:
            evol_fns  = '' if prev_fns is None else (' ▲' if d['fns'] >= prev_fns else ' ▼')
            ecart_fns = '' if prev_fns is None else d['fns'] - prev_fns
            risque    = f"{d['fns']/d['ca']*100:.1f}%" if d['ca']>0 else '—'
            rows_fns.append({'periode':p,'fns':d['fns'],'evol':evol_fns,
                             'ecart':ecart_fns,'risque':risque,'solde':d['ca']-d['rec']})
            prev_fns = d['fns']
        prev_ca  = d['ca']
        prev_rec = d['rec']
    return {
        'ca':           rows_ca,
        'recouvrement': rows_rec,
        'creances':     rows_fns,
        'periodes':     [{
            'periode': p, 'ca': agg[p]['ca'],
            'recouvrement': agg[p]['rec'], 'fns': agg[p]['fns'],
        } for p in periods],
        'granularite': granularite,
    }

# ── Compute all (entree principale) ──────────────────────────────────────────

def resolve_period(args, latest_date=None):
    """
    Resout une periode d'analyse a partir des parametres de requete,
    fidele a la barre globale Annee/Mois/Du-Au de GTC ERP PILOT V3.

    Priorite (la plus precise gagne) :
      1. du + au (dates explicites)            -> periode exacte
      2. annee + mois                          -> ce mois precis
      3. annee seule (mois absent ou 'tous')    -> toute l'annee
      4. rien fourni                            -> mois en cours (comme
         "Mois en cours" dans l'ancien logiciel, le defaut le plus sur)

    args : dict-like (request.args) avec cles possibles :
           'du', 'au', 'annee', 'mois' (mois = 1-12 ou '' / 'tous')
    latest_date : date la plus recente connue dans les donnees (fallback
                  pour le defaut si aucun parametre n'est fourni)

    Retourne (start_date, end_date, label) ou label est un texte lisible
    du type "Juin 2026" / "2026" / "01/06/2026 -> 15/06/2026".
    """
    du   = (args.get('du')    or args.get('debut') or '').strip()
    au   = (args.get('au')    or args.get('fin')   or '').strip()
    annee= (args.get('annee') or '').strip()
    mois = (args.get('mois')  or '').strip()

    MOIS_NOMS = ['Janvier','Fevrier','Mars','Avril','Mai','Juin',
                 'Juillet','Aout','Septembre','Octobre','Novembre','Decembre']

    # 1. Dates explicites Du/Au
    if du and au:
        d1 = _parse_date_str(du)
        d2 = _parse_date_str(au)
        if d1 and d2:
            return d1, d2, f"{d1.strftime('%d/%m/%Y')} -> {d2.strftime('%d/%m/%Y')}"

    # 2 & 3. Annee (+ Mois optionnel)
    if annee and annee.lower() != 'tous':
        try:
            a = int(annee)
        except ValueError:
            a = None
        if a:
            if mois and mois.lower() != 'tous':
                try:
                    m = int(mois)
                    if 1 <= m <= 12:
                        d1 = date(a, m, 1)
                        d2 = date(a, m, _last_day_of_month(a, m))
                        return d1, d2, f"{MOIS_NOMS[m-1]} {a}"
                except ValueError:
                    pass
            # Annee seule
            return date(a, 1, 1), date(a, 12, 31), str(a)

    # 4. Defaut : mois en cours (par rapport a aujourd'hui, ou a la derniere
    #    date connue si aucune donnee recente n'existe)
    ref_date = latest_date if isinstance(latest_date, date) else date.today()
    d1 = date(ref_date.year, ref_date.month, 1)
    d2 = date(ref_date.year, ref_date.month, _last_day_of_month(ref_date.year, ref_date.month))
    return d1, d2, f"{MOIS_NOMS[ref_date.month-1]} {ref_date.year} (mois en cours)"


def _last_day_of_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def compute_all(all_rows, ref, start_date=None, end_date=None):
    """
    Calcule toutes les donnees commerciales en une passe.
    C'est la fonction centrale appelee par tous les modules.
    """
    analysis_date = end_date if isinstance(end_date, date) else _latest_date(all_rows)
    rows_bal  = filter_rows(all_rows, None, analysis_date, mode='upto')
    _annotate(rows_bal)
    grand     = build_grand_livre(rows_bal, ref, analysis_date)
    creances  = build_creances(grand, ref)
    rows_per  = filter_rows(all_rows, start_date, analysis_date, mode='between')
    _annotate(rows_per)
    classement = build_classement(rows_per, creances)
    # Ajouter rang dans cockpit
    rang_map = {r['commercial']: r['rang'] for r in classement}
    kpis      = build_kpis(rows_per, creances)
    tendances = build_tendances(all_rows)  # données complètes, indépendant du filtre
    alertes   = build_alertes(creances)
    return {
        'raw':        rows_per,
        'raw_bal':    rows_bal,
        'grand':      grand,
        'creances':   creances,
        'classement': classement,
        'kpis':       kpis,
        'tendances':  tendances,
        'alertes':    alertes,
        'analysis_date': analysis_date,
        'ref':        ref,
        'commerciaux': [r['commercial'] for r in classement if not _is_vc(r['commercial'])],
        'years':      _available_years(all_rows),
        'loaded_at':  datetime.now().strftime('%d/%m/%Y %H:%M'),
        'period_label': f"{_fmt_d(start_date) or 'Debut'} → {_fmt_d(analysis_date)}",
        'start_date': start_date,
        'end_date':   analysis_date,
    }

def _latest_date(rows):
    d = None
    for r in rows:
        rd = r.get('date')
        if isinstance(rd, date) and _up(r.get('journal','')) != 'RAN':
            if d is None or rd > d: d = rd
    return d or date.today()

def _available_years(rows):
    years = set()
    for r in rows:
        d = r.get('date')
        if isinstance(d, date):
            years.add(d.year+1 if _up(r.get('journal',''))=='RAN' else d.year)
    return sorted(y for y in years if y >= 2000)

def _fmt_d(d):
    if d is None: return ''
    try: return d.strftime('%d/%m/%Y')
    except: return str(d)
