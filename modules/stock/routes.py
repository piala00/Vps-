from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/stock')
@login_required
def module_stock():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'stock', 'fiche_bl_sage', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/stock.html', module='stock',
                            module_label='📦 Stock')
