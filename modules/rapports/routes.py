"""NEXORA v2.0 - Module Rapports"""
import os
from flask import render_template, jsonify, session, request, current_app
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/rapports")
@login_required
def module_rapports():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/rapports.html",
        module="rapports", module_label="Rapports",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)


@bp.route('/api/rapports/caisse-excel')
@login_required
def api_rapport_caisse_excel():
    """Genere un export Excel des rapports de caisse pour un mois/agence donnes."""
    mois   = request.args.get('mois', '')
    agence = request.args.get('agence', 'BERTOUA')
    if not mois:
        return jsonify({'ok': False, 'message': 'Mois requis'}), 400

    rapports = db_all(
        "SELECT * FROM rapports_caisse WHERE date_rapport LIKE ? AND agence=? "
        "ORDER BY date_rapport", (mois + '%', agence))

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Rapport Caisse'
    ws.append(['Date', 'Commercial', 'Agence', 'Total Ventes', 'Total Encaisse',
               'Total Credit', 'Statut', 'Observations'])
    for r in rapports:
        ws.append([r.get('date_rapport',''), r.get('commercial',''), r.get('agence',''),
                   r.get('total_ventes',0), r.get('total_encaisse',0),
                   r.get('total_credit',0), r.get('statut',''), r.get('observations','')])

    ws2 = wb.create_sheet('Lignes')
    ws2.append(['Rapport ID', 'N° Facture', 'Code Client', 'Client', 'Montant Facture',
                'Montant Encaisse', 'Mode Paiement', 'Observations'])
    for r in rapports:
        lignes = db_all("SELECT * FROM lignes_rapport_caisse WHERE rapport_id=?", (r['id'],))
        for l in lignes:
            ws2.append([r['id'], l.get('no_facture',''), l.get('code_client',''),
                        l.get('client_nom',''), l.get('montant_facture',0),
                        l.get('montant_encaisse',0), l.get('mode_paiement',''),
                        l.get('observations','')])

    exports_dir = os.path.join(current_app.static_folder, 'exports')
    os.makedirs(exports_dir, exist_ok=True)
    filename = 'rapport_caisse_%s_%s.xlsx' % (mois, agence)
    wb.save(os.path.join(exports_dir, filename))

    return jsonify({'ok': True, 'url': '/static/exports/' + filename})
