from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/multisite')
@login_required
def module_multisite():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'multisite', 'gestion_agences', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/multisite.html', module='multisite',
                            module_label='🌐 Multi-Agences')
