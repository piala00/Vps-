"""NEXORA v2.0 - Module Multi-Sites"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/multisite")
@login_required
def module_multisite():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/multisite.html",
        module="multisite", module_label="Multi-Sites",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)


@bp.route('/api/multisite/stock-disponible')
@login_required
def api_ms_stock():
    from core.sage_connector import get_stock_disponible
    from core.database import db_all
    agence_src = int(request.args.get('agence_source', 2))
    q          = request.args.get('q','')
    articles   = get_stock_disponible(7, q)
    if not articles:
        return jsonify({'ok': True, 'message': 'Sage non disponible (aucun article recupere)', 'articles': []})
    # Déduire les DTs validées non livrées
    dts_en_cours = db_all(
        "SELECT tl.ar_ref, SUM(tl.qte_demandee) as qte_dt "
        "FROM nx_transferts_lignes tl "
        "JOIN nx_transferts t ON t.id=tl.transfert_id "
        "WHERE t.statut IN ('VALIDEE','EN_COURS') "
        "GROUP BY tl.ar_ref")
    dt_map = {r['ar_ref']: r['qte_dt'] for r in dts_en_cours}
    for a in articles:
        ref  = a.get('AR_Ref','')
        phys = float(a.get('stock_physique',0))
        res  = float(a.get('qte_reservee',0))
        dt   = float(dt_map.get(ref, 0))
        a['qte_en_dt']   = dt
        a['stock_dispo'] = max(0, phys - res - dt)
    return jsonify({'ok':True,'articles':articles})

@bp.route('/api/multisite/transferts', methods=['GET','POST'])
@login_required
def api_ms_transferts():
    if request.method == 'POST':
        d = request.get_json() or {}
        from datetime import date
        import random, string
        no  = 'DT' + date.today().strftime('%Y%m%d') + ''.join(random.choices(string.digits,k=4))
        uid = db_exec(
            "INSERT INTO nx_transferts(numero,agence_source_id,agence_dest_id,statut,urgence,demande_par)"
            " VALUES(?,?,?,?,?,?)",
            (no, d.get('agence_source_id',2), d.get('agence_dest_id',3),
             'SOUMISE', 1 if d.get('urgence') else 0, session.get('username','')))
        for l in d.get('lignes',[]):
            db_exec(
                "INSERT INTO nx_transferts_lignes(transfert_id,ar_ref,designation,qte_demandee)"
                " VALUES(?,?,?,?)",
                (uid, l.get('ar_ref',''), l.get('designation',''), float(l.get('qte',0))))
        return jsonify({'ok':True,'id':uid,'numero':no})
    statut = request.args.get('statuts','')
    sql = ("SELECT t.*, sa.nom source_nom, da.nom dest_nom FROM nx_transferts t "
           "LEFT JOIN nx_agences sa ON sa.id=t.agence_source_id "
           "LEFT JOIN nx_agences da ON da.id=t.agence_dest_id")
    p = []
    if statut:
        sql += " WHERE t.statut=?"
        p.append(statut)
    sql += " ORDER BY t.date_demande DESC LIMIT 100"
    return jsonify({'ok':True,'transferts':db_all(sql, p)})

@bp.route('/api/multisite/transferts/<int:tid>/valider', methods=['POST'])
@login_required
def api_ms_valider_dt(tid):
    d      = request.get_json() or {}
    action = d.get('action','valider')
    motif  = d.get('motif_refus','')
    if action == 'refuser' and not motif:
        return jsonify({'ok':False,'msg':'Motif de refus obligatoire'})
    from datetime import date
    statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
    db_exec("UPDATE nx_transferts SET statut=?,date_validation=?,valide_par=?,motif_refus=? WHERE id=?",
            (statut, str(date.today()), session.get('username',''), motif, tid))
    return jsonify({'ok':True,'statut':statut})

@bp.route('/api/multisite/demandes-achat', methods=['GET','POST'])
@login_required
def api_ms_da():
    if request.method == 'POST':
        d = request.get_json() or {}
        from datetime import date
        import random, string
        no  = 'DA' + date.today().strftime('%Y%m%d') + ''.join(random.choices(string.digits,k=4))
        uid = db_exec(
            "INSERT INTO nx_demandes_achat(numero,agence_id,fournisseur_nom,statut,urgence,"
            "livraison_agence,demande_par,observations) VALUES(?,?,?,?,?,?,?,?)",
            (no, d.get('agence_id',2), d.get('fournisseur_nom',''),
             'SOUMISE', 1 if d.get('urgence') else 0,
             d.get('agence_id',2), session.get('username',''),
             d.get('observations','')))
        return jsonify({'ok':True,'id':uid,'numero':no})
    return jsonify({'ok':True,'demandes':db_all(
        "SELECT * FROM nx_demandes_achat ORDER BY date_demande DESC LIMIT 100")})

@bp.route('/api/multisite/demandes-achat/<int:did>/valider', methods=['POST'])
@login_required
def api_ms_valider_da(did):
    d      = request.get_json() or {}
    action = d.get('action','valider')
    motif  = d.get('motif_refus','')
    if action == 'refuser' and not motif:
        return jsonify({'ok':False,'msg':'Motif obligatoire'})
    from datetime import date
    statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
    db_exec("UPDATE nx_demandes_achat SET statut=?,date_validation=?,valide_par=?,motif_refus=? WHERE id=?",
            (statut, str(date.today()), session.get('username',''), motif, did))
    return jsonify({'ok':True})
