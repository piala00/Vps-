"""NEXORA v2.0 - Module Ressources Humaines"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/rh")
@login_required
def module_rh():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/rh.html",
        module="rh", module_label="Ressources Humaines",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)
