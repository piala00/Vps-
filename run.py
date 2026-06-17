"""NEXORA v2.0 — Point d'entree principal"""
import os, sys, threading, webbrowser, logging

# PyInstaller compatibility
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from flask import Flask
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_DIR, 'nexora.log'), encoding='utf-8'),
    ]
)
log = logging.getLogger('NEXORA')


def create_app():
    app = Flask(__name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'))
    app.config.from_object(Config)

    # Init base de donnees
    from core.database import init_db
    init_db(app.config['DB_PATH'])
    log.info("Base de donnees initialisee")

    # Init licences
    from core.nexora_licence import init_licence
    from core.database import get_config, set_config
    init_licence(get_config, set_config)
    log.info("Systeme de licences initialise")

    # Routes principales
    from core.routes_main import bp as main_bp
    app.register_blueprint(main_bp)

    # Blueprints modules
    from modules.stock        import bp as stock_bp
    from modules.logistique   import bp as log_bp
    from modules.commercial   import bp as com_bp
    from modules.comptabilite import bp as compta_bp
    from modules.caisse       import bp as caisse_bp
    from modules.rh           import bp as rh_bp
    from modules.consolidation import bp as cons_bp
    from modules.multisite    import bp as ms_bp
    from modules.rapports     import bp as rpt_bp
    from modules.parametres   import bp as param_bp

    for bp_mod in [stock_bp, log_bp, com_bp, compta_bp, caisse_bp,
                   rh_bp, cons_bp, ms_bp, rpt_bp, param_bp]:
        app.register_blueprint(bp_mod)

    log.info("Blueprints enregistres")
    return app


def open_browser(port):
    import time
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:' + str(port))


if __name__ == '__main__':
    app  = create_app()
    port = Config.PORT

    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'

    log.info("NEXORA v2.0")
    log.info("Local  : http://127.0.0.1:%d", port)
    log.info("Reseau : http://%s:%d", local_ip, port)

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host='0.0.0.0', port=port, debug=False,
            use_reloader=False, threaded=True)
