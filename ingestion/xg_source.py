"""
Accès ISOLÉ aux xG (buts attendus), interface stable pour la méthode B.

    get_match_xg(match_id) -> (xg_home, xg_away) | None

UN SEUL FOURNISSEUR à la fois (ne JAMAIS mélanger des modèles d'xG différents).
Défaut WC2026 : FBref (xG Opta) via scraping/`soccerdata` — À BRANCHER ET VÉRIFIER
(état du paquet + CGU). Backtest Coupes du Monde passées : StatsBomb Open Data.

⚠️ État actuel : aucun fournisseur xG n'est branché (CGU/disponibilité à valider, et
les résultats WC2026 de ce projet proviennent d'un dataset, pas d'un flux xG réel).
`get_match_xg` renvoie donc None -> le modèle B fait un REPLI sur les BUTS RÉELS,
clairement marqué (champ `xg_is_fallback`). Brancher un fournisseur = implémenter
une classe `XgSource` et la renvoyer par `get_source()`.

Un cache CSV local (data/xg_cache.csv : match_key,xg_home,xg_away) est lu s'il existe,
ce qui permet d'injecter des xG sans coder de scraper.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
XG_CACHE = DATA_DIR / "xg_cache.csv"


def match_key(home: str, away: str, date_iso: str) -> str:
    return f"{date_iso}|{home}|{away}"


class XgSource(Protocol):
    def get(self, key: str) -> tuple[float, float] | None: ...


class NoneSource:
    """Aucun fournisseur : tout renvoie None (-> repli buts réels côté modèle)."""
    def get(self, key: str) -> tuple[float, float] | None:
        return None


class CsvCacheSource:
    """Lit data/xg_cache.csv si présent. Permet d'injecter des xG sans scraper."""
    def __init__(self, path: Path = XG_CACHE):
        self._map: dict[str, tuple[float, float]] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._map[row["match_key"]] = (
                        float(row["xg_home"]), float(row["xg_away"]))

    def get(self, key: str) -> tuple[float, float] | None:
        return self._map.get(key)


class FBrefSource:
    """
    SQUELETTE — FBref (xG Opta) via `soccerdata` ou scraping. NON IMPLÉMENTÉ :
    vérifier d'abord l'état du paquet et les CGU (Sports Reference). Un seul
    fournisseur d'xG : ne pas combiner avec StatsBomb dans le même run.
    """
    def get(self, key: str) -> tuple[float, float] | None:
        raise NotImplementedError(
            "FBref/soccerdata à brancher et VÉRIFIER (CGU + disponibilité). "
            "En attendant : data/xg_cache.csv (CsvCacheSource) ou repli buts réels.")


def get_source(name: str = "auto") -> XgSource:
    """`auto` : cache CSV s'il existe, sinon NoneSource (repli buts réels)."""
    if name in ("auto", "csv"):
        return CsvCacheSource() if XG_CACHE.exists() else NoneSource()
    if name == "none":
        return NoneSource()
    if name == "fbref":
        return FBrefSource()
    raise ValueError(f"Fournisseur xG inconnu : {name!r}")


_DEFAULT = None


def get_match_xg(home: str, away: str, date_iso: str,
                 source: XgSource | None = None) -> tuple[float, float] | None:
    """xG (domicile, extérieur) d'un match, ou None si indisponible (-> repli)."""
    global _DEFAULT
    if source is None:
        if _DEFAULT is None:
            _DEFAULT = get_source("auto")
        source = _DEFAULT
    return source.get(match_key(home, away, date_iso))
