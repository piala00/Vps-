from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/commercial')
@login_required
def module_commercial():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'commercial', 'fiches_clients', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/commercial.html', module='commercial',
                            module_label='📊 Commercial')
