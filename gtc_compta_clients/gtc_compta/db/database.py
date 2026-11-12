"""Acces SQLite : migrations, transactions atomiques, audit, sauvegarde.

Toute la persistance passe par cette classe pour permettre plus tard une
implementation SQL Server (multi-utilisateurs) avec la meme interface.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from pathlib import Path


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _migrations() -> list[tuple[int, str, str]]:
    out = []
    pkg = resources.files("gtc_compta.db") / "migrations"
    for entry in pkg.iterdir():
        if entry.name.endswith(".sql"):
            num = int(entry.name.split("_", 1)[0])
            out.append((num, entry.name, entry.read_text(encoding="utf-8")))
    return sorted(out)


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self._in_tx = 0
        self.migrate()

    # -- migrations -----------------------------------------------------------
    def migrate(self) -> list[str]:
        self.conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                          "version INTEGER PRIMARY KEY, nom TEXT, applique_le TEXT)")
        done = {r[0] for r in self.conn.execute("SELECT version FROM schema_migrations")}
        applied = []
        for num, name, sql in _migrations():
            if num in done:
                continue
            with self.transaction():
                for stmt in _split_sql(sql):
                    self.conn.execute(stmt)
                self.conn.execute("INSERT INTO schema_migrations VALUES (?,?,?)",
                                  (num, name, now_iso()))
            applied.append(name)
        return applied

    # -- transactions -------------------------------------------------------------
    @contextmanager
    def transaction(self):
        with self._lock:
            outer = self._in_tx == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            else:
                self.conn.execute(f"SAVEPOINT sp{self._in_tx}")
            self._in_tx += 1
            try:
                yield self
            except BaseException:
                self._in_tx -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                else:
                    self.conn.execute(f"ROLLBACK TO sp{self._in_tx}")
                    self.conn.execute(f"RELEASE sp{self._in_tx}")
                raise
            else:
                self._in_tx -= 1
                if outer:
                    self.conn.execute("COMMIT")
                else:
                    self.conn.execute(f"RELEASE sp{self._in_tx}")

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params=()):
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params=(), default=None):
        row = self.one(sql, params)
        return default if row is None or row[0] is None else row[0]

    # -- audit -----------------------------------------------------------------
    def audit(self, user: str, action: str, objet: str = "", details=None) -> None:
        if details is not None and not isinstance(details, str):
            details = json.dumps(details, ensure_ascii=False, default=str)
        self.execute("INSERT INTO audit_events(utilisateur, action, objet, details) VALUES (?,?,?,?)",
                     (user, action, objet, details))

    # -- sauvegarde / restauration ---------------------------------------------
    def backup(self, dest: str | Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self.conn.backup(target)
            finally:
                target.close()
        return dest

    @staticmethod
    def restore(backup_file: str | Path, db_path: str | Path) -> None:
        """Restaure en verifiant d'abord l'integrite de la sauvegarde."""
        chk = sqlite3.connect(str(backup_file))
        try:
            res = chk.execute("PRAGMA integrity_check").fetchone()[0]
            if res != "ok":
                raise ValueError(f"Sauvegarde corrompue : {res}")
        finally:
            chk.close()
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        shutil.copyfile(backup_file, db_path)

    def close(self):
        self.conn.close()


def _split_sql(script: str) -> list[str]:
    stmts, buf = [], []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt.strip(";").strip():
                stmts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts
