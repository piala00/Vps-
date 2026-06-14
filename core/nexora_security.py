#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/nexora_security.py
NEXORA v2.0 — Securite applicative

- Controle d'acces par adresse IP (liste blanche optionnelle)
- Decorateurs de session / permission pour les blueprints
- Mode conception : connexion sans mot de passe (cf. routes_main)
"""
import ipaddress
import json
from functools import wraps

from flask import session, redirect, url_for, jsonify, request

from core.database import get_config, has_permission, db_one


def is_ip_allowed(ip: str) -> bool:
    """Verifie si l'adresse IP est autorisee (liste blanche optionnelle)."""
    if get_config("ip_whitelist_active", "0") != "1":
        return True
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    try:
        whitelist = json.loads(get_config("ip_whitelist", "[]"))
    except Exception:
        whitelist = []
    for entry in whitelist:
        try:
            if "/" in entry:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(entry, strict=False):
                    return True
            elif entry == ip:
                return True
        except Exception:
            continue
    return False


def current_user_id():
    return session.get("user_id")


def current_username():
    return session.get("username", "")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, msg="Session expiree"), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def permission_required(module, sous_module, action="lire"):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            uid = session.get("user_id")
            if uid is None:
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, msg="Session expiree"), 401
                return redirect(url_for("login"))
            if not has_permission(uid, module, sous_module, action):
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, msg="Acces refuse"), 403
                return redirect(url_for("accueil"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return db_one("SELECT * FROM utilisateurs WHERE id=?", (uid,))
