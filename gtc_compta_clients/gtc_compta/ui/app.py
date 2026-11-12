"""Fenetre principale : navigation laterale, bandeau de mode, taches de fond."""
from __future__ import annotations

import logging
import queue
import threading
import traceback

import customtkinter as ctk

from .. import __version__
from ..services.auth import AccesRefuse, LIBELLES_ROLES
from .widgets import BLEU, ORANGE, erreur, style_treeview

log = logging.getLogger("gtc.ui")

MODULES = [
    ("accueil", "Accueil"),
    ("clients", "Clients"),
    ("import", "Preparation / Imports"),
    ("fiches", "Fiches clients"),
    ("rapprochement", "Rapprochement Sage"),
    ("solvabilite", "Solvabilite / BC"),
    ("pointage", "Pointage client"),
    ("documents", "Documents"),
    ("impressions", "Impressions"),
    ("parametres", "Parametres"),
]


class App(ctk.CTk):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title(f"GTC Comptabilite Clients {__version__} - {ctx.cfg['agence']}")
        self.geometry("1360x820")
        self.minsize(1100, 680)
        style_treeview(self)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.bandeau = ctk.CTkLabel(self, text="", height=26, corner_radius=0,
                                    font=ctk.CTkFont(size=12, weight="bold"))
        self.bandeau.grid(row=0, column=0, columnspan=2, sticky="ew")
        side = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#14324F")
        side.grid(row=1, column=0, sticky="ns")
        ctk.CTkLabel(side, text="GTC\nComptabilite clients", text_color="white", justify="left",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(padx=16, pady=(16, 14), anchor="w")
        self.nav = {}
        for key, lib in MODULES:
            b = ctk.CTkButton(side, text=lib, anchor="w", corner_radius=0, height=38, fg_color="transparent",
                              hover_color="#1F4E79", text_color="white", command=lambda k=key: self.afficher(k))
            b.pack(fill="x")
            self.nav[key] = b
        u = ctx.user
        ctk.CTkLabel(side, text=f"{u.nom}\n{LIBELLES_ROLES.get(u.role, u.role)}", text_color="#B0C4DE",
                     justify="left").pack(side="bottom", padx=16, pady=14, anchor="w")
        self.contenu = ctk.CTkFrame(self, corner_radius=0, fg_color="#F3F5F8")
        self.contenu.grid(row=1, column=1, sticky="nsew")
        self.statut = ctk.CTkLabel(self, text="Pret.", anchor="w", height=24, fg_color="#E0E6ED", corner_radius=0)
        self.statut.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.progress = ctk.CTkProgressBar(self, width=200, height=10)
        self.maj_bandeau()
        self.page = None
        self._resultats: queue.Queue = queue.Queue()   # retours des taches de fond (thread-safe)
        self.after(100, self._depiler)
        self.afficher("accueil")

    def _depiler(self):
        try:
            while True:
                cb = self._resultats.get_nowait()
                cb()
        except queue.Empty:
            pass
        self.after(100, self._depiler)

    def maj_bandeau(self):
        s = self.ctx.sage
        if getattr(s, "est_demo", False):
            self.bandeau.configure(text="MODE DEMONSTRATION - donnees Sage FICTIVES - aucun resultat n'est "
                                        "verifie sur Sage reel", fg_color=ORANGE, text_color="white")
        else:
            self.bandeau.configure(text=f"Connecte en LECTURE SEULE : {s.nom}", fg_color=BLEU, text_color="white")

    def afficher(self, key):
        from . import pages
        for k, b in self.nav.items():
            b.configure(fg_color="#1F4E79" if k == key else "transparent")
        for w in self.contenu.winfo_children():
            w.destroy()
        cls = pages.PAGES[key]
        try:
            self.page = cls(self.contenu, self)
            self.page.pack(fill="both", expand=True)
        except Exception as exc:  # affichage robuste : jamais de plantage silencieux
            log.exception("Erreur d'affichage %s", key)
            erreur(f"Impossible d'afficher le module : {exc}")

    def set_statut(self, txt):
        self.statut.configure(text=txt)

    def tache(self, libelle, fn, ok=None, err=None):
        """Execute fn() en tache de fond (l'interface ne fige pas) puis ok(res) dans le thread UI."""
        self.set_statut(libelle + "...")
        self.progress.grid(row=2, column=1, sticky="e", padx=10)
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        def run():
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                log.error("Tache '%s' en echec : %s\n%s", libelle, exc, traceback.format_exc())
                self._resultats.put(lambda e=exc: fin(None, e))
            else:
                self._resultats.put(lambda r=res: fin(r, None))

        def fin(res, exc):
            self.progress.stop()
            self.progress.grid_forget()
            if exc is not None:
                self.set_statut(f"{libelle} : echec")
                if err:
                    err(exc)
                else:
                    erreur(f"{libelle} : {exc}" if not isinstance(exc, AccesRefuse) else str(exc))
            else:
                self.set_statut(f"{libelle} : termine")
                if ok:
                    ok(res)

        threading.Thread(target=run, daemon=True).start()

    def action(self, fn, *a, **kw):
        """Action synchrone courte avec gestion d'erreur en francais."""
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            log.warning("Action refusee : %s", exc)
            erreur(str(exc))
            return None


def main(cfg_path=None):
    from ..context import AppContext
    ctx = AppContext(cfg_path)
    App(ctx).mainloop()
