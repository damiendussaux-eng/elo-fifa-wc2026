"""
Chargement de l'historique des matchs internationaux (dépendance critique §6a).

Source : dataset « International football results from 1872 to ... » de Mart
Jürisoo. Miroir GitHub public, mêmes données que la version Kaggle, accessible
sans authentification — colonnes identiques.
  https://github.com/martj42/international_results  (results.csv)

VÉRIFIÉ (2026-06-25) :
  - Colonnes : date, home_team, away_team, home_score, away_score, tournament,
    city, country, neutral  -> superset exact de ce qu'attend compute_ratings.
  - `neutral` est "TRUE"/"FALSE" (chaîne) -> converti en bool.
  - CGU : licence CC0 (domaine public) côté Kaggle ; miroir GitHub public.
  - Fraîcheur : mis à jour en continu jusqu'aux matchs récents. À RE-VÉRIFIER
    avant le tournoi pour s'assurer que la phase de groupes WC2026 y figure.

Les tirs au but : dans ce dataset, un match de coupe décidé aux tirs au but est
enregistré avec le score à la fin du temps réglementaire/prolongation (souvent un
nul). eloratings.net compte justement les tirs au but comme un nul (W=0,5). On
laisse donc les nuls tels quels — on n'applique PAS shootouts.csv au score.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/results.csv"
)
SHOOTOUTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/shootouts.csv"
)
LOCAL_CSV = DATA_DIR / "results.csv"
LOCAL_SHOOTOUTS = DATA_DIR / "shootouts.csv"
# Résultats récents récupérés AUTOMATIQUEMENT d'une source plus à jour (ESPN, via
# ingestion/live_results.py) pour combler le décalage du dataset martj42.
OVERRIDE_CSV = DATA_DIR / "espn_results.csv"

REQUIRED = ["date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "neutral"]


def download(force: bool = False) -> Path:
    """Télécharge results.csv dans data/ (cache local sauf force=True)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LOCAL_CSV.exists() and not force:
        return LOCAL_CSV
    resp = requests.get(RESULTS_URL, timeout=60)
    resp.raise_for_status()
    LOCAL_CSV.write_bytes(resp.content)
    return LOCAL_CSV


def load(path: Path | None = None, download_if_missing: bool = True) -> pd.DataFrame:
    """
    Charge l'historique en DataFrame propre, prêt pour compute_ratings :
    colonnes REQUIRED, `neutral` en bool, scores en int, triés par date.
    """
    if path is None:
        path = LOCAL_CSV
        if not path.exists() and download_if_missing:
            download()
    df = pd.read_csv(path)

    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path}: {sorted(missing)}")

    # Lignes valides uniquement (scores présents).
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)

    # neutral : "TRUE"/"FALSE"/bool -> bool
    df["neutral"] = (
        df["neutral"].astype(str).str.strip().str.lower().map(
            {"true": True, "false": False}
        ).fillna(False).astype(bool)
    )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df[REQUIRED].copy()

    # Résultats récents d'une source plus à jour (ESPN), récupérés automatiquement :
    # complètent martj42 pour les matchs qu'il n'a pas encore publiés.
    df = _merge_overrides(df)

    return df.sort_values("date", kind="stable").reset_index(drop=True)


def _merge_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Fusionne data/espn_results.csv (mêmes colonnes que REQUIRED) ; ces lignes
    complètent/remplacent celles de la source (clé date+home+away)."""
    if not OVERRIDE_CSV.exists():
        return df
    try:
        m = pd.read_csv(OVERRIDE_CSV)
    except Exception:
        return df
    if "home_score" not in m.columns or "away_score" not in m.columns:
        return df
    m = m.dropna(subset=["home_score", "away_score"]).copy()
    if m.empty:
        return df
    m["home_score"] = m["home_score"].astype(int)
    m["away_score"] = m["away_score"].astype(int)
    if "tournament" not in m.columns:
        m["tournament"] = "FIFA World Cup"
    if "neutral" not in m.columns:
        m["neutral"] = True
    m["neutral"] = (m["neutral"].astype(str).str.strip().str.lower()
                    .map({"true": True, "false": False}).fillna(True).astype(bool))
    m["date"] = pd.to_datetime(m["date"], errors="coerce")
    m = m.dropna(subset=["date"])[REQUIRED]
    combined = pd.concat([df, m], ignore_index=True)
    # garde la dernière (= la source live ESPN) en cas de doublon
    return combined.drop_duplicates(subset=["date", "home_team", "away_team"],
                                    keep="last")


def load_shootouts(download_if_missing: bool = True) -> dict[tuple[str, str, str], str]:
    """
    Vainqueurs aux tirs au but : {(date_iso, home, away): winner}.
    Sert au backtest pour départager les matchs à élimination directe nuls à la
    fin du temps réglementaire (le calcul Elo, lui, les compte comme nuls).
    """
    if not LOCAL_SHOOTOUTS.exists() and download_if_missing:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        resp = requests.get(SHOOTOUTS_URL, timeout=60)
        resp.raise_for_status()
        LOCAL_SHOOTOUTS.write_bytes(resp.content)
    if not LOCAL_SHOOTOUTS.exists():
        return {}
    df = pd.read_csv(LOCAL_SHOOTOUTS)
    out: dict[tuple[str, str, str], str] = {}
    for r in df.itertuples(index=False):
        out[(str(r.date), str(r.home_team), str(r.away_team))] = str(r.winner)
    return out


if __name__ == "__main__":
    import config  # noqa: F401  (UTF-8 stdout)

    p = download()
    df = load(p)
    print(f"{len(df):,} matchs chargés depuis {p}")
    print(f"Période : {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"Équipes distinctes : "
          f"{len(set(df['home_team']) | set(df['away_team']))}")
    print("\nDerniers matchs :")
    print(df.tail(5).to_string(index=False))
