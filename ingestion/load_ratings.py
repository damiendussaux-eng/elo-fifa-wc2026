"""
Calcul des ratings Elo FROM SCRATCH (§6a) puis chargement dans elo_ratings.

On NE télécharge PAS les notes : on rejoue tout l'historique des matchs
internationaux chronologiquement via ratings_engine.compute_ratings().

Usage :
    python -m ingestion.load_ratings            # calcule + écrit en base
    python -m ingestion.load_ratings --dry-run  # calcule + affiche, sans base
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

import config  # noqa: F401  (UTF-8 stdout + .env)
from ingestion import load_history
from ingestion.teams_ref import meta_for
from ratings_engine import compute_ratings

SOURCE = "from_scratch:martj42"


def compute_current_ratings() -> tuple[dict[str, float], date]:
    """Retourne (ratings courants par équipe, date du dernier match rejoué)."""
    matches = load_history.load()
    ratings = compute_ratings(matches)
    as_of = matches["date"].max().date()
    return ratings, as_of


def persist(ratings: dict[str, float], as_of: date, source: str = SOURCE) -> int:
    """Upsert teams + insère une ligne elo_ratings par équipe (historisé)."""
    from db.connection import connect

    rows = []
    for name, rating in ratings.items():
        iso2, flag = meta_for(name)
        rows.append((name, iso2, flag, rating))

    with connect() as conn, conn.cursor() as cur:
        # Upsert teams (sans écraser is_host déjà positionné).
        cur.executemany(
            """
            INSERT INTO teams (name, code_iso2, flag_emoji)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET code_iso2  = COALESCE(EXCLUDED.code_iso2, teams.code_iso2),
                  flag_emoji = COALESCE(EXCLUDED.flag_emoji, teams.flag_emoji)
            """,
            [(n, i, f) for (n, i, f, _) in rows],
        )
        # Récupère les team_id.
        cur.execute("SELECT name, team_id FROM teams")
        id_by_name = dict(cur.fetchall())
        # Insère/écrase les ratings de cette date+source.
        cur.executemany(
            """
            INSERT INTO elo_ratings (team_id, rating, as_of, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (team_id, as_of, source) DO UPDATE
              SET rating = EXCLUDED.rating
            """,
            [(id_by_name[n], r, as_of.isoformat(), source) for (n, _, _, r) in rows],
        )
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="calcule et affiche le top 25 sans écrire en base")
    args = ap.parse_args()

    ratings, as_of = compute_current_ratings()
    print(f"Ratings calculés FROM SCRATCH au {as_of} — {len(ratings)} équipes.\n")
    top = pd.Series(ratings).sort_values(ascending=False).head(25)
    print("Top 25 (calcul maison) :")
    for rank, (name, r) in enumerate(top.items(), 1):
        print(f"  {rank:2d}. {name:24s} {r:7.1f}")

    if args.dry_run:
        print("\n[dry-run] rien écrit en base.")
        return

    n = persist(ratings, as_of)
    print(f"\n{n} équipes écrites dans elo_ratings (source={SOURCE}, as_of={as_of}).")


if __name__ == "__main__":
    main()
