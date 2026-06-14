from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/parametres')
@login_required
def module_parametres():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'parametres', 'config_generale', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/parametres.html', module='parametres',
                            module_label='⚙️ Parametres')
