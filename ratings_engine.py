"""
Moteur de calcul des ratings Elo FROM SCRATCH, réplique de la méthodologie
eloratings.net (World Football Elo Ratings de Lange).
Référence primaire : http://eloratings.net/about

Mise à jour après chaque match :
    R_n = R_o + K · G · (W − W_e)

  K  = poids selon l'importance du match (voir K_BY_TIER)
  G  = indice de différence de buts (voir goal_difference_index)
  W  = résultat (1 victoire / 0,5 nul / 0 défaite) ; tirs au but = nul (0,5)
  W_e= espérance de gain (depuis elo.win_expectancy, +100 si à domicile)

Propriété : mise à jour symétrique (ΔR_local = −ΔR_visiteur), donc somme conservée.

LIMITE D'HONNÊTETÉ : reproduire eloratings.net À L'UNITÉ près exige aussi LEUR
classification exacte des tournois (-> K), LEUR initialisation, et leur gestion
des cas limites (matchs abandonnés, forfaits, drapeaux terrain-neutre par match).
Ce moteur reproduit la FORMULE fidèlement ; l'écart résiduel viendra de ces
choix de données, pas du calcul. Vérifier TOURNAMENT_TO_TIER contre eloratings.net.
"""

from __future__ import annotations
from collections import defaultdict
import pandas as pd

from elo import win_expectancy

# Paliers de K (importance du match)
K_BY_TIER = {
    "world_cup_finals": 60,
    "continental_finals": 50,
    "qualifiers": 40,
    "other_tournament": 30,
    "friendly": 20,
}

# Mapping libellé de tournoi -> palier. À CONFIRMER/COMPLÉTER contre eloratings.net.
# Clés en minuscules ; on teste par sous-chaîne. Adapté au dataset Jürisoo (Kaggle).
TOURNAMENT_TO_TIER = {
    "fifa world cup qualification": "qualifiers",
    "fifa world cup": "world_cup_finals",
    "uefa euro qualification": "qualifiers",
    "uefa euro": "continental_finals",
    "copa américa": "continental_finals",
    "copa america": "continental_finals",
    "african cup of nations qualification": "qualifiers",
    "african cup of nations": "continental_finals",
    "afc asian cup qualification": "qualifiers",
    "afc asian cup": "continental_finals",
    "gold cup": "continental_finals",
    "confederations cup": "continental_finals",
    "uefa nations league": "other_tournament",
    "friendly": "friendly",
}
DEFAULT_TIER = "other_tournament"


def classify_tier(tournament: str) -> str:
    """Renvoie le palier de K pour un libellé de tournoi (par sous-chaîne, ordre du dict)."""
    t = (tournament or "").strip().lower()
    for key, tier in TOURNAMENT_TO_TIER.items():
        if key in t:
            return tier
    return DEFAULT_TIER


def k_factor(tournament: str) -> int:
    return K_BY_TIER[classify_tier(tournament)]


def goal_difference_index(goal_diff: int) -> float:
    """G d'eloratings.net. goal_diff = |buts_local − buts_visiteur|."""
    n = abs(int(goal_diff))
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11.0 + n) / 8.0   # n >= 3


def update_match(r_home: float, r_away: float, goals_home: int, goals_away: int,
                 k: float, neutral: bool = True) -> tuple[float, float, float]:
    """
    Met à jour les deux ratings pour un match. Retourne (r_home_new, r_away_new, delta).
    delta = variation du local (le visiteur varie de −delta).
    Un match nul (goals égaux) couvre le cas "décidé aux tirs au but" (W=0,5, G=1).
    """
    home_adv = 0.0 if neutral else 100.0
    we_home = win_expectancy(r_home, r_away, home_adv)
    if goals_home > goals_away:
        w_home = 1.0
    elif goals_home == goals_away:
        w_home = 0.5
    else:
        w_home = 0.0
    g = goal_difference_index(goals_home - goals_away)
    delta = k * g * (w_home - we_home)
    return r_home + delta, r_away - delta, delta


def compute_ratings(
    matches: pd.DataFrame,
    init_rating: float = 1300.0,
    return_history: bool = False,
) -> dict | tuple[dict, pd.DataFrame]:
    """
    Calcule les ratings courants en rejouant tout l'historique chronologiquement.

    `matches` : DataFrame trié ou non, colonnes attendues :
        date, home_team, away_team, home_score, away_score, tournament, neutral(bool)
    init_rating : rating d'entrée d'une équipe vue pour la première fois
        (eloratings backfill depuis 1872 ; valeur à confirmer — n'affecte les
        notes courantes que marginalement vu la longueur de l'historique).
    """
    required = {"date", "home_team", "away_team", "home_score",
                "away_score", "tournament", "neutral"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes : {sorted(missing)}")

    df = matches.sort_values("date", kind="stable").reset_index(drop=True)
    ratings: dict[str, float] = defaultdict(lambda: init_rating)
    hist_rows = []

    for row in df.itertuples(index=False):
        rh, ra = ratings[row.home_team], ratings[row.away_team]
        k = k_factor(row.tournament)
        rh_new, ra_new, delta = update_match(
            rh, ra, int(row.home_score), int(row.away_score),
            k, neutral=bool(row.neutral),
        )
        ratings[row.home_team] = rh_new
        ratings[row.away_team] = ra_new
        if return_history:
            hist_rows.append((row.date, row.home_team, rh_new, row.away_team, ra_new, k, delta))

    ratings = dict(sorted(ratings.items(), key=lambda kv: -kv[1]))
    if return_history:
        hist = pd.DataFrame(hist_rows, columns=[
            "date", "home_team", "home_rating_after",
            "away_team", "away_rating_after", "k", "delta_home"])
        return ratings, hist
    return ratings
