from flask import render_template, session, redirect, url_for
from . import bp
from core.database import has_permission
from core.nexora_security import login_required


@bp.route('/module/consolidation')
@login_required
def module_consolidation():
    uid = session['user_id']
    if not (session.get('is_master') or has_permission(uid, 'consolidation', 'synthese_groupe', 'lire')):
        return redirect(url_for('accueil'))
    return render_template('modules/consolidation.html', module='consolidation',
                            module_label='🧮 Consolidation')
