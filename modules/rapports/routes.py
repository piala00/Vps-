#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/rapports/routes.py
NEXORA v2.0 — Module Rapports : rapports stock, commerciaux, comptables et
logistique avec export Excel (xlsx) et PDF.
"""
from datetime import date
from io import BytesIO

from flask import render_template, session, redirect, url_for, request, jsonify, send_file
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from . import bp
from core.database import db_all, has_permission
from core.nexora_security import login_required
from core.sage_connector import get_stock_disponible, get_ventes, get_creances_clients


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'rapports', sous_module, action)


def _niveau_risque(solde):
    solde = float(solde or 0)
    if solde > 500000:
        return 'CRITIQUE'
    if solde > 200000:
        return 'ELEVE'
    if solde > 50000:
        return 'MOYEN'
    return 'FAIBLE'


RAPPORTS = {
    'stock': {
        'sous_module': 'rpt_stock',
        'titre': 'Rapport Stock',
        'headers': ['Depot', 'Code article', 'Designation', 'Famille',
                     'Stock actuel', 'Stock mini', 'Stock maxi', 'Valeur stock'],
        'champs': ['depot', 'code_article', 'designation', 'famille',
                    'stock_actuel', 'stock_mini', 'stock_maxi', 'valeur_stock'],
        'periode': False,
    },
    'commercial': {
        'sous_module': 'rpt_commercial',
        'titre': 'Rapport Commercial - Ventes',
        'headers': ['Date facture', 'No facture', 'Code client', 'Client', 'Montant TTC'],
        'champs': ['date_facture', 'no_facture', 'code_client', 'client_nom', 'montant_ttc'],
        'periode': True,
    },
    'comptable': {
        'sous_module': 'rpt_comptable',
        'titre': 'Rapport Comptable - Balance agee des creances',
        'headers': ['Code client', 'Client', 'Solde', 'Niveau de risque'],
        'champs': ['code_client', 'nom', 'solde', 'niveau_risque'],
        'periode': False,
    },
    'logistique': {
        'sous_module': 'rpt_logistique',
        'titre': 'Rapport Logistique - Voyages',
        'headers': ['No voyage', 'Camion', 'Chauffeur', 'Origine', 'Destination',
                     'Date depart', 'Date retour', 'Statut'],
        'champs': ['no_voyage', 'camion_immat', 'chauffeur_nom', 'origine', 'destination',
                    'date_depart', 'date_retour', 'statut'],
        'periode': True,
    },
}


def _donnees_rapport(type_rapport, date_debut, date_fin):
    if type_rapport == 'stock':
        return get_stock_disponible()
    if type_rapport == 'commercial':
        return get_ventes(date_debut, date_fin)
    if type_rapport == 'comptable':
        creances = get_creances_clients()
        for c in creances:
            c['niveau_risque'] = _niveau_risque(c.get('solde'))
        return creances
    if type_rapport == 'logistique':
        sql = """SELECT v.*, c.immatriculation AS camion_immat, ch.nom AS chauffeur_nom
                 FROM voyages v
                 LEFT JOIN camions c ON c.id=v.camion_id
                 LEFT JOIN personnel_logistique ch ON ch.id=v.chauffeur_id
                 WHERE 1=1"""
        params = []
        if date_debut:
            sql += " AND v.date_depart>=?"
            params.append(date_debut)
        if date_fin:
            sql += " AND v.date_depart<=?"
            params.append(date_fin)
        sql += " ORDER BY v.date_depart DESC"
        return db_all(sql, tuple(params))
    return []


def _export_excel(filename, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                      as_attachment=True, download_name=filename)


def _export_pdf(filename, titre, headers, rows):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph(titre, styles['Title']), Spacer(1, 12)]
    data = [headers] + [[('' if v is None else str(v)) for v in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2b4c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


@bp.route('/module/rapports')
@login_required
def module_rapports():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'rapports', 'rpt_stock', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/rapports.html', module='rapports',
                            module_label='📋 Rapports')


@bp.route('/api/rapports/<type_rapport>')
@login_required
def api_rapport(type_rapport):
    uid = session['user_id']
    cfg = RAPPORTS.get(type_rapport)
    if not cfg:
        return jsonify(ok=False, msg='Rapport inconnu'), 404
    if not _peut(uid, cfg['sous_module'], 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    lignes = _donnees_rapport(type_rapport, date_debut, date_fin)
    return jsonify(ok=True, titre=cfg['titre'], headers=cfg['headers'],
                    champs=cfg['champs'], periode=cfg['periode'],
                    peut_excel=_peut(uid, 'export_excel', 'lire'),
                    peut_pdf=_peut(uid, 'export_pdf', 'lire'),
                    data=lignes)


@bp.route('/api/rapports/<type_rapport>/export')
@login_required
def api_rapport_export(type_rapport):
    uid = session['user_id']
    cfg = RAPPORTS.get(type_rapport)
    if not cfg:
        return jsonify(ok=False, msg='Rapport inconnu'), 404
    if not _peut(uid, cfg['sous_module'], 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    fmt = request.args.get('format', 'excel')
    if fmt == 'pdf':
        if not _peut(uid, 'export_pdf', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403
    else:
        if not _peut(uid, 'export_excel', 'lire'):
            return jsonify(ok=False, msg='Acces refuse'), 403

    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')
    lignes = _donnees_rapport(type_rapport, date_debut, date_fin)
    rows = [[ligne.get(c) for c in cfg['champs']] for ligne in lignes]

    nom_fichier = 'rapport_%s_%s' % (type_rapport, date.today().isoformat())
    if fmt == 'pdf':
        return _export_pdf(nom_fichier + '.pdf', cfg['titre'], cfg['headers'], rows)
    return _export_excel(nom_fichier + '.xlsx', cfg['headers'], rows)
