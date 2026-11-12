"""Lance l'interface reelle (demo) et capture chaque module : python tools/captures.py
(sous Linux : xvfb-run -s "-screen 0 1400x880x24" python tools/captures.py)"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from gtc_compta.context import AppContext  # noqa: E402
from gtc_compta.ui.app import App  # noqa: E402

OUT = ROOT / "docs" / "captures"


def main():
    ctx = AppContext(ROOT / "demo" / "sortie" / "config.json")
    app = App(ctx)
    app.geometry("1380x840+0+0")
    erreurs = []

    def pause(s=0.8):
        end = time.time() + s
        while time.time() < end:
            app.update()
            time.sleep(0.03)

    def shot(nom):
        pause()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(OUT / f"{nom}.png")

    from gtc_compta.excel import preparation as prep
    from gtc_compta.services import clients as sc, imports
    for i, (key, _lib) in enumerate(__import__("gtc_compta.ui.app", fromlist=["MODULES"]).MODULES, 1):
        try:
            app.afficher(key)
            p = app.page
            if key == "clients":
                p.table.tv.selection_set("0")
            elif key == "import":
                f = ROOT / "demo" / "sortie" / "GTC_PREPARATION_20261001.xlsx"
                res = prep.preparer_depuis_classeur(f, ctx.cfg["rapport"], sc.correspondances(ctx.db), "BERTOUA")
                lignes = prep.lignes_export(res)
                imports.completer_codes(lignes, sc.correspondances(ctx.db))
                p.apercu((str(f), lignes, res, "COLLAGE traite par l'application (secours)", 0))
            elif key == "fiches":
                p.ct.insert(0, "CL001")
                p.charger()
            elif key == "rapprochement":
                iid = next(i for i, r in p.t._data.items() if r["ct_num"] == "CL003")
                p.t.tv.selection_set(iid)
            elif key == "solvabilite":
                p.bc.insert(0, "BCCB0101")
                p.controler()
                pause(1.5)
            elif key == "pointage":
                p.ct.insert(0, "CL001")
                p.historique()
                pause(0.3)
                p.th.tv.selection_set("0")
            elif key == "documents":
                p.piece.insert(0, "FACB0201")
                p.rechercher()
            shot(f"{i:02d}_{key}")
        except Exception as exc:  # noqa: BLE001
            import traceback
            erreurs.append((key, traceback.format_exc()))
    app.destroy()
    for k, e in erreurs:
        print("ERREUR", k, e)
    print("captures :", len(list(OUT.glob("*.png"))), "erreurs :", len(erreurs))
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
