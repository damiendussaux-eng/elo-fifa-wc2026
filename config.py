"""
Configuration centrale : chargement de .env + chemin de la base SQLite.

Stockage = SQLite (fichier local, intégré à Python, AUCUN serveur) : compatible
avec un déploiement gratuit sur Streamlit Community Cloud. La base est reconstruite
à chaque lancement à partir du dataset + ESPN (cf. bootstrap), donc son caractère
éphémère sur le cloud n'est pas un problème.

Sur Windows, la console est en cp1252 et plante sur les caractères unicode (≈,
drapeaux). On force UTF-8 sur stdout/stderr dès l'import.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Sortie console robuste (Windows cp1252 -> UTF-8) ---------------------
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (ValueError, io.UnsupportedOperation):
            pass


# --- Base SQLite ----------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
# Fichier SQLite (paramétrable). Par défaut data/wc2026.sqlite.
DB_PATH = os.getenv("WC2026_DB_PATH", str(DATA_DIR / "wc2026.sqlite"))


# --- Source des résultats de tableau (adaptateur ingestion/source_results) -
RESULTS_SOURCE = os.getenv("RESULTS_SOURCE", "none")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
