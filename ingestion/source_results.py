"""
Adaptateur ISOLÉ des résultats du tableau (§6b) -> table `results`.

Objectif : interface STABLE pour changer de source sans toucher au reste.
Tout le pipeline ne connaît que :
    - le dataclass `KnockoutResult` (dans NOTRE repère bracket : round_idx, match_idx),
    - la fonction `sync()` (lit la source configurée, écrit `results`).

Sources :
  - "none"  (défaut) : aucune ingestion automatique. On épingle à la main via la
    table `results` (ou la source CSV ci-dessous). Choix sûr tant qu'aucune API
    n'est confirmée pour la WC2026.
  - "csv"   : lit data/results_knockout.csv (colonnes : round_idx, match_idx,
    winner_team, played_at). 100 % fonctionnel, zéro dépendance externe.
  - "football_data" : football-data.org v4. Squelette DOCUMENTÉ mais NON VÉRIFIÉ
    pour la WC2026 (couverture du tier gratuit, libellés de stage, CGU à valider) :
    on ne hardcode aucune syntaxe d'API non confirmée — il faut tester avant usage.

round_idx : 0=R32, 1=R16, 2=quarts, 3=demies, 4=finale (cohérent avec bracket_sim).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "results_knockout.csv"


@dataclass(frozen=True)
class KnockoutResult:
    """Un résultat connu, exprimé dans NOTRE repère de bracket."""
    round_idx: int
    match_idx: int
    winner_team: str          # nom d'équipe (clé naturelle de teams.name)
    played_at: datetime | None = None


class ResultsSource(Protocol):
    """Interface stable : toute source renvoie des KnockoutResult."""
    def fetch(self) -> list[KnockoutResult]: ...


# --------------------------------------------------------------------------- #
class NoneSource:
    """Pas d'ingestion automatique (défaut)."""
    def fetch(self) -> list[KnockoutResult]:
        return []


class CsvResultsSource:
    """
    Lit data/results_knockout.csv. En-têtes attendus :
        round_idx,match_idx,winner_team,played_at
    `played_at` au format ISO (optionnel). Voie simple pour épingler à la main.
    """
    def __init__(self, path: Path = CSV_PATH):
        self.path = path

    def fetch(self) -> list[KnockoutResult]:
        if not self.path.exists():
            return []
        out: list[KnockoutResult] = []
        with self.path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                played = row.get("played_at") or ""
                out.append(KnockoutResult(
                    round_idx=int(row["round_idx"]),
                    match_idx=int(row["match_idx"]),
                    winner_team=row["winner_team"].strip(),
                    played_at=datetime.fromisoformat(played) if played else None,
                ))
        return out


class FootballDataSource:
    """
    football-data.org v4 — SQUELETTE DOCUMENTÉ, NON VÉRIFIÉ pour la WC2026.

    AVANT USAGE, vérifier (cf. §6b) :
      - que le tier gratuit couvre bien la Coupe du Monde 2026 (code compétition) ;
      - les libellés exacts de `stage` (LAST_16/QUARTER_FINALS/…) -> round_idx ;
      - la résolution match_idx : un match externe (équipe A vs B) doit être relié
        au bon slot via l'état courant de bracket_slots (équipes déjà affectées).
        Tant que les slots n'ont pas de team_id, cette résolution est impossible.

    L'implémentation réseau est volontairement laissée à compléter pour ne pas
    coder une syntaxe d'API non confirmée.
    """
    BASE = "https://api.football-data.org/v4"
    STAGE_TO_ROUND = {
        "LAST_32": 0, "ROUND_OF_32": 0,
        "LAST_16": 1, "ROUND_OF_16": 1,
        "QUARTER_FINALS": 2, "QUARTER_FINAL": 2,
        "SEMI_FINALS": 3, "SEMI_FINAL": 3,
        "FINAL": 4,
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.FOOTBALL_DATA_API_KEY

    def fetch(self) -> list[KnockoutResult]:
        if not self.api_key:
            raise RuntimeError(
                "FOOTBALL_DATA_API_KEY manquant. Renseigner .env, ou utiliser "
                "RESULTS_SOURCE=csv / none en attendant de vérifier l'API."
            )
        raise NotImplementedError(
            "Adaptateur football-data.org à finaliser et VÉRIFIER pour la WC2026 "
            "(couverture, libellés de stage, mapping match_idx). Voir docstring."
        )


# --------------------------------------------------------------------------- #
def get_source(name: str | None = None) -> ResultsSource:
    name = (name or config.RESULTS_SOURCE or "none").lower()
    if name == "none":
        return NoneSource()
    if name == "csv":
        return CsvResultsSource()
    if name == "football_data":
        return FootballDataSource()
    raise ValueError(f"RESULTS_SOURCE inconnu : {name!r}")


def persist_results(results: list[KnockoutResult]) -> int:
    """Upsert dans `results` (résout winner_team -> team_id)."""
    if not results:
        return 0
    from db.connection import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name, team_id FROM teams")
        id_by_name = dict(cur.fetchall())
        rows = []
        for r in results:
            tid = id_by_name.get(r.winner_team)
            if tid is None:
                raise ValueError(
                    f"Vainqueur inconnu dans teams : {r.winner_team!r} "
                    f"(match {r.round_idx}/{r.match_idx})"
                )
            played = r.played_at.isoformat() if r.played_at is not None else None
            rows.append((r.round_idx, r.match_idx, tid, played))
        cur.executemany(
            """
            INSERT INTO results (round_idx, match_idx, winner_team_id, played_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (round_idx, match_idx) DO UPDATE
              SET winner_team_id = EXCLUDED.winner_team_id,
                  played_at      = EXCLUDED.played_at
            """,
            rows,
        )
    return len(rows)


def sync(source_name: str | None = None) -> int:
    """Lit la source configurée et écrit `results`. Retourne le nb de lignes."""
    src = get_source(source_name)
    n = persist_results(src.fetch())
    print(f"Résultats synchronisés : {n} (source={source_name or config.RESULTS_SOURCE}).")
    return n


if __name__ == "__main__":
    sync()
