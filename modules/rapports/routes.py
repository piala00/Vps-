from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/rapports')
@login_required
def module_rapports():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'rapports', 'rpt_stock', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/rapports.html', module='rapports',
                            module_label='📋 Rapports')
