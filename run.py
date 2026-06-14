#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point d'entree NEXORA v2.0"""
import os
import sys
import threading
import webbrowser
import logging

from flask import Flask
from config import Config

# Ajouter le repertoire courant au path (pour PyInstaller)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def create_app():
    app = Flask(__name__,
                 template_folder=os.path.join(BASE_DIR, 'templates'),
                 static_folder=os.path.join(BASE_DIR, 'static'))
    app.config.from_object(Config)

    # Initialiser la base de donnees
    from core.database import init_db
    init_db(app.config['DB_PATH'])

    # Initialiser les licences
    from core.nexora_licence import init_licence
    from core.database import get_config, set_config
    init_licence(get_config, set_config)

    # Enregistrer les blueprints
    from modules.stock import bp as stock_bp
    from modules.logistique import bp as log_bp
    from modules.commercial import bp as com_bp
    from modules.comptabilite import bp as compta_bp
    from modules.caisse import bp as caisse_bp
    from modules.rh import bp as rh_bp
    from modules.consolidation import bp as cons_bp
    from modules.multisite import bp as ms_bp
    from modules.rapports import bp as rpt_bp
    from modules.parametres import bp as param_bp

    for bp in [stock_bp, log_bp, com_bp, compta_bp, caisse_bp,
               rh_bp, cons_bp, ms_bp, rpt_bp, param_bp]:
        app.register_blueprint(bp)

    # Routes principales
    from core.routes_main import register_main_routes
    register_main_routes(app)

    return app


if __name__ == '__main__':
    app = create_app()
    port = Config.PORT

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger('NEXORA')
    log.info('NEXORA v2.0 -- http://127.0.0.1:%s' % port)

    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open('http://127.0.0.1:%s' % port)

    if not os.environ.get('NEXORA_NO_BROWSER'):
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host='0.0.0.0', port=port, debug=False,
            use_reloader=False, threaded=True)
