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
    print(f"Schéma appliqué depuis {SCHEMA_PATH.name}.")


if __name__ == "__main__":
    migrate()
