from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/rh')
@login_required
def module_rh():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'rh', 'fiches_employes', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/rh.html', module='rh',
                            module_label='👥 Ressources Humaines')
