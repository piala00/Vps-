"""NEXORA v2.0 - Module Caisse"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/caisse")
@login_required
def module_caisse():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/caisse.html",
        module="caisse", module_label="Caisse",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)


@bp.route('/api/caisse/rapports', methods=['GET','POST'])
@login_required
def api_caisse_rapports():
    if request.method == 'POST':
        d   = request.get_json() or {}
        uid = db_exec(
            "INSERT INTO rapports_caisse(date_rapport,commercial,agence,total_ventes,"
            "total_encaisse,total_credit,observations,statut,saisi_par) VALUES(?,?,?,?,?,?,?,?,?)",
            (d.get('date_rapport',''), d.get('commercial',''),
             d.get('agence','BERTOUA'), float(d.get('total_ventes',0)),
             float(d.get('total_encaisse',0)), float(d.get('total_credit',0)),
             d.get('observations',''), 'brouillon', session.get('username','')))
        for l in d.get('lignes',[]):
            db_exec(
                "INSERT INTO lignes_rapport_caisse(rapport_id,no_facture,code_client,"
                "client_nom,montant_facture,montant_encaisse,mode_paiement) VALUES(?,?,?,?,?,?,?)",
                (uid, l.get('no_facture',''), l.get('code_client',''),
                 l.get('client_nom',''), float(l.get('montant_facture',0)),
                 float(l.get('montant_encaisse',0)), l.get('mode_paiement','ESPECES')))
        return jsonify({'ok':True,'id':uid})
    rows = db_all("SELECT * FROM rapports_caisse ORDER BY date_rapport DESC LIMIT 100")
    return jsonify({'ok':True,'rapports':rows})

@bp.route('/api/caisse/rapport/<int:rid>/lignes')
@login_required
def api_caisse_lignes(rid):
    rows = db_all("SELECT * FROM lignes_rapport_caisse WHERE rapport_id=?", (rid,))
    return jsonify({'ok':True,'lignes':rows})
