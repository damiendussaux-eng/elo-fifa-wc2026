"""
Applique le schéma (db/schema.sql). Idempotent.
Usage : python -m db.migrate
"""
from __future__ import annotations

from pathlib import Path

import config  # noqa: F401  (force la reconfiguration UTF-8 + chargement .env)
from db.connection import connect

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def migrate() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(sql)   # plusieurs instructions -> executescript (SQLite)
        _ensure_columns(conn)     # colonnes ajoutées après coup (bases locales déjà créées)
    print(f"Schéma appliqué depuis {SCHEMA_PATH.name}.")


def _ensure_columns(conn) -> None:
    """ALTER idempotents : ajoute les colonnes récentes aux bases déjà existantes
    (CREATE TABLE IF NOT EXISTS ne modifie pas une table déjà créée)."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(results)").fetchall()}
    for col in ("score_a", "score_b"):
        if col not in have:
            conn.execute(f"ALTER TABLE results ADD COLUMN {col} INTEGER")


if __name__ == "__main__":
    migrate()
