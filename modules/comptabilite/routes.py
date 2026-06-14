from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/comptabilite')
@login_required
def module_comptabilite():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'comptabilite', 'balance_agee', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/comptabilite.html', module='comptabilite',
                            module_label='💰 Comptabilite')
