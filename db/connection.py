"""
Accès SQLite (fichier local) — compatible Streamlit Community Cloud (pas de serveur).

Un fin adaptateur reproduit l'interface psycopg utilisée dans le code :
  - `with connect() as conn:` (commit à la sortie, rollback sur erreur),
  - `conn.execute(sql, params).fetchall()`,
  - `with conn.cursor() as cur:` puis `cur.execute / executemany / fetchall /
    fetchone / rowcount`,
  - les requêtes gardent les marqueurs `%s` (traduits en `?` à la volée).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import config


def _tr(sql: str) -> str:
    """Traduit les marqueurs de paramètres psycopg (%s) vers SQLite (?)."""
    return sql.replace("%s", "?")


class _Cursor:
    def __init__(self, cur: sqlite3.Cursor):
        self._cur = cur

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *exc) -> bool:
        self._cur.close()
        return False

    def execute(self, sql: str, params=()):
        self._cur.execute(_tr(sql), params)
        return self._cur

    def executemany(self, sql: str, seq):
        self._cur.executemany(_tr(sql), list(seq))
        return self._cur

    def fetchall(self):
        return self._cur.fetchall()

    def fetchone(self):
        return self._cur.fetchone()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class _Connection:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params=()):
        return self._conn.execute(_tr(sql), params)

    def executescript(self, sql: str):
        return self._conn.executescript(sql)

    def cursor(self) -> _Cursor:
        return _Cursor(self._conn.cursor())


@contextmanager
def connect() -> Iterator[_Connection]:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    try:
        yield _Connection(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping() -> bool:
    """True si la base répond."""
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
