"""
Source de la phase de groupes WC2026 -> tables group_teams + group_matches.

- Composition officielle des 12 groupes (tirage du 05/12/2025), graphies alignées
  sur le dataset martj42. Validée : les 48 équipes existent dans `teams` et
  concordent avec les ancres du tableau (Mexico=1A, Switzerland=1B, Brazil=1C,
  USA=1D, Germany=1E, etc.).
- Les MATCHS de poule sont ingérés depuis le dataset (load_history), filtrés sur
  « FIFA World Cup » 2026 avant le 28/06, et conservés uniquement si les deux
  équipes appartiennent au même groupe. Les classements en sont déduits (glue).

Usage :
    python -m ingestion.source_groups          # (ré)écrit group_teams + group_matches
    python -m ingestion.source_groups --show
"""
from __future__ import annotations

import argparse

import pandas as pd

import config  # noqa: F401  (UTF-8 + .env)
from ingestion import load_history

# Composition officielle (noms = graphies du dataset).
GROUPS: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Fenêtre de la phase de groupes (le R32 commence le 28/06).
GROUP_START = pd.Timestamp("2026-06-01")
GROUP_END = pd.Timestamp("2026-06-27")

# Calendrier des matchs de poule RESTANTS (3e journée), HEURE DE PARIS.
# Source : calendriers publics français (radiosports.fr, recoupé avec France 24 et
# olympics.com). Vérifié : Norvège–France = 26/06 à 21:00 (heure de Paris). Les
# heures tardives (01:00, 04:00…) correspondent aux coups d'envoi en soirée aux
# USA. Les APPARIEMENTS sont déduits des données (paires non jouées) ; ce dict ne
# sert qu'à dater. Clé = frozenset des deux noms (anglais) ; valeur = (date ISO,
# heure de Paris "HH:MM", lieu|None).
REMAINING_SCHEDULE: dict[frozenset, tuple[str, str, str | None]] = {
    # Groupe E — 25/06 22:00 (Paris)
    frozenset({"Germany", "Ecuador"}): ("2026-06-25", "22:00", None),
    frozenset({"Curaçao", "Ivory Coast"}): ("2026-06-25", "22:00", None),
    # Groupe F — 26/06 01:00
    frozenset({"Netherlands", "Tunisia"}): ("2026-06-26", "01:00", None),
    frozenset({"Japan", "Sweden"}): ("2026-06-26", "01:00", None),
    # Groupe D — 26/06 04:00
    frozenset({"United States", "Turkey"}): ("2026-06-26", "04:00", None),
    frozenset({"Paraguay", "Australia"}): ("2026-06-26", "04:00", None),
    # Groupe I — 26/06 21:00
    frozenset({"France", "Norway"}): ("2026-06-26", "21:00", None),
    frozenset({"Senegal", "Iraq"}): ("2026-06-26", "21:00", None),
    # Groupe H — 27/06 02:00
    frozenset({"Spain", "Uruguay"}): ("2026-06-27", "02:00", None),
    frozenset({"Cape Verde", "Saudi Arabia"}): ("2026-06-27", "02:00", None),
    # Groupe G — 27/06 05:00
    frozenset({"Belgium", "New Zealand"}): ("2026-06-27", "05:00", None),
    frozenset({"Egypt", "Iran"}): ("2026-06-27", "05:00", None),
    # Groupe L — 27/06 23:00
    frozenset({"England", "Panama"}): ("2026-06-27", "23:00", None),
    frozenset({"Croatia", "Ghana"}): ("2026-06-27", "23:00", None),
    # Groupe K — 28/06 01:30
    frozenset({"Portugal", "Colombia"}): ("2026-06-28", "01:30", None),
    frozenset({"DR Congo", "Uzbekistan"}): ("2026-06-28", "01:30", None),
    # Groupe J — 28/06 04:00
    frozenset({"Argentina", "Jordan"}): ("2026-06-28", "04:00", None),
    frozenset({"Algeria", "Austria"}): ("2026-06-28", "04:00", None),
}


def _group_of(name: str) -> str | None:
    for code, members in GROUPS.items():
        if name in members:
            return code
    return None


def _prematch_predictions(df) -> dict:
    """
    Rejoue TOUT l'historique chronologiquement et fige, pour chaque match de poule
    WC2026, la prédiction calculée avec l'Elo D'AVANT le match (terrain neutre).
    Clé = (home, away, date) ; valeur = (pred_h, pred_a, p_home, p_draw, p_away).
    Ces prédictions ne dépendent que du passé -> immuables quand de nouveaux
    résultats arrivent.
    """
    from collections import defaultdict

    import goals_model
    from elo import win_expectancy
    from ratings_engine import k_factor, update_match

    cl = goals_model.DEFAULT_CLIP
    clip = lambda x: min(max(x, cl[0]), cl[1])  # noqa: E731

    ratings = defaultdict(lambda: 1300.0)
    preds: dict = {}
    for row in df.sort_values("date", kind="stable").itertuples(index=False):
        h, a = row.home_team, row.away_team
        rh, ra = ratings[h], ratings[a]
        ca = _group_of(h)
        is_grp = (row.tournament == "FIFA World Cup"
                  and GROUP_START <= row.date <= GROUP_END
                  and ca is not None and ca == _group_of(a))
        pred_tuple = None
        if is_grp:
            W = win_expectancy(rh, ra, 0.0)              # PRÉ-match, terrain neutre
            mat = goals_model.scoreline_matrix(
                clip(goals_model.lambda_neutral(W)),
                clip(goals_model.lambda_neutral(1.0 - W)))
            wa, dr, wb = goals_model.outcome_probabilities(mat)
            ph, pa = goals_model.consistent_score(mat)
            # ph/pa = score prédit ; wa/dr/wb = probas ; rh/ra = Elo PRÉ-match figé
            pred_tuple = (ph, pa, wa, dr, wb, rh, ra)
        k = k_factor(row.tournament)
        rh_new, ra_new, delta = update_match(rh, ra, int(row.home_score),
                                             int(row.away_score), k, neutral=bool(row.neutral))
        if is_grp:
            # delta = variation d'Elo du LOCAL pour ce match (le visiteur fait −delta)
            preds[(h, a, row.date.date())] = pred_tuple + (delta,)
        ratings[h], ratings[a] = rh_new, ra_new
    return preds


def load() -> None:
    from db.connection import connect

    # 1) Composition -> group_teams
    team_rows = []
    for code, members in GROUPS.items():
        for pos, name in enumerate(members, 1):
            team_rows.append((code, name, pos))

    # 2) Matchs de poule depuis le dataset + prédictions pré-match figées
    df = load_history.load()
    preds = _prematch_predictions(df)
    g = df[(df["tournament"] == "FIFA World Cup")
           & (df["date"] >= GROUP_START) & (df["date"] <= GROUP_END)]
    match_rows = []
    for r in g.itertuples(index=False):
        ca, cb = _group_of(r.home_team), _group_of(r.away_team)
        if ca is not None and ca == cb:   # match intra-groupe uniquement
            p = preds.get((r.home_team, r.away_team, r.date.date()),
                          (None,) * 8)   # ph,pa,wa,dr,wb,rh,ra,delta
            match_rows.append((ca, r.home_team, r.away_team,
                               int(r.home_score), int(r.away_score),
                               r.date.date().isoformat(), *p))   # date ISO (SQLite)

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name, team_id FROM teams")
        id_by_name = dict(cur.fetchall())

        def tid(n):
            if n not in id_by_name:
                raise ValueError(f"Équipe absente de teams : {n!r}")
            return id_by_name[n]

        cur.execute("DELETE FROM group_teams")
        cur.executemany(
            "INSERT INTO group_teams (group_code, team_id, draw_pos) VALUES (%s,%s,%s)",
            [(c, tid(n), p) for (c, n, p) in team_rows],
        )
        cur.execute("DELETE FROM group_matches")
        cur.executemany(
            """
            INSERT INTO group_matches
              (group_code, home_team_id, away_team_id, home_score, away_score,
               played_at, pred_home_goals, pred_away_goals, p_home, p_draw, p_away,
               elo_home_pre, elo_away_pre, elo_home_delta, elo_away_delta)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [(c, tid(h), tid(a), hs, as_, d, ph, pa, pH, pD, pA, eh, ea,
              dl, (-dl if dl is not None else None))
             for (c, h, a, hs, as_, d, ph, pa, pH, pD, pA, eh, ea, dl) in match_rows],
        )
    print(f"group_teams : {len(team_rows)} (12 groupes). "
          f"group_matches : {len(match_rows)} matchs (avec prédiction pré-match figée).")


def show() -> None:
    from db.connection import connect

    with connect() as conn:
        for code in GROUPS:
            rows = conn.execute(
                """
                SELECT t.name FROM group_teams gt JOIN teams t USING (team_id)
                WHERE gt.group_code = %s ORDER BY gt.draw_pos
                """,
                (code,),
            ).fetchall()
            n = conn.execute(
                "SELECT count(*) FROM group_matches WHERE group_code = %s", (code,)
            ).fetchone()[0]
            print(f"  Groupe {code} ({n} matchs joués) : "
                  + ", ".join(r[0] for r in rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        show()
    else:
        load()
        show()


if __name__ == "__main__":
    main()
