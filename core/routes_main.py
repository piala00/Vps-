#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/routes_main.py
NEXORA v2.0 — Routes principales : authentification, setup, accueil, licence
"""
from flask import (render_template, redirect, url_for, request,
                    session, jsonify)

from core.database import (
    db_all, db_one, db_exec, get_config, set_config,
    has_permission, get_accessible_modules, set_all_permissions,
    hash_pwd, verify_pwd, audit, PERMISSIONS_TREE,
    _NEXORA_MASTER, _NEXORA_MASTER_NOM,
)
from core.nexora_licence import get_licence_manager
from core.nexora_security import is_ip_allowed


MODULE_ROUTES = {
    "stock":         ("stock.module_stock", "📦 Stock"),
    "logistique":    ("logistique.module_logistique", "🚚 Logistique"),
    "commercial":    ("commercial.module_commercial", "📊 Commercial"),
    "comptabilite":  ("comptabilite.module_comptabilite", "💰 Comptabilite"),
    "caisse":        ("caisse.module_caisse", "🏪 Caisse"),
    "rh":            ("rh.module_rh", "👥 Ressources Humaines"),
    "consolidation": ("consolidation.module_consolidation", "🧮 Consolidation"),
    "multisite":     ("multisite.module_multisite", "🌐 Multi-Agences"),
    "rapports":      ("rapports.module_rapports", "📋 Rapports"),
    "parametres":    ("parametres.module_parametres", "⚙️ Parametres"),
}


def register_main_routes(app):

    @app.before_request
    def check_ip():
        if request.endpoint in ("ip_bloquee", "static"):
            return None
        ip = request.remote_addr or ""
        if not is_ip_allowed(ip):
            return redirect(url_for("ip_bloquee"))
        return None

    @app.route("/")
    def index():
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        if get_config("setup_done") != "1":
            return redirect(url_for("setup"))
        return redirect(url_for("accueil"))

    # ── Assistant de configuration initiale ──────────────────────────────
    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if get_config("setup_done") == "1":
            return redirect(url_for("accueil"))

        if request.method == "POST":
            data = request.form

            # Etape 1 : societe
            set_config("societe_nom", data.get("societe_nom", "").strip())
            set_config("societe_ville", data.get("societe_ville", "").strip())

            # Etape 2 : agence locale
            agence_code = data.get("agence_locale", "BERTOUA")
            set_config("agence_locale", agence_code)
            depot = data.get("depot_sage_no", "").strip()
            if depot:
                db_exec("UPDATE nx_agences SET depot_sage_no=? WHERE code=?",
                        (depot, agence_code))

            # Etape 3 : connexion Sage (optionnelle)
            set_config("sage_server", data.get("sage_server", "").strip())
            set_config("sage_database", data.get("sage_database", "").strip())
            set_config("sage_trusted", "1" if data.get("sage_trusted") else "0")
            set_config("sage_login", data.get("sage_login", "sa").strip())
            set_config("sage_password", data.get("sage_password", ""))

            # Etape 4 : compte administrateur
            username = data.get("admin_username", "admin").strip().lower()
            password = data.get("admin_password", "")
            nom = data.get("admin_nom", "Administrateur").strip()
            if not db_one("SELECT id FROM utilisateurs WHERE username=?", (username,)):
                uid = db_exec(
                    "INSERT INTO utilisateurs(username,password_hash,nom,agence)"
                    " VALUES(?,?,?,?)",
                    (username, hash_pwd(password), nom, agence_code))
                set_all_permissions(uid, True)

            # Etape 5 : finalisation
            set_config("mode_conception", "1" if data.get("mode_conception") else "0")
            set_config("setup_done", "1")
            audit("système", "INIT", "SETUP", "Configuration initiale terminee")

            return redirect(url_for("login"))

        agences = db_all("SELECT * FROM nx_agences ORDER BY id")
        return render_template("setup.html", agences=agences)

    # ── Authentification ──────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if get_config("setup_done") != "1":
            return redirect(url_for("setup"))

        erreur = ""
        mode_conception = get_config("mode_conception", "1") == "1"

        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")

            user = db_one(
                "SELECT * FROM utilisateurs WHERE username=? AND actif=1",
                (username,))

            if not user:
                erreur = "Identifiant inconnu"
            elif mode_conception and not user["password_hash"]:
                ok = True
            else:
                ok = verify_pwd(password, user["password_hash"])
                if not ok:
                    erreur = "Mot de passe incorrect"

            if user and not erreur:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["nom"] = ("%s %s" % (user["prenom"] or "", user["nom"])).strip()
                session["is_master"] = (user["username"] == _NEXORA_MASTER)
                audit(user["username"], "AUTH", "LOGIN", "Connexion", request.remote_addr or "")
                return redirect(url_for("accueil"))

        users = []
        if mode_conception:
            users = db_all(
                "SELECT id,username,nom,prenom FROM utilisateurs"
                " WHERE actif=1 AND masque=0 ORDER BY nom")

        return render_template("login.html", erreur=erreur,
                                mode_conception=mode_conception, users=users)

    @app.route("/logout")
    def logout():
        if session.get("username"):
            audit(session["username"], "AUTH", "LOGOUT", "Deconnexion", request.remote_addr or "")
        session.clear()
        return redirect(url_for("login"))

    # ── Accueil ──────────────────────────────────────────────────────────
    @app.route("/accueil")
    def accueil():
        if session.get("user_id") is None:
            return redirect(url_for("login"))

        uid = session["user_id"]
        accessibles = get_accessible_modules(uid)
        modules = []
        for key in PERMISSIONS_TREE:
            if key in accessibles:
                route, label = MODULE_ROUTES.get(key, (None, key))
                modules.append({
                    "key": key,
                    "label": label,
                    "icon": PERMISSIONS_TREE[key]["icon"],
                    "url": url_for(route) if route else "#",
                })

        licence_mgr = get_licence_manager()
        licence_info = licence_mgr.get_licence().to_dict() if licence_mgr else {}
        demo = licence_mgr.mode_demonstration() if licence_mgr else False
        jours_demo = licence_mgr.jours_demo_restants() if licence_mgr else 0

        return render_template("accueil.html",
                                modules=modules,
                                societe_nom=get_config("societe_nom", "NEXORA"),
                                licence=licence_info,
                                demo=demo,
                                jours_demo=jours_demo)

    # ── Redirection generique de module ─────────────────────────────────
    @app.route("/module/<nom_module>")
    def module_page(nom_module):
        if nom_module not in MODULE_ROUTES:
            return redirect(url_for("accueil"))
        route, _ = MODULE_ROUTES[nom_module]
        return redirect(url_for(route))

    # ── API session ──────────────────────────────────────────────────────
    @app.route("/api/me")
    def api_me():
        if session.get("user_id") is None:
            return jsonify(ok=False, msg="Non connecte"), 401
        uid = session["user_id"]
        user = db_one("SELECT id,username,nom,prenom,email,agence FROM utilisateurs WHERE id=?", (uid,))
        return jsonify(ok=True,
                        user=user,
                        is_master=bool(session.get("is_master")),
                        modules=get_accessible_modules(uid))

    # ── API licence ─────────────────────────────────────────────────────
    @app.route("/api/licence/statut")
    def api_licence_statut():
        mgr = get_licence_manager()
        if not mgr:
            return jsonify(ok=False, msg="Module licence indisponible")
        info = mgr.get_licence().to_dict()
        info["mode_demo"] = mgr.mode_demonstration()
        info["jours_demo_restants"] = mgr.jours_demo_restants()
        return jsonify(ok=True, licence=info)

    @app.route("/api/licence/verifier", methods=["POST"])
    def api_licence_verifier():
        mgr = get_licence_manager()
        if not mgr:
            return jsonify(ok=False, msg="Module licence indisponible")
        numero = (request.get_json(silent=True) or {}).get("numero", "")
        info = mgr._verifier.verifier(numero)
        return jsonify(ok=True, licence=info.to_dict())

    @app.route("/api/licence/activer", methods=["POST"])
    def api_licence_activer():
        if session.get("user_id") is None:
            return jsonify(ok=False, msg="Session expiree"), 401
        if not has_permission(session["user_id"], "parametres", "licence", "ecrire"):
            return jsonify(ok=False, msg="Acces refuse"), 403
        mgr = get_licence_manager()
        if not mgr:
            return jsonify(ok=False, msg="Module licence indisponible")
        numero = (request.get_json(silent=True) or {}).get("numero", "")
        info = mgr.activer(numero)
        if not info.valide:
            return jsonify(ok=False, msg=info.erreur or "Numero de serie invalide")
        audit(session["username"], "PARAMETRES", "LICENCE_ACTIVATION", info.nom_societe)
        return jsonify(ok=True, licence=info.to_dict())

    # ── Acces refuse (IP) ───────────────────────────────────────────────
    @app.route("/acces-refuse")
    def ip_bloquee():
        return render_template("ip_bloquee.html"), 403
