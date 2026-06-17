"""NEXORA v2.0 - Module Consolidation"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/consolidation")
@login_required
def module_consolidation():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/consolidation.html",
        module="consolidation", module_label="Consolidation",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)


@bp.route('/api/consolidation/dashboard')
@login_required
def api_cons_dashboard():
    from core.sage_connector import get_factures_vente
    from core.database import db_all as local_all
    from datetime import date, timedelta
    periode = request.args.get('periode','mois')
    if periode == 'mois':
        debut = str(date.today().replace(day=1))
    elif periode == 'semaine':
        debut = str(date.today() - timedelta(days=7))
    elif periode == 'mois-1':
        d = date.today().replace(day=1) - timedelta(days=1)
        debut = str(d.replace(day=1))
    else:
        debut = str(date.today())
    factures = get_factures_vente(date_debut=debut)
    if not factures:
        agences  = local_all("SELECT * FROM nx_agences WHERE actif=1")
        result   = [{'agence':a['nom'],'ca_mois':0,'nb_factures':0} for a in agences]
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucune facture recuperee)',
                        'agences': result, 'total_ca': 0})
    total_ca = sum(float(f.get('DO_TTC',0) or 0) for f in factures)
    agences  = local_all("SELECT * FROM nx_agences WHERE actif=1")
    result   = [{'agence':a['nom'], 'ca_mois':total_ca if a['id']==2 else 0, 'nb_factures':len(factures) if a['id']==2 else 0} for a in agences]
    return jsonify({'ok':True,'agences':result,'total_ca':total_ca})
