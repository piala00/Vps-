"""Contexte applicatif : configuration, base locale, adaptateur Sage, utilisateur courant."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import load_config
from .db import Database
from .sage import creer_adaptateur
from .services.auth import Utilisateur, assurer_utilisateur


class AppContext:
    def __init__(self, cfg_path=None):
        self.cfg = load_config(cfg_path)
        base = Path(self.cfg["_path"]).resolve().parent
        self.data_dir = Path(self.cfg["data_dir"])
        if not self.data_dir.is_absolute():
            self.data_dir = base / self.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("sauvegardes", "impressions", "preparations", "exports", "logs"):
            (self.data_dir / sub).mkdir(exist_ok=True)
        self._logging()
        self.db_path = self.data_dir / "gtc_compta.sqlite3"
        self.db = Database(self.db_path)
        u = self.cfg["utilisateur"]
        self.user = Utilisateur(u["login"], u["nom"], u["role"])
        assurer_utilisateur(self.db, self.user)
        self.sage = creer_adaptateur(self.cfg)
        logging.getLogger("gtc").info("Demarrage : utilisateur=%s sage=%s", self.user.login, self.sage.nom)

    def _logging(self):
        log = logging.getLogger("gtc")
        if log.handlers:
            return
        h = logging.handlers.RotatingFileHandler(self.data_dir / "logs" / "gtc_compta.log",
                                                 maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)

    def recharger_sage(self):
        self.sage = creer_adaptateur(self.cfg)
