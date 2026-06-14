from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/logistique')
@login_required
def module_logistique():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'logistique', 'flotte', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/logistique.html', module='logistique',
                            module_label='🚚 Logistique')
